"""知识引擎：知识点向量集合（用于记忆关联 + 图谱语义搜索）"""
from functools import lru_cache

from app.core.config import settings
from app.services.memory.chroma_client import get_chroma_client


@lru_cache(maxsize=1)
def get_knowledge_collection():
    return get_chroma_client().get_or_create_collection(
        name="knowledge_vectors",
        metadata={"hnsw:space": "cosine"},
    )
