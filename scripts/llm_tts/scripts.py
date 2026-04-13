# scripts/llm_tts.py 
### llm + tts:  
# 1. realtime
# 2. text-input
# 3. voice-output
# coding=utf-8
import os
import time
import asyncio
import threading
import queue
import re
import io
import subprocess
import atexit
import urllib.request
import urllib.error
import base64  
import gc  # 新增：用于垃圾回收
from typing import AsyncGenerator, Optional, Dict, Any, List

import torch
import numpy as np
import soundfile as sf
from loguru import logger
from fastapi import FastAPI, BackgroundTasks, WebSocket, WebSocketDisconnect 
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
from openai import AsyncOpenAI
from contextlib import asynccontextmanager

# ==========================================
# 1. 配置管理 (Pydantic-Settings)
# ==========================================

import os
# 强行把镜像站塞进环境变量，天王老子来了也得走国内镜像
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
# 强制 Hugging Face 进入离线模式
os.environ["HF_HUB_OFFLINE"] = "1"
import warnings
warnings.filterwarnings("ignore")


class AppSettings(BaseSettings):
    # LLM 配置
    gguf_file: str = "/mnt/e/local_models/huggingface/local/Qwen3.5-4B-Q4_1.gguf"  # 0.8B, 4B
    llamacpp_bin: str = "/home/baheas/githubrepos/llama.cpp/build/bin/llama-server"
    koko_model: str = "/mnt/e/local_models/huggingface/cache/hub/models--hexgrad--Kokoro-82M/snapshots/f3ff3571791e39611d31c381e3a41a3af07b4987"
    qwen_model: str = "/mnt/e/local_models/modelscope/models/Qwen/Qwen3-TTS-12Hz-0___6B-Base"
    
    llm_port: int = 8080
    ctx_size: int = 4096
    
    # 播放器配置
    audio_sample_rate: int = 24000
    
    # Pydantic V2 的标准写法，消灭警告
    model_config = SettingsConfigDict(env_prefix="NENE_")

settings = AppSettings()


# ==========================================
# 2. 核心基础组件 ( Chunker)
# ==========================================

class TextChunker:
    """流式文本分块器（按标点截断）"""
    def __init__(self):
        self.split_pattern = re.compile(r'([。！？；，,!?;\n])')

    async def chunk_stream(self, token_queue: asyncio.Queue) -> AsyncGenerator[str, None]:
        buffer = ""
        while True:
            token = await token_queue.get()
            if token is None:  # 结束信号
                if buffer.strip():
                    yield buffer.strip()
                break
                
            buffer += token
            if self.split_pattern.search(token):
                yield buffer.strip()
                buffer = ""


# ==========================================
# 3. 本地 LLM 引擎 (llama.cpp)
# ==========================================
class LlamaCppServerLLMcpu:
    """基于 llama-server 的本地 LLM 独立进程 (全异步生命周期)"""
    def __init__(self):
        self.server_process = None
        self.client = None
        self._is_ready = False

    async def startup(self):
        """异步启动服务并等待就绪"""
        self._start_server_process()
        # 异步等待服务健康，绝不阻塞主线程
        await self._wait_for_health_async()
        self._init_client()
        self._is_ready = True
        
    def _start_server_process(self):
        command = [
            settings.llamacpp_bin,
            "-m", settings.gguf_file,
            "-c", str(settings.ctx_size),
            "--port", str(settings.llm_port),
            # 强制指定 Qwen 的专属模板，防止出现上下文截断或无限循环生成的 Bug
            "--chat-template", "chatml"
        ]
        logger.info(f"Starting local llama-server on port {settings.llm_port}...")
        
        # 无 llamacpp 日志
        self.server_process = subprocess.Popen(
            command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        # # 有 llamacpp 日志
        # self.server_process = subprocess.Popen(command)
        
        # 注册退出回调，防止 Python 崩溃时留下僵尸 C++ 进程
        atexit.register(self._sync_cleanup)
        

    async def _wait_for_health_async(self, timeout: int = 120):
        """异步健康检查轮询，等待 llama.cpp 的 HTTP 服务就绪"""
        health_url = f"http://localhost:{settings.llm_port}/health"
        start_time = time.time()
        
        # 将 urllib 的同步请求包装为函数，以便投入线程池
        def _ping():
            try:
                urllib.request.urlopen(health_url)
                return True
            except (urllib.error.URLError, ConnectionResetError):
                return False
        
        
        while time.time() - start_time < timeout:
            # 使用 to_thread 发起 HTTP 请求，防止阻塞
            is_healthy = await asyncio.to_thread(_ping)
            if is_healthy:
                logger.info(f"✅ LLM {settings.gguf_file.rsplit(os.sep, 1)[1]} Server is ready!")
                return
            # 使用 asyncio.sleep 代替 time.sleep，把 CPU 时间片让给其他任务
            await asyncio.sleep(1)

        await self.teardown()        
        raise TimeoutError("llama-server failed to start within the timeout period.")
    
    def _init_client(self):
        """初始化官方的 AsyncOpenAI 客户端，将其指向我们的本地端口"""
        self.client = AsyncOpenAI(
            base_url=f"http://localhost:{settings.llm_port}/v1",
            api_key="sk-local"
        )

    async def teardown(self) -> None:
        """关闭服务，由 FastAPI lifespan 调用"""
        logger.info("🛑 正在关闭 LLM 引擎与 llama.cpp 子进程...")
        self._sync_cleanup()
        self._is_ready = False

    def _sync_cleanup(self):
        """实际的清理逻辑（同步，供 teardown 和 atexit 复用）"""
        if self.server_process and self.server_process.poll() is None:
            logger.info("Terminating llama-server...")
            self.server_process.terminate()
            self.server_process.wait()
            self.server_process = None

    async def astream_chat(self, prompt: str) -> AsyncGenerator[str, None]:
        """核心业务接口：接收用户输入，返回异步的文字流"""
        response = await self.client.chat.completions.create(
            model="local",
            messages=[{"role": "user", "content": prompt}],
            stream=True,
            temperature=0.7
        )
        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


# ==========================================
# 4. TTS 引擎工厂
# ==========================================
class BaseTTS:
    async def startup(self) -> None:
        """异步初始化：加载模型、预热、建立连接等"""
        pass
    
    async def synthesize(self, text: str) -> Optional[np.ndarray]:
        raise NotImplementedError
    
    async def teardown(self) -> None:
        """子类需实现此方法以清理资源和显存"""
        pass
    
    @property
    def is_ready(self) -> bool:
        """ states """
        return self._is_ready 

class KokoroTTS(BaseTTS):
    def __init__(self):
        super().__init__()
        self.pipeline = None 
        self.voice = "zf_xiaoxiao"
        
    async def startup(self) -> None:
        logger.info("Initializing KokoroTTS in background...")
        
        # 将耗时的同步加载过程封装到函数中
        def _load_model():
            from kokoro import KPipeline
            # self.pipeline = KPipeline(lang_code='z', repo_id='hexgrad/Kokoro-82M')
            self.pipeline = KPipeline(lang_code='z', repo_id=settings.koko_model, device="cuda")
            # 预热
            list(self.pipeline("测试", voice=self.voice, speed=1.0))

        # 线程池加载
        await asyncio.to_thread(_load_model)
        self._is_ready = True 
        logger.info("✅ KokoroTTS is ready!")

    async def synthesize(self, text: str) -> Optional[np.ndarray]:
        """
        Kokoro 的推理是 CPU/GPU 密集型且同步阻塞的。如果直接在主线程跑，会导致 FastAPI 卡死。
        利用 asyncio.to_thread 将其丢入后台线程池执行，保证网络服务的并发能力。
        """
        def sync_infer():
            generator = self.pipeline(text, voice=self.voice, speed=1.0)
            for _, _, audio in generator:
                return audio  # 直接返回 Float32 的 NumPy 数组
            return None
        return await asyncio.to_thread(sync_infer)

    async def teardown(self) -> None:
        logger.info("Unloading KokoroTTS and releasing VRAM...")
        if hasattr(self, 'pipeline'):
            del self.pipeline
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


class EdgeTTS(BaseTTS):
    def __init__(self):
        self.voice = "zh-CN-XiaoxiaoNeural"
    
    async def startup(self) -> None:
        logger.info("Initializing EdgeTTS...")
        self._is_ready = True
        logger.info("✅ EdgeTTS is ready!")
    
    async def synthesize(self, text: str) -> Optional[np.ndarray]:
        import edge_tts
        from pydub import AudioSegment
        communicate = edge_tts.Communicate(text, voice=self.voice, proxy="http://127.0.0.1:7890")
        # communicate = edge_tts.Communicate(text, voice=self.voice)
        audio_bytes = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_bytes += chunk["data"]
                
        if not audio_bytes:
            return None
            
        # Edge-TTS 默认返回 MP3，将其转换为 float32 PCM 以适应 AudioPlayer
        def decode_audio():
            audio_segment = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
            audio_segment = audio_segment.set_frame_rate(settings.audio_sample_rate).set_channels(1)
            samples = np.array(audio_segment.get_array_of_samples()).astype(np.float32)
            # 归一化到 [-1.0, 1.0]
            samples /= np.iinfo(audio_segment.array_type).max
            return samples
            
        return await asyncio.to_thread(decode_audio)

    async def teardown(self) -> None:
        logger.info("Closing EdgeTTS resources...")
        # 在线接口无需清理显存，只需占位即可
        pass


class QwenTTS(BaseTTS):
    def __init__(self):
        super().__init__() # 继承基类的 _is_ready 状态
        self.model = None 
        
    async def startup(self) -> BaseTTS:
        logger.info("Initializing Qwen3-TTS...")
        
        def _load_model():
            import torchaudio
            from qwen_tts import Qwen3TTSModel
            import soundfile as sf
            
            # 应用魔法补丁防止 torchaudio 在 Ubuntu 环境下偶尔的 ffmpeg 冲突
            torchaudio.load = lambda f, *a, **kw: (torch.from_numpy(sf.read(f)[0]).float().unsqueeze(0), sf.read(f)[1])
            
            self.model = Qwen3TTSModel.from_pretrained(
                # "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
                settings.qwen_model,
                device_map="cuda:0",
                dtype=torch.float16
            )
            torch.set_num_threads(8)
        
        # 将耗时的模型加载丢给后台线程
        await asyncio.to_thread(_load_model)
        self._is_ready = True 
        logger.info("✅ Qwen3-TTS is ready!")

        return self 

    async def synthesize(self, text: str) -> Optional[np.ndarray]:
        def sync_infer():
            wavs, sr = self.model.generate_custom_voice(
                text=text, language="Chinese", speaker="Vivian", instruct=""
            )
            return wavs[0]
        return await asyncio.to_thread(sync_infer)

    async def teardown(self) -> None:
        logger.info("Unloading Qwen3-TTS and releasing VRAM...")
        if hasattr(self, 'model'):
            del self.model
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

# ==========================================
# 5. 全局单例声明
# ==========================================
llm_engine: LlamaCppServerLLMcpu = None
tts_engines: Dict[str, BaseTTS] = {}

# ==========================================
# 6. 生命周期管理 (Lifespan)
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # -------------------
    # 1. Startup (启动阶段)
    # -------------------
    logger.info("🚀 正在启动系统资源...")
    
    # 初始化 LLM 引擎 (会拉起 llama-server)
    llm_engine = LlamaCppServerLLMcpu()  # app.state.llm_engine
    await llm_engine.startup()
    app.state.llm_engine = llm_engine
    
    # 瞬间创建空壳实例，拿到它的引用
    edge_engine = EdgeTTS()
    # 异步执行耗时的加载操作
    await edge_engine.startup()     # startup() 的返回值 如果是自身的话，一行代码搞定。
    # 将装载完毕的实例挂载到全局状态上
    tts_engines['edge'] = edge_engine
    app.state.tts_engines = tts_engines   # 字典整个挂载到 app.state 
    # # app.state.tts_engines = await EdgeTTS().startup()
    
    logger.info("✅ 所有核心服务已就绪！")
    
    # 将控制权交还给 FastAPI 框架，服务开始处理请求
    yield  
    
    # -------------------
    # 2. Shutdown (关闭阶段 - 当你按下 Ctrl+C 时触发)
    # -------------------
    logger.info("🛑 正在关闭 Nene 系统，清理资源...")
    
    # 终止 llama.cpp 子进程，防止变成僵尸进程占用 VRAM/RAM
    if hasattr(app.state, "llm_engine") and app.state.llm_engine:
        await app.state.llm_engine.teardown()
    # 遍历字典，优雅关闭所有后台拉起的引擎
    if hasattr(app.state, "tts_engines"):
        for name, engine in app.state.tts_engines.items():
            logger.info(f"正在清理 TTS 引擎: {name}")
            await engine.teardown()
        app.state.tts_engines.clear() # 斩断引用，协助 GC 回收显存
        
    logger.info("👋 资源清理完毕，安全退出。")

# ==========================================
# 7. FastAPI 实例初始化
# ==========================================
app = FastAPI(
    title=" RAG - LLM & TTS Streaming API", 
    lifespan=lifespan
)

class ChatRequest(BaseModel):
    prompt: str
    tts_type: str = "kokoro"  # 可选 "kokoro", "edge", "qwen"

# ===============================================================
# 8. 核心业务：WebSocket 双轨流式工作流  # websocket禁止并发写入
# ===============================================================
async def background_tts_worker(websocket: WebSocket, 
                                token_queue: asyncio.Queue, 
                                tts_type: str, 
                                ws_lock: asyncio.Lock, 
                                cancel_event: asyncio.Event):
    """
    [后台消费者任务]
    作用：从队列拿 Token -> 切分成句 -> 交给 TTS 推理 -> 转 Base64 -> 推给前端
    """
    chunker = TextChunker()
    engine = websocket.app.state.tts_engines.get(tts_type)
    
    # 动态实时加载未被预热的 TTS 引擎
    if not engine:
        logger.warning(f"TTS 引擎 {tts_type} 未初始化，尝试实时加载...")
        if tts_type == "edge": engine = EdgeTTS()
        elif tts_type == "qwen": engine = QwenTTS()
        else: engine = KokoroTTS()
        tts_engines[tts_type] = engine
        
        # 不要忘了调用 startup 来加载模型！
        await engine.startup()
        
        # 加载完后，塞回全局字典，下次别人请求就不用再加载了
        websocket.app.state.tts_engines[tts_type] = engine
        logger.info(f"✅ TTS 引擎 {tts_type} 异步加载完毕！")

        
    try:
        # 循环从队列切分出完整句子
        async for sentence in chunker.chunk_stream(token_queue):
            logger.debug(f"[TTS 目标句子]: {sentence}")
            if cancel_event.is_set(): 
                break
            t0 = time.time()
            
            # 1. 声音推理
            audio_data = await engine.synthesize(sentence)  
            
            if audio_data is not None and not cancel_event.is_set():
                # 针对 torch.Tensor
                if hasattr(audio_data, 'detach'):  # 判断如果是 Tensor
                    audio_data = audio_data.detach().cpu().numpy()
                # 2. 内存转换：NumPy Array (Float32) -> 纯字节 (Bytes) -> Base64 字符串
                audio_bytes = audio_data.astype(np.float32).tobytes()
                b64_audio = base64.b64encode(audio_bytes).decode('utf-8')
                
                # 发送音频前，确保 websocket 没有被关闭
                if websocket.client_state.name == "CONNECTED":
                    # ws_lock
                    async with ws_lock:
                        await websocket.send_json({
                            "type": "audio",
                            "data": b64_audio,
                            "sample_rate": settings.audio_sample_rate
                        })
                    logger.debug(f"[{tts_type.upper()}] 音频块合成并发送耗时: {time.time() - t0:.4f}s")   
    except asyncio.CancelledError:
        logger.warning("⚠️ 后台 TTS 任务被强制取消 (前端已断开)。")
    except Exception as e:
        # 💡 使用 logger.exception 打印完整的错误栈，不再是空白！
        logger.exception(f"❌ 后台 TTS 合成发生致命错误")         


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """
    [前端 WebSocket 接入点]
    维持着“双轨机制”：一轨快速吐字给前端，另一轨把字塞进队列给后台 TTS 慢速合成。
    """
    await websocket.accept()
    logger.info("🟢 前端已连接到 WebSocket") # [修复] 补上字符串引号

    ws_lock = asyncio.Lock()
    # stop
    cancel_event = asyncio.Event()
    llm_task = None 
    tts_task = None 
    
    try:
        # 1. 接收前端的握手参数 (提问内容和引擎选择)
        data = await websocket.receive_json()
        original_prompt = data.get("prompt", "你好")
        tts_type = data.get("tts_type", "edge") # [修复] 修正键名为 tts_type
        
        # 启动一个专门监听“打断”信号的子任务
        async def listen_for_stop():
            try:
                while True:
                    msg = await websocket.receive_json()
                    if msg.get("action") == "stop":
                        logger.warning("🚨 收到前端核按钮，紧急刹车！")
                        cancel_event.set() # 拉响警报
                        break
            except Exception as e:
                logger.error(str(e))
        listener_task = asyncio.create_task(listen_for_stop())
        
        prompt = f"你是一个中文语音助手。请直接给出简短的回答，绝对不要输出任何你的内部思考过程或分析。请用简短、自然、口语化的中文回答。用户问：{original_prompt}"
        
        # 初始化通信队列
        token_queue = asyncio.Queue()
        
        # 2. 启动后台消费者任务 (它会在后台默默等待 token 进来)
        tts_task = asyncio.create_task(
            background_tts_worker(
                websocket=websocket, 
                token_queue=token_queue, 
                tts_type=tts_type,
                ws_lock=ws_lock,
                cancel_event=cancel_event
            )
        )
            
        # 3. 主任务：驱动大模型生成 (生产者)
        async for chunk in websocket.app.state.llm_engine.astream_chat(prompt):
            # 检查打断信号，如果被踩刹车，立刻中止 LLM 推理！
            if cancel_event.is_set():
                logger.info("🛑 收到打断信号，中止大模型生成！")
                break
            
            # 将新生成的字立刻通过 WebSocket 发给前端 (文字流)
            async with ws_lock:
                await websocket.send_json({"type": "text", "content": chunk})
            # 同时，把字扔进队列里，喂给后台的 TTS Worker
            await token_queue.put(chunk)
            
        # 扫尾工作
        # 发送 None 信号，告诉队列“话已经说完了，收工”
        await token_queue.put(None)
        
        # 等待后台的 TTS 任务把所有语音都合成并发送完毕
        await tts_task 
        
        # 关掉监听任务
        listener_task.cancel()
        
        # 告诉前端：对话和音频已全部传输结束
        if not cancel_event.is_set():
            async with ws_lock:
                await websocket.send_json({"type": "done"})
                
        logger.info("✅ 本次会话所有数据流处理完毕")

    except WebSocketDisconnect:
        logger.info("🔴 前端断开连接")
    except Exception as e:
        logger.error(f"❌ WebSocket 通信异常: {e}")
    finally:
        # 清理
        cancel_event.set()
        
        # 如果发生异常或断开，必须取消后台仍在死算的 TTS 任务
        if tts_task and not tts_task.done():
            tts_task.cancel()
        # 确保哪怕发生异常也会安全关闭连接
        try:
            await websocket.close()
        except:
            pass

if __name__ == "__main__":
    import uvicorn
    # 启动 ASGI 服务器
    uvicorn.run(app, host="0.0.0.0", port=8081)
    
    # todo
    # 我想到了用grpc代替websocket会更好吗？