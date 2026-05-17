# app/components/vectordb/factory.py

import logging
from typing import Optional

from app.components.base import BaseVectorStore
from app.components.vectordb.chroma import ChromaVectorStore
from app.components.vectordb.milvus import MilvusVectorStore
from config.config import NeneSettings, settings

logger = logging.getLogger(__name__)


class VectorStoreFactory:
    """向量数据库统一工厂"""

    @staticmethod
    def create(config: Optional[NeneSettings] = None) -> BaseVectorStore:
        cfg = (config or settings).vector_db
        provider = cfg.provider

        if provider == "chroma":
            return ChromaVectorStore(config.vector_db if config else cfg)
        elif provider == "milvus":
            return MilvusVectorStore(config.vector_db if config else cfg)
        else:
            raise ValueError(f"Unsupported vector DB provider: {provider}")
