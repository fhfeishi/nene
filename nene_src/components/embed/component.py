# app/components/embed/component.py

import asyncio
import logging
from typing import List

from app.components.base import BaseEmbed
from app.components.utils import resolve_model_path
from config.config import settings

logger = logging.getLogger(__name__)


class SentenceTransformerEmbed(BaseEmbed):
    """基于 sentence-transformers 的本地 Embedding 模型"""

    def __init__(self, config=None):
        super().__init__(config or settings.embed)
        self._embedder = None

    async def startup(self) -> None:
        from sentence_transformers import SentenceTransformer

        cfg = self.config
        model_path = resolve_model_path(cfg.model_id, cfg.hub_backend)
        device = getattr(cfg, "device", "cpu")

        def _load():
            self._embedder = SentenceTransformer(model_path, device=device)

        await asyncio.to_thread(_load)
        self._ready = True
        logger.info("SentenceTransformerEmbed ready (model=%s).", model_path)

    async def teardown(self) -> None:
        del self._embedder
        self._embedder = None
        self._ready = False

    async def embed(self, texts: List[str]) -> List[List[float]]:
        def _encode():
            return self._embedder.encode(
                texts,
                normalize_embeddings=True,
                show_progress_bar=False,
            ).tolist()

        return await asyncio.to_thread(_encode)


class CloudEmbed(BaseEmbed):
    """云端 Embedding API (OpenAI 兼容协议)"""

    def __init__(self, config=None):
        super().__init__(config or settings.embed)
        self.client = None

    async def startup(self) -> None:
        from openai import AsyncOpenAI

        cfg = self.config
        self.client = AsyncOpenAI(
            api_key=cfg.api_key or "sk-placeholder",
            base_url=cfg.base_url,
        )
        self._ready = True
        logger.info("CloudEmbed ready.")

    async def teardown(self) -> None:
        self.client = None
        self._ready = False

    async def embed(self, texts: List[str]) -> List[List[float]]:
        response = await self.client.embeddings.create(
            model=self.config.model_id,
            input=texts,
        )
        return [d.embedding for d in response.data]
