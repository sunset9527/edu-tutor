"""ChromaDB 客户端工厂（记忆向量库）"""
from functools import lru_cache

import chromadb

from app.core.config import settings


@lru_cache(maxsize=1)
def get_chroma_client() -> chromadb.PersistentClient:
    return chromadb.PersistentClient(path=settings.chroma_dir)


@lru_cache(maxsize=1)
def get_memory_collection():
    """记忆向量集合：自己算 embedding 后传入，不用 chromadb 内置 embedding"""
    return get_chroma_client().get_or_create_collection(
        name="memory_vectors",
        metadata={"hnsw:space": "cosine"},
    )
