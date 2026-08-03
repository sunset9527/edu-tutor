"""LLM 工厂：统一创建 DeepSeek ChatOpenAI 实例"""
from langchain_openai import ChatOpenAI

from app.core.config import settings


def create_llm(
    temperature: float = 0.7,
    streaming: bool = False,
    request_timeout: int = 60,
) -> ChatOpenAI:
    """创建 LLM 实例（DeepSeek，OpenAI 兼容协议）"""
    return ChatOpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        temperature=temperature,
        streaming=streaming,
        request_timeout=request_timeout,
        max_retries=2,
    )
