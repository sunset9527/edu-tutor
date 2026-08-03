"""知识点图谱 API：图谱数据 / 统计 / 详情"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.knowledge import KnowledgePoint
from app.services.knowledge.graph_service import KnowledgeGraphService

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("/graph")
def knowledge_graph(subject: str | None = None):
    """图谱数据（前端 ECharts 可视化用）"""
    return KnowledgeGraphService().get_graph(subject)


@router.get("/stats")
def knowledge_stats(subject: str | None = None):
    """图谱统计：节点/边/连接率"""
    return KnowledgeGraphService().get_stats(subject)


@router.get("/{kp_id}")
def knowledge_detail(kp_id: int, db: Session = Depends(get_db)):
    """知识点详情"""
    kp = db.get(KnowledgePoint, kp_id)
    if not kp:
        raise HTTPException(status_code=404, detail="知识点不存在")
    return {
        "id": kp.id,
        "title": kp.title,
        "chapter": kp.chapter,
        "difficulty": kp.difficulty,
        "content_md": kp.content_md,
    }


@router.get("/path/{kp_id}")
def learning_path(kp_id: int, db: Session = Depends(get_db)):
    """个性化学习路径：目标知识点的前置知识链（v1.3）"""
    from app.services.knowledge.path_service import build_learning_path

    target = db.get(KnowledgePoint, kp_id)
    if not target:
        raise HTTPException(status_code=404, detail="知识点不存在")
    path = build_learning_path(db, kp_id)
    return {
        "target": {"id": target.id, "title": target.title, "subject": target.subject},
        "path": path,
    }

