# app/components/llm/component.py

import asyncio
import atexit
import subprocess
import time
import urllib.request
import urllib.error
import uuid
from typing import AsyncGenerator, List, Dict, Any

from app.components.base import BaseLLM
from app.components.utils import resolve_model_path
from config.config import settings

import logging

logger = logging.getLogger(__name__)


class LlamaCppLLM(BaseLLM):
    """基于 llama-server 子进程的本地 LLM，通过 OpenAI 兼容 API 交互"""

    def __init__(self, config=None):
        super().__init__(config or settings.llm)
        self.server_process = None
        self.client = None
        self._startup_called = False

    async def startup(self) -> None:
        from openai import AsyncOpenAI

        cfg = self.config
        command = [
            cfg.llamacpp_bin,
            "-m", cfg.llamacpp_gguffile,
            "-c", str(cfg.llamacpp_ctx),
            "--port", str(cfg.llamacpp_port),
            "--chat-template", "chatml",
        ]
        logger.info("Starting llama-server on port %s...", cfg.llamacpp_port)
        self.server_process = subprocess.Popen(
            command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        atexit.register(self._cleanup_process)
        await asyncio.to_thread(self._wait_for_health)

        self.client = AsyncOpenAI(
            base_url=f"http://localhost:{cfg.llamacpp_port}/v1",
            api_key="sk-local",
        )
        self._ready = True
        self._startup_called = True
        logger.info("LlamaCppLLM ready.")

    def _wait_for_health(self, timeout: int = 120) -> None:
        cfg = self.config
        health_url = f"http://localhost:{cfg.llamacpp_port}/health"
        start = time.time()
        while time.time() - start < timeout:
            try:
                urllib.request.urlopen(health_url)
                logger.info("llama-server health check passed.")
                return
            except (urllib.error.URLError, ConnectionResetError):
                time.sleep(1)
        self._cleanup_process()
        raise TimeoutError("llama-server failed to start.")

    def _cleanup_process(self) -> None:
        if self.server_process and self.server_process.poll() is None:
            logger.info("Terminating llama-server...")
            self.server_process.terminate()
            self.server_process.wait()

    async def teardown(self) -> None:
        self._cleanup_process()
        self.client = None
        self._ready = False
        self._startup_called = False

    async def chat(self, messages: List[Dict[str, str]], **kwargs: Any) -> str:
        response = await self.client.chat.completions.create(
            model="local",
            messages=messages,
            stream=False,
            temperature=kwargs.get("temperature", 0.7),
        )
        return response.choices[0].message.content or ""

    async def chat_stream(self, messages: List[Dict[str, str]], **kwargs: Any) -> AsyncGenerator[str, None]:
        response = await self.client.chat.completions.create(
            model="local",
            messages=messages,
            stream=True,
            temperature=kwargs.get("temperature", 0.7),
        )
        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


class VllmLLM(BaseLLM):
    """基于 vLLM AsyncLLMEngine 的 GPU 加速 LLM"""

    def __init__(self, config=None):
        super().__init__(config or settings.llm)
        self.engine = None
        self.tokenizer = None

    async def startup(self) -> None:
        from vllm import AsyncEngineArgs, AsyncLLMEngine
        from transformers import AutoTokenizer

        cfg = self.config
        model_path = resolve_model_path(cfg.model_id, cfg.hub_backend)

        engine_args = AsyncEngineArgs(
            model=model_path,
            trust_remote_code=True,
            gpu_memory_utilization=getattr(cfg, "gpu_memory_utilization", 0.85),
            max_model_len=getattr(cfg, "max_model_len", 4096),
            tensor_parallel_size=getattr(cfg, "tensor_parallel_size", 1),
            disable_log_requests=True,
        )
        self.engine = AsyncLLMEngine.from_engine_args(engine_args)
        self.tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        self._ready = True
        logger.info("VllmLLM ready.")

    async def teardown(self) -> None:
        self.engine = None
        self.tokenizer = None
        self._ready = False

    async def chat(self, messages: List[Dict[str, str]], **kwargs: Any) -> str:
        chunks = []
        async for chunk in self.chat_stream(messages, **kwargs):
            chunks.append(chunk)
        return "".join(chunks)

    async def chat_stream(self, messages: List[Dict[str, str]], **kwargs: Any) -> AsyncGenerator[str, None]:
        from vllm import SamplingParams

        formatted = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        sampling_params = SamplingParams(
            temperature=kwargs.get("temperature", 0.7),
            top_p=kwargs.get("top_p", 0.9),
            max_tokens=kwargs.get("max_tokens", 2048),
        )
        request_id = uuid.uuid4().hex
        results = self.engine.generate(formatted, sampling_params, request_id=request_id)

        prev_len = 0
        async for output in results:
            text = output.outputs[0].text
            delta = text[prev_len:]
            if delta:
                yield delta
                prev_len = len(text)


class CloudLLM(BaseLLM):
    """云端 LLM API (OpenAI 兼容协议)"""

    def __init__(self, config=None):
        super().__init__(config or settings.llm)
        self.client = None

    async def startup(self) -> None:
        from openai import AsyncOpenAI

        cfg = self.config
        self.client = AsyncOpenAI(
            api_key=cfg.cloud_apikey or "sk-placeholder",
            base_url=cfg.cloud_url,
        )
        self._ready = True
        logger.info("CloudLLM ready.")

    async def teardown(self) -> None:
        self.client = None
        self._ready = False

    async def chat(self, messages: List[Dict[str, str]], **kwargs: Any) -> str:
        response = await self.client.chat.completions.create(
            model=self.config.model_id,
            messages=messages,
            stream=False,
            temperature=kwargs.get("temperature", 0.7),
        )
        return response.choices[0].message.content or ""

    async def chat_stream(self, messages: List[Dict[str, str]], **kwargs: Any) -> AsyncGenerator[str, None]:
        response = await self.client.chat.completions.create(
            model=self.config.model_id,
            messages=messages,
            stream=True,
            temperature=kwargs.get("temperature", 0.7),
        )
        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
