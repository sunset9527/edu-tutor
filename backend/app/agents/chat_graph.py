"""LangGraph 对话工作流（v0.2：接入记忆引擎）

流程：load_history → retrieve_memory → generate → save_messages → extract_memory → END

- load_history：短期记忆（会话内上下文）
- retrieve_memory：长期记忆多路召回（画像 + 向量 + 最近事件），注入 System Prompt
- generate：LLM 生成回复
- save_messages：消息落库
- extract_memory：对话后 LLM 提取长期记忆 → MySQL + Chroma 双写（v0.2 新增）
"""
from functools import lru_cache
from typing import TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.llm import create_llm
from app.models.session import Message

# 辅导老师角色（基础版；v0.2 起会动态拼接记忆上下文）
SYSTEM_PROMPT = (
    "你是一名耐心的初中数学辅导老师。"
    "请用清晰、循序渐进的方式讲解，多举具体例子。"
    "讲解完主动询问学生是否理解，引导他自己说出思路。"
)


class ChatState(TypedDict):
    """对话流状态"""
    student_id: int
    session_id: int
    user_message: str
    history: list  # list[BaseMessage]
    memory_context: str  # 记忆注入文本
    ai_response: str


def _load_recent_messages(session_id: int) -> list:
    """读取最近 N 轮消息（工作记忆窗口）"""
    db = SessionLocal()
    try:
        rows = (
            db.query(Message)
            .filter(Message.session_id == session_id)
            .order_by(Message.id.desc())
            .limit(settings.working_memory_window_size * 2)
            .all()
        )
        history: list = []
        for m in reversed(rows):  # 恢复时间正序
            if m.role == "user":
                history.append(HumanMessage(content=m.content))
            elif m.role == "assistant":
                history.append(AIMessage(content=m.content))
        return history
    finally:
        db.close()


def load_history_node(state: ChatState) -> ChatState:
    """节点 1：加载会话历史（短期记忆）"""
    return {"history": _load_recent_messages(state["session_id"])}


def retrieve_memory_node(state: ChatState) -> ChatState:
    """节点 2：长期记忆多路召回，组装注入文本"""
    from app.services.memory.retriever import MemoryRetriever

    retriever = MemoryRetriever()
    result = retriever.retrieve(state["student_id"], state["user_message"])
    injection = retriever.build_injection_text(result)
    return {"memory_context": injection}


def generate_node(state: ChatState) -> ChatState:
    """节点 3：LLM 生成回复（注入长期记忆上下文）"""
    llm = create_llm()
    system = SYSTEM_PROMPT
    if state.get("memory_context"):
        system = SYSTEM_PROMPT + "\n\n以下是这个学生的长期记忆，请充分利用它提供个性化辅导：\n" + state["memory_context"]

    messages = (
        [SystemMessage(content=system)]
        + state["history"]
        + [HumanMessage(content=state["user_message"])]
    )
    response = llm.invoke(messages)
    return {"ai_response": response.content}


def save_messages_node(state: ChatState) -> ChatState:
    """节点 4：用户消息 + AI 回复落库（短期记忆持久化）"""
    db = SessionLocal()
    try:
        db.add(
            Message(session_id=state["session_id"], role="user", content=state["user_message"])
        )
        db.add(
            Message(
                session_id=state["session_id"],
                role="assistant",
                content=state["ai_response"],
            )
        )
        db.commit()
    finally:
        db.close()
    return {}


def extract_memory_node(state: ChatState) -> ChatState:
    """节点 5：对话后提取长期记忆并双写存储（v0.2 核心）"""
    from app.services.memory.extractor import MemoryExtractor
    from app.services.memory.retriever import MemoryRetriever
    from app.services.memory.storage import MemoryStorage

    try:
        # 传入画像摘要，避免重复提取已有信息
        profile_summary = MemoryRetriever().retrieve(
            state["student_id"], state["user_message"]
        )["profile_summary"]

        extractor = MemoryExtractor()
        items = extractor.extract(
            user_message=state["user_message"],
            ai_response=state["ai_response"],
            profile_summary=profile_summary,
        )
        if items:
            MemoryStorage().write(
                student_id=state["student_id"],
                session_id=state["session_id"],
                items=items,
            )
    except Exception as e:  # noqa: BLE001
        # 记忆提取失败不应阻断对话主流程
        import logging

        logging.getLogger(__name__).warning(f"记忆提取/写入失败: {e}")
    return {}


@lru_cache(maxsize=1)
def build_chat_graph():
    """构建并编译 LangGraph 工作流（开发期用内存 checkpointer）"""
    graph = StateGraph(ChatState)
    graph.add_node("load_history", load_history_node)
    graph.add_node("retrieve_memory", retrieve_memory_node)
    graph.add_node("generate", generate_node)
    graph.add_node("save_messages", save_messages_node)
    graph.add_node("extract_memory", extract_memory_node)
    graph.add_edge(START, "load_history")
    graph.add_edge("load_history", "retrieve_memory")
    graph.add_edge("retrieve_memory", "generate")
    graph.add_edge("generate", "save_messages")
    graph.add_edge("save_messages", "extract_memory")
    graph.add_edge("extract_memory", END)
    return graph.compile(checkpointer=MemorySaver())


def run_chat(student_id: int, session_id: int, user_message: str) -> str:
    """执行对话，返回 AI 回复"""
    result = build_chat_graph().invoke(
        {
            "student_id": student_id,
            "session_id": session_id,
            "user_message": user_message,
        },
        config={"configurable": {"thread_id": str(session_id)}},
    )
    return result["ai_response"]
