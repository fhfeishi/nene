# app/components/llm/factory.py

import logging
from typing import Optional

from app.components.base import BaseLLM
from app.components.llm.component import LlamaCppLLM, VllmLLM, CloudLLM
from config.config import NeneSettings, settings

logger = logging.getLogger(__name__)


class LLMFactory:
    """LLM 统一工厂"""

    @staticmethod
    def create(config: Optional[NeneSettings] = None) -> BaseLLM:
        cfg = (config or settings).llm
        engine = cfg.infer_engine

        if engine == "llama-cpp":
            return LlamaCppLLM(config.llm if config else cfg)
        elif engine == "vllm":
            return VllmLLM(config.llm if config else cfg)
        elif engine == "cloud-api":
            return CloudLLM(config.llm if config else cfg)
        elif engine == "transformers":
            logger.warning("transformers engine not fully supported, falling back to llama-cpp")
            return LlamaCppLLM(config.llm if config else cfg)
        else:
            raise ValueError(f"Unsupported LLM infer_engine: {engine}")
