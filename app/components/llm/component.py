# app/components/llm/component.py

import atexit
import subprocess
import time
from typing import AsyncGenerator
import urllib
from app.components.utils_model_load import get_huggingface_path, get_modelscope_path
from config.config import settings
from openai import AsyncOpenAI 
import uuid 

import logging 
logger = logging.getLogger(__name__)


# base LLM class 



class QwenLLM:
    """ qwen llm class """
    
    def __init__(self, cfg: settings):
        logger.info(f"Initializing QwenLLM with engine: {cfg.llm.infer_engine}")        
        
        self.cfg = cfg.llm
        self.model_path = None
        self.client = None 
        self.model = None
    
    def _resolve_model_path(self):
        """ 解析并获取本地模型路径 """
        if self.hub_backend == "modelscope":
            logger.info(f"Loading model from modelscope")
            try:
                self.model_path = get_modelscope_path(self.model_id)
            except:
                self.model_path = get_modelscope_path(self.model_id, mode="local")
        elif self.hub_backend == "huggingface":
            logger.info(f"Loading model from huggingface")
            try:
                self.model_path = get_huggingface_path(self.model_id)
            except:
                self.model_path = get_huggingface_path(self.model_id, mode="local")
        else:
            self.model_path = self.cfg.model_id
        logger.info(f"Loading model from: {self.model_path}")

    def _init_engine(self):
        """ 根据配置实例化具体的推理后端 """
        engine = self.cfg.infer_engine

        if engine == "cloud-api":
            from openai import AsyncOpenAI
            self.client = AsyncOpenAI(
                api_key=self.cfg.api_key,
                base_url=self.cfg.base_url
            )
            logger.info("Cloud API Engine initialized.")
            
        elif engine == "llama-cpp":
            from llama_cpp import Llama
            n_gpu = -1 if self.cfg.device in ["cuda", "auto"] else 0
            # 这里的 Llama 本身是同步的，后续可以通过 asyncio.to_thread 包装成异步
            self.model = Llama(
                model_path=self.model_path,
                n_gpu_layers=n_gpu,
                verbose=False
            )
            logger.info("llama.cpp Engine initialized.")
    
        elif engine == "transformers":
            from transformers import AutoModelForCausalLM, AutoTokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_path)
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_path, 
                device_map=self.cfg.device
            )
            logger.info("Transformers Engine initialized.")
            
            
        else:
            raise ValueError(f"Unsupported engine: {engine}")            


    async def astream_chat(self, prompt: str) -> AsyncGenerator[str, None]:
        """ 
        核心异步流式接口：接收 prompt，返回异步生成器。
        这对于接下来的 TTS 组件边听边读至关重要。
        """
        engine = self.cfg.infer_engine
        
        if engine == "cloud-api":
            response = await self.client.chat.completions.create(
                model=self.cfg.model_id,
                messages=[{"role": "user", "content": prompt}],
                stream=True
            )
            async for chunk in response:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        
        elif engine == "llama-cpp":
            import asyncio
            # llama_cpp-python 目前主要是同步库，需要借助线程池实现不阻塞
            def generate_sync():
                return self.model.create_chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    stream=True
                )
            
            stream_generator = await asyncio.to_thread(generate_sync)
            for chunk in stream_generator:
                if "content" in chunk["choices"][0]["delta"]:
                    # 为了模拟异步行为，交出控制权
                    await asyncio.sleep(0) 
                    yield chunk["choices"][0]["delta"]["content"]
                    
                    
        elif engine == "transformers":
            # transformers 的流式输出需要用到 TextIteratorStreamer，此处略作简化
            # 实际部署时，vllm 或 llama-cpp 才是 RAG 流式更好的选择
            yield "Transformers 流式输出需要配合 TextIteratorStreamer 较为复杂，建议优先使用 vllm/llama-cpp 或 Cloud API。"
            
            
# llama cpp [cpu] 集成
class LlamaCppServerLLMcpu:
    """ 
    基于 llama-server.exe 的本地独立进程 LLM 类
    通过子进程启动模型，并通过兼容 OpenAI 的本地 API 进行交互
    """                
    def __init__(self, gguf_file: str, port: int=8080, ctx_size:int=4096):
        self.gguf_file = gguf_file 
        self.port = port 
        self.ctx_size = ctx_size 
        self.server_process = None 
        self.client = None 
        
        # 1. 启动本地服务
        self._start_server()
        
        # 2. 初始化异步客户端
        self._init_client()
        
        
        def _start_server(self):
            """ 在后台运行 llama-server """
            command = [
                "llama-server.exe", # 如果在 Linux/Mac 下，改为 "./llama-server"
                "-m", self.gguf_file,
                "-c", str(self.ctx_size),
                "--port", str(self.port)
            ]
            
            logger.info(f"Starting local llama-server on port {self.port}...")
        
            # 启动子进程，将输出重定向以避免污染主程序的控制台日志
            # 如果需要调试模型加载过程，可以去掉 stdout 和 stderr 参数
            self.server_process = subprocess.Popen(
                command, 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL
            )
            
            # 注册清理函数，防止主进程意外退出时留下僵尸进程
            atexit.register(self._cleanup_process)
            
            # 等待服务器就绪
            self._wait_for_health()

        def _wait_for_health(self, timeout: int = 120):
            """ 阻塞等待服务器加载模型完毕 """
            health_url = f"http://localhost:{self.port}/health"
            start_time = time.time()
            
            logger.info("Waiting for model to load into memory...")
            while time.time() - start_time < timeout:
                try:
                    # 尝试访问健康检查接口
                    urllib.request.urlopen(health_url)
                    logger.info("Model loaded successfully. Server is ready!")
                    return
                except (urllib.error.URLError, ConnectionResetError):
                    time.sleep(2)  # 每 2 秒探测一次
                    
            # 如果超时仍未启动
            self._cleanup_process()
            raise TimeoutError(f"llama-server failed to start within {timeout} seconds.")

        def _init_client(self):
            """ 初始化 AsyncOpenAI 客户端，指向本地端口 """
            self.client = AsyncOpenAI(
                base_url=f"http://localhost:{self.port}/v1",
                api_key="sk-local-llama-cpp" # 本地服务不需要真实 API Key
            )

        def _cleanup_process(self):
            """ 安全关闭子进程 """
            if self.server_process and self.server_process.poll() is None:
                logger.info("Terminating local llama-server process...")
                self.server_process.terminate()
                self.server_process.wait()
                logger.info("llama-server terminated.")

        def __del__(self):
            """ 对象被销毁时，确保清理进程 """
            self._cleanup_process()

        async def astream_chat(self, prompt: str) -> AsyncGenerator[str, None]:
            """ 
            核心异步流式接口：接收 prompt，返回异步生成器。
            复用 OpenAI 的标准调用逻辑。
            """
            if not self.client:
                raise RuntimeError("Client is not initialized.")
                
            try:
                response = await self.client.chat.completions.create(
                    model="local-model", # 这里填什么都可以，llama-server 会忽略
                    messages=[{"role": "user", "content": prompt}],
                    stream=True,
                    temperature=0.7
                )
                
                async for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                        
            except Exception as e:
                logger.error(f"Error during streaming chat: {e}")
                yield f"\n[Error: {str(e)}]"
            
        
# vllm [gpu] 集成
class VllmLLMgpu:
    """ 
    基于 vLLM AsyncLLMEngine 的 GPU 原生加速 LLM 类 
    提供极高的并发吞吐量和纯异步的流式生成体验
    """
    
    def __init__(self, model_path: str, cfg: settings.llm = None):
        self.model_path = model_path
        self.cfg = cfg
        self.engine = None
        self.tokenizer = None
        
        self._init_engine()

    def _init_engine(self):
        """ 初始化 vLLM 异步引擎 """
        logger.info(f"Initializing vLLM AsyncEngine with model: {self.model_path}")
        
        try:
            from vllm import AsyncEngineArgs, AsyncLLMEngine
        except ImportError:
            raise ImportError("Please install vllm first: pip install vllm")

        # 配置引擎参数
        # 这里的参数在生产环境中非常关键，可以按需暴露到 settings 中
        engine_args = AsyncEngineArgs(
            model=self.model_path,
            trust_remote_code=True,
            
            # 显存利用率 (默认 0.9，如果你的 GPU 还要跑其他模型如 TTS，建议调小到 0.5-0.7)
            gpu_memory_utilization=getattr(self.cfg, "gpu_memory_utilization", 0.85),
            
            # 最大上下文长度 (如果不设置，vllm 会默认读取 config.json，有时会导致 OOM)
            max_model_len=getattr(self.cfg, "max_model_len", 4096),
            
            # 如果有多张显卡，可以设置张量并行度
            tensor_parallel_size=getattr(self.cfg, "tensor_parallel_size", 1),
            
            # 禁用不必要的日志以保持控制台干净
            disable_log_requests=True 
        )
        
        # 实例化引擎
        self.engine = AsyncLLMEngine.from_engine_args(engine_args)
        
        # 获取 tokenizer (为了处理 Chat Template)
        # vLLM 的 AsyncLLMEngine 内部也包含了 tokenizer，这里显式获取方便后续处理
        from transformers import AutoTokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_path, trust_remote_code=True)
        logger.info("vLLM AsyncEngine initialized successfully.")


    async def astream_chat(self, prompt: str) -> AsyncGenerator[str, None]:
        """ 
        核心异步流式接口
        注意：vLLM 默认返回的是完整的、累加的文本，为了适配 TTS 的边听边读，必须手动提取 Delta
        """
        if not self.engine:
            raise RuntimeError("vLLM Engine is not initialized.")

        from vllm import SamplingParams

        # 1. 设置采样参数 (温度、Top-P、最大生成 token 数等)
        sampling_params = SamplingParams(
            temperature=0.7,
            top_p=0.9,
            max_tokens=2048,
            # 可以添加停止词 stop=["<|im_end|>", "User:"]
        )

        # 2. 应用 Chat Template 格式化 Prompt (非常重要，否则模型容易胡言乱语)
        # 将简单的字符串包装成对话列表，然后应用模板
        messages = [{"role": "user", "content": prompt}]
        formatted_prompt = self.tokenizer.apply_chat_template(
            messages, 
            tokenize=False, 
            add_generation_prompt=True
        )

        # 3. 生成唯一的请求 ID
        request_id = uuid.uuid4().hex

        # 4. 调用异步生成器
        results_generator = self.engine.generate(
            prompt=formatted_prompt, 
            sampling_params=sampling_params, 
            request_id=request_id
        )

        # 5. Delta 提取逻辑：因为 vLLM 每次 yield 出的是从头开始的完整字符串
        previous_text_len = 0
        
        try:
            async for request_output in results_generator:
                # 获取最新生成的完整文本
                text = request_output.outputs[0].text
                
                # 切片获取增量部分 (Delta)
                delta_text = text[previous_text_len:]
                
                if delta_text:
                    yield delta_text
                    previous_text_len = len(text)
                    
        except Exception as e:
            logger.error(f"Error during vLLM streaming: {e}")
            yield f"\n[Generation Error: {str(e)}]"


