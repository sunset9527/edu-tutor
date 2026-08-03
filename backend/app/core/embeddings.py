"""Embedding 工厂：复用本机 BGE-M3 模型（HeritageMind 同款）"""
from functools import lru_cache

from langchain_huggingface import HuggingFaceEmbeddings

# 本地 BGE-M3 模型路径（1024 维，中文效果好）
EMBEDDING_MODEL_PATH = r"E:/huggingface/model"


@lru_cache(maxsize=1)
def get_embeddings() -> HuggingFaceEmbeddings:
    """加载 BGE-M3（CPU，首次加载约 20-40 秒，之后常驻）"""
    return HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL_PATH,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )


def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量文本向量化"""
    return get_embeddings().embed_documents(texts)


def embed_query(text: str) -> list[float]:
    """查询向量化（BGE 中文查询建议加 query 指令前缀）"""
    return get_embeddings().embed_query(text)
