"""对话相关 schema"""
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    student_id: int
    session_id: int | None = Field(default=None, description="不传则自动创建新会话")
    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    session_id: int
    response: str
