"""FastAPI 应用入口"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import auth, chat, knowledge, memories, students
from app.core.database import engine

app = FastAPI(
    title="EduTutor API",
    description="基于 LangChain 的智能体记忆增强系统——个性化教育辅导",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(students.router)
app.include_router(chat.router)
app.include_router(memories.router)
app.include_router(knowledge.router)


@app.get("/health")
def health():
    """健康检查：API + MySQL 连通性"""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        mysql_status = "ok"
    except Exception:
        mysql_status = "error"
    return {"status": "ok", "mysql": mysql_status}
