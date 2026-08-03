"""学习路径生成（v1.3）：基于知识图谱前置关系，从目标知识点反推学习路径"""
from collections import deque

from sqlalchemy.orm import Session

from app.models.knowledge import KnowledgePoint, KnowledgePointLink


def build_learning_path(
    db: Session,
    target_kp_id: int,
    max_depth: int = 3,
    max_nodes: int = 15,
) -> list[dict]:
    """从 target 出发，BFS 沿 prerequisite 反边收集前置知识链

    返回有序列表（最底层前置 → ... → 直接前置 → target）
    """
    target = db.get(KnowledgePoint, target_kp_id)
    if not target:
        return []

    # 反向边索引：kp_id -> [前置知识点]（link: source->target, prerequisite）
    prereq_map: dict[int, list[KnowledgePoint]] = {}
    links = (
        db.query(KnowledgePointLink)
        .filter(KnowledgePointLink.link_type == "prerequisite")
        .all()
    )
    for link in links:
        prereq_map.setdefault(link.target_kp_id, []).append(db.get(KnowledgePoint, link.source_kp_id))

    # BFS（从 target 往上游）
    visited: dict[int, int] = {target.id: 0}  # kp_id -> depth
    queue = deque([target])
    chain: list[KnowledgePoint] = []

    while queue and len(chain) < max_nodes:
        node = queue.popleft()
        chain.append(node)
        depth = visited[node.id]
        if depth >= max_depth:
            continue
        for pre in prereq_map.get(node.id, []):
            if pre and pre.id not in visited:
                visited[pre.id] = depth + 1
                queue.append(pre)

    # 倒序：最底层前置在前，target 在最后
    ordered = list(reversed(chain))
    return [
        {
            "id": kp.id,
            "title": kp.title,
            "difficulty": kp.difficulty,
            "subject": kp.subject,
            "grade": kp.grade,
            "is_target": kp.id == target.id,
        }
        for kp in ordered
    ]
