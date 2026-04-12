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
from typing import AsyncGenerator, Optional, Dict, Any, List

import torch
import numpy as np
import pyaudio
import soundfile as sf
from loguru import logger
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
from openai import AsyncOpenAI
from contextlib import asynccontextmanager

# ==========================================
# 1. 配置管理 (Pydantic-Settings)
# ==========================================
class AppSettings(BaseSettings):
    # LLM 配置
    gguf_file: str = "/mnt/e/local_models/huggingface/local/Qwen3.5-0.8B-Q4_1.gguf"
    llamacpp_bin: str = "/home/baheas/githubrepos/llama.cpp/build/bin/llama-server"
    llm_port: int = 8080
    ctx_size: int = 4096
    
    # 播放器配置
    audio_sample_rate: int = 24000
    
    # class Config:
    #     env_prefix = "NENE_"
    
    # Pydantic V2 的标准写法，消灭警告
    model_config = SettingsConfigDict(env_prefix="NENE_")

settings = AppSettings()


# ==========================================
# 2. 核心基础组件 (Player & Chunker)
# ==========================================
class AudioPlayer:
    """本地音频流式播放器 (后台线程消费队列)"""
    def __init__(self, sample_rate=settings.audio_sample_rate):
        self.sample_rate = sample_rate
        self.p = pyaudio.PyAudio()
        self.queue = queue.Queue()
        self.is_playing = True
        self.thread = threading.Thread(target=self._play_loop, daemon=True)
        self.thread.start()

    def _play_loop(self):
        # 1. 尝试打开音频设备，加了异常保护
        try:
            stream = self.p.open(
                format=pyaudio.paFloat32,
                channels=1,
                rate=self.sample_rate,
                output=True
            )
        except OSError as e:
            logger.warning(f"⚠️ 无法打开物理音频设备，本地播放已禁用 (通常发生在 WSL/服务器环境下)。")
            logger.warning("🔊 TTS 音频仍在后台正常合成，只是不会通过扬声器放出来。")
            self.is_playing = False
            
            # 持续消费队列，防止内存溢出 (既然不播放，就直接丢弃音频数据)
            while True:
                try:
                    data = self.queue.get(timeout=1.0)
                    if data is None: # 收到退出信号
                        self.queue.task_done()
                        break
                    self.queue.task_done()
                except queue.Empty:
                    if not self.is_playing and getattr(self, '_force_quit', False):
                        break
            return

        # 2. 如果设备正常，走正常的播放逻辑
        while self.is_playing:
            try:
                data = self.queue.get(timeout=0.5)
                # 收到 None 信号，代表系统正在关闭，直接退出循环
                if data is None:
                    self.queue.task_done()
                    break 
                
                if data is not None:
                    # 确保是 NumPy float32 格式
                    if isinstance(data, torch.Tensor):
                        data = data.detach().cpu().numpy()
                    stream.write(data.astype(np.float32).tobytes())
                self.queue.task_done()
            except queue.Empty:
                continue
                
        stream.stop_stream()
        stream.close()

    def add_to_queue(self, audio_data: np.ndarray):
        self.queue.put(audio_data)

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
    """基于 llama-server 的本地 LLM 独立进程"""
    def __init__(self):
        self.server_process = None
        self.client = None
        self._start_server()
        self._init_client()

    def _start_server(self):
        command = [
            settings.llamacpp_bin,
            "-m", settings.gguf_file,
            "-c", str(settings.ctx_size),
            "--port", str(settings.llm_port),
            "--chat-template", "chatml"
        ]
        logger.info(f"Starting local llama-server on port {settings.llm_port}...")
        
        # # 无 llamacpp 日志
        # self.server_process = subprocess.Popen(
        #     command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        # )
        # 有 llamacpp 日志
        self.server_process = subprocess.Popen(command)
        
        atexit.register(self._cleanup_process)
        self._wait_for_health()

    def _wait_for_health(self, timeout: int = 120):
        health_url = f"http://localhost:{settings.llm_port}/health"
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                urllib.request.urlopen(health_url)
                logger.info("LLM Server is ready!")
                return
            except (urllib.error.URLError, ConnectionResetError):
                time.sleep(1)
        self._cleanup_process()
        raise TimeoutError("llama-server failed to start.")

    def _init_client(self):
        self.client = AsyncOpenAI(
            base_url=f"http://localhost:{settings.llm_port}/v1",
            api_key="sk-local"
        )

    def _cleanup_process(self):
        if self.server_process and self.server_process.poll() is None:
            logger.info("Terminating llama-server...")
            self.server_process.terminate()
            self.server_process.wait()

    async def astream_chat(self, prompt: str) -> AsyncGenerator[str, None]:
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
    async def synthesize(self, text: str) -> Optional[np.ndarray]:
        raise NotImplementedError

class KokoroTTS(BaseTTS):
    def __init__(self):
        logger.info("Initializing KokoroTTS...")
        from kokoro import KPipeline
        import warnings
        warnings.filterwarnings("ignore")
        self.pipeline = KPipeline(lang_code='z', repo_id='hexgrad/Kokoro-82M')
        self.voice = "zf_xiaoxiao"
        # 预热
        list(self.pipeline("测试", voice=self.voice, speed=1.0))

    async def synthesize(self, text: str) -> Optional[np.ndarray]:
        def sync_infer():
            generator = self.pipeline(text, voice=self.voice, speed=1.0)
            for _, _, audio in generator:
                return audio  # 已经返回 numpy array
            return None
        return await asyncio.to_thread(sync_infer)

class EdgeTTS(BaseTTS):
    def __init__(self):
        logger.info("Initializing EdgeTTS...")
        self.voice = "zh-CN-XiaoxiaoNeural"
        
    async def synthesize(self, text: str) -> Optional[np.ndarray]:
        import edge_tts
        from pydub import AudioSegment
        
        communicate = edge_tts.Communicate(text, voice=self.voice)
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

class QwenTTS(BaseTTS):
    def __init__(self):
        logger.info("Initializing Qwen3-TTS...")
        from qwen_tts import Qwen3TTSModel
        import torchaudio
        import soundfile as sf
        
        # 应用魔法补丁防止 torchaudio 在 Ubuntu 环境下偶尔的 ffmpeg 冲突
        torchaudio.load = lambda f, *a, **kw: (torch.from_numpy(sf.read(f)[0]).float().unsqueeze(0), sf.read(f)[1])
        
        self.model = Qwen3TTSModel.from_pretrained(
            "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
            device_map="cpu",
            dtype=torch.float32
        )
        torch.set_num_threads(8)

    async def synthesize(self, text: str) -> Optional[np.ndarray]:
        def sync_infer():
            wavs, sr = self.model.generate_custom_voice(
                text=text, language="Chinese", speaker="Vivian", instruct=""
            )
            return wavs[0]
        return await asyncio.to_thread(sync_infer)


# ==========================================
# 全局单例声明
# ==========================================
llm_engine: LlamaCppServerLLMcpu = None
audio_player: AudioPlayer = None
tts_engines: Dict[str, BaseTTS] = {}

# ==========================================
# 生命周期管理 (Lifespan)
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # -------------------
    # 1. Startup (启动阶段)
    # -------------------
    global llm_engine, audio_player
    logger.info("🚀 正在启动 Nene 系统资源...")
    
    # 初始化 LLM 引擎 (会拉起 llama-server)
    llm_engine = LlamaCppServerLLMcpu()  # app.statu.llm_engine
    
    # 初始化音频播放器
    audio_player = AudioPlayer()      # app.statu.audio_player
    
    # 预加载默认的 TTS 引擎 (Kokoro)
    tts_engines["kokoro"] = KokoroTTS()
    
    logger.info("✅ 所有核心服务已就绪！")
    
    # 将控制权交还给 FastAPI 框架，服务开始处理请求
    yield  
    
    # -------------------
    # 2. Shutdown (关闭阶段 - 当你按下 Ctrl+C 时触发)
    # -------------------
    logger.info("🛑 正在关闭 Nene 系统，清理资源...")
    
    # 停止音频播放器线程并释放音频流
    if audio_player:
        audio_player.is_playing = False
        # 发送一个空信号唤醒可能阻塞的队列
        audio_player.queue.put(None) 
    
    # 终止 llama.cpp 子进程，防止变成僵尸进程占用 VRAM/RAM
    if llm_engine:
        llm_engine._cleanup_process()
        
    logger.info("👋 资源清理完毕，安全退出。")

# ==========================================
# FastAPI 实例 (注入 lifespan)
# ==========================================
app = FastAPI(
    title="Nene RAG - LLM & TTS Streaming API", 
    lifespan=lifespan
)


class ChatRequest(BaseModel):
    prompt: str
    tts_type: str = "kokoro"  # 可选 "kokoro", "edge", "qwen"

async def background_tts_worker(token_queue: asyncio.Queue, tts_type: str):
    """后台任务：消费 token，切分成句，合成语音并播放"""
    chunker = TextChunker()
    engine = tts_engines.get(tts_type)
    
    if not engine:
        logger.warning(f"TTS 引擎 {tts_type} 未初始化，尝试实时加载...")
        if tts_type == "edge": engine = EdgeTTS()
        elif tts_type == "qwen": engine = QwenTTS()
        else: engine = KokoroTTS()
        tts_engines[tts_type] = engine

    async for sentence in chunker.chunk_stream(token_queue):
        logger.debug(f"[TTS 目标句子]: {sentence}")
        t0 = time.time()
        audio_np = await engine.synthesize(sentence)
        if audio_np is not None:
            logger.debug(f"[{tts_type.upper()}] 合成耗时: {time.time() - t0:.2f}s")
            audio_player.add_to_queue(audio_np)

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest, background_tasks: BackgroundTasks):
    """
    处理对话流：
    前端收到 LLM 的文本 Streaming 响应，
    同时后台开启 TTS 工作流并直接在本地硬件播放声音。
    """
    token_queue = asyncio.Queue()
    
    # 启动后台 TTS 消费任务
    bg_task = asyncio.create_task(background_tts_worker(token_queue, request.tts_type))

    async def generate_and_feed():
        try:
            async for chunk in llm_engine.astream_chat(request.prompt):
                await token_queue.put(chunk)
                yield chunk
                logger.info(chunk)
        finally:
            # 推送结束信号给文本切分器
            await token_queue.put(None)
            
    return StreamingResponse(generate_and_feed(), media_type="text/plain")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)