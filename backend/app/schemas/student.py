"""学生相关 schema"""
from pydantic import BaseModel, ConfigDict, Field


class StudentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    grade: str = Field(min_length=1, max_length=20, description="年级：初一/初二/初三…")
    subject: str = Field(default="数学", max_length=20)
    level: str = Field(default="基础", max_length=20, description="入门/基础/中等/进阶")
    prefer_style: str | None = Field(default=None, max_length=200)


class StudentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    grade: str
    subject: str
    level: str
    prefer_style: str | None = None
    user_id: int | None = None
