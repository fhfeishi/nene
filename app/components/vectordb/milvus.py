# app/components/vectordb/milvus.py

import asyncio
import logging
from typing import List, Dict, Any, Optional

from pymilvus import (
    connections,
    Collection,
    CollectionSchema,
    FieldSchema,
    DataType,
    utility,
)

from app.components.base import BaseVectorStore, Document
from config.config import settings

logger = logging.getLogger(__name__)


class MilvusVectorStore(BaseVectorStore):
    """基于 Milvus 的向量数据库"""

    def __init__(self, config=None):
        super().__init__(config or settings.vector_db)
        self._collection = None
        self._dim = None

    async def startup(self) -> None:
        cfg = self.config
        alias = "default"

        def _init():
            connections.connect(
                alias=alias,
                host=cfg.host,
                port=cfg.port,
            )
            if utility.has_collection(cfg.collection_name):
                self._collection = Collection(cfg.collection_name)
                self._collection.load()
            else:
                # Create collection with required schema
                fields = [
                    FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=100),
                    FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=1024),
                    FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
                    FieldSchema(name="metadata", dtype=DataType.JSON),
                ]
                schema = CollectionSchema(fields, description="nene collection")
                self._collection = Collection(cfg.collection_name, schema)
                index_params = {"metric_type": "COSINE", "index_type": "IVF_FLAT", "params": {"nlist": 128}}
                self._collection.create_index("embedding", index_params)
                self._collection.load()

        await asyncio.to_thread(_init)
        self._ready = True
        logger.info("MilvusVectorStore ready (collection=%s).", cfg.collection_name)

    async def teardown(self) -> None:
        if self._collection:
            await asyncio.to_thread(self._collection.release)
        connections.disconnect("default")
        self._collection = None
        self._ready = False

    async def add(
        self,
        documents: List[Document],
        embeddings: List[List[float]],
    ) -> List[str]:
        ids = [f"doc_{i}_{id(d)}" for i, d in enumerate(documents)]
        entities = [
            ids,
            embeddings,
            [d.content for d in documents],
            [d.metadata for d in documents],
        ]

        def _insert():
            self._collection.insert(entities)
            self._collection.flush()

        await asyncio.to_thread(_insert)
        return ids

    async def search(
        self,
        query_embedding: List[float],
        top_k: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Document]:
        k = top_k or self.config.top_k
        search_params = {"metric_type": "COSINE", "params": {"nprobe": 10}}

        def _search():
            self._collection.load()
            return self._collection.search(
                data=[query_embedding],
                anns_field="embedding",
                param=search_params,
                limit=k,
                output_fields=["content", "metadata"],
            )

        results = await asyncio.to_thread(_search)
        docs = []
        for hits in results:
            for hit in hits:
                docs.append(Document(
                    content=hit.entity.get("content", ""),
                    metadata=hit.entity.get("metadata", {}),
                    score=hit.score,
                ))
        return docs

    async def delete(self, ids: List[str]) -> None:
        await asyncio.to_thread(lambda: self._collection.delete(f"id in {ids}"))

    async def count(self) -> int:
        return await asyncio.to_thread(lambda: self._collection.num_entities)
