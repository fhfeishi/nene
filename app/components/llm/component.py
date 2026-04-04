# app/components/llm/component.py

from typing import AsyncGenerator
from app.components.utils_model_load import get_huggingface_path, get_modelscope_path
from config.config import settings

import logging 
logger = logging.getLogger(__name__)

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