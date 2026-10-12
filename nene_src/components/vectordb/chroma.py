# app/components/vectordb/chroma.py

import asyncio
import logging
from typing import List, Dict, Any, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.components.base import BaseVectorStore, Document
from config.config import settings

logger = logging.getLogger(__name__)


class ChromaVectorStore(BaseVectorStore):
    """基于 Chroma 的向量数据库"""

    def __init__(self, config=None):
        super().__init__(config or settings.vector_db)
        self._client = None
        self._collection = None

    async def startup(self) -> None:
        cfg = self.config
        persist_dir = str(cfg.persist_directory or "./chroma_data")

        def _init():
            self._client = chromadb.PersistentClient(
                path=persist_dir,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            self._collection = self._client.get_or_create_collection(
                name=cfg.collection_name,
                metadata={"hnsw:space": "cosine"} if cfg.similarity == "cosine" else {},
            )

        await asyncio.to_thread(_init)
        self._ready = True
        logger.info("ChromaVectorStore ready (collection=%s).", cfg.collection_name)

    async def teardown(self) -> None:
        self._client = None
        self._collection = None
        self._ready = False

    async def add(
        self,
        documents: List[Document],
        embeddings: List[List[float]],
    ) -> List[str]:
        ids = [f"doc_{i}_{id(d)}" for i, d in enumerate(documents)]
        await asyncio.to_thread(
            lambda: self._collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=[d.content for d in documents],
                metadatas=[d.metadata for d in documents],
            )
        )
        return ids

    async def search(
        self,
        query_embedding: List[float],
        top_k: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Document]:
        k = top_k or self.config.top_k
        where = filters or self.config.metadata_filter

        def _query():
            return self._collection.query(
                query_embeddings=[query_embedding],
                n_results=k,
                where=where,
                include=["documents", "metadatas", "distances"],
            )

        result = await asyncio.to_thread(_query)
        docs = []
        if result["ids"] and result["ids"][0]:
            for i, doc_id in enumerate(result["ids"][0]):
                docs.append(Document(
                    content=result["documents"][0][i] or "",
                    metadata=result["metadatas"][0][i] or {},
                    score=1.0 - (result["distances"][0][i] or 0),
                ))
        return docs

    async def delete(self, ids: List[str]) -> None:
        await asyncio.to_thread(lambda: self._collection.delete(ids=ids))

    async def count(self) -> int:
        return await asyncio.to_thread(lambda: self._collection.count())
