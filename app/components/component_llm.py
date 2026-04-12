# app/components/component_llm.py 

import os 
import time 
import asyncio 
import subprocess
import atexit
import urllib.request
import urllib.error
from openai import AsyncOpenAI

from config.config import settings

import logging 
logger = logging.getLogger(__name__)


# --cpu_build-llamacpp
class LlamaCppServerLLMcpu:
    """基于 llama-server 的本地 LLM 独立进程"""
    def __init__(self, settings=settings):
        
        self.cfg = settings.llm 
        
        self.server_process = None
        self.client = None
        self.startup()
        self.teardown()

    def startup(self):
        command = [
            self.cfg.llamacpp_bin,
            "-m", self.cfg.llamacpp_gguffile,
            "-c", str(self.cfg.llamacpp_ctx),
            "--port", str(self.cfg.llamacpp_port),
            # 强制指定 Qwen 的专属模板，防止出现上下文截断或无限循环生成的 Bug
            "--chat-template", "chatml"
        ]
        logger.info(f"Starting local llama-server on port {self.cfg.llamacpp_port}...")
        
        # 无 llamacpp 日志
        self.server_process = subprocess.Popen(
            command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        # # 有 llamacpp 日志
        # self.server_process = subprocess.Popen(command)
        
        # 注册退出回调，防止 Python 崩溃时留下僵尸 C++ 进程
        atexit.register(self._cleanup_process)
        # 阻塞等待模型加载进内存
        self._wait_for_health()

    def _wait_for_health(self, timeout: int = 120):
        """健康检查轮询，等待 llama.cpp 的 HTTP 服务就绪"""
        health_url = f"http://localhost:{settings.llm_port}/health"
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                urllib.request.urlopen(health_url)
                logger.info(f"LLM {self.cfg.llamacpp_gguffile.rsplit(os.sep, 1)[1]} Server is ready!")
                return
            except (urllib.error.URLError, ConnectionResetError):
                time.sleep(1)# 没准备好就等 1 秒再问
        self._cleanup_process()
        raise TimeoutError("llama-server failed to start.")

    def _init_client(self):
        """初始化官方的 AsyncOpenAI 客户端，将其指向我们的本地端口"""
        self.client = AsyncOpenAI(
            base_url=f"http://localhost:{settings.llm_port}/v1",
            api_key="sk-local"
        )

    def teardown(self):
        if self.server_process and self.server_process.poll() is None:
            logger.info("Terminating llama-server...")
            self.server_process.terminate()
            self.server_process.wait()

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








if __name__ =="__main__":
    
    
    llm_engine = LlamaCppServerLLMcpu()
