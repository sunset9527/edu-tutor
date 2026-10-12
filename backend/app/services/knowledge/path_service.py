"""学习路径生成（v1.3）：基于知识图谱前置关系，从目标知识点反推学习路径"""
from collections import deque

from sqlalchemy.orm import Session

from app.models.knowledge import KnowledgePoint, KnowledgePointLink
from app.models.knowledge import WrongQuestion
from app.models.memory import Memory, ReviewPlan


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


def build_personalized_learning_path(
    db: Session,
    student_id: int,
    target_kp_id: int,
    *,
    max_depth: int = 3,
    max_nodes: int = 15,
) -> dict:
    """根据图谱和学生真实学习证据生成可解释路径。"""
    from datetime import datetime

    target = db.get(KnowledgePoint, target_kp_id)
    if not target:
        return {"path": [], "evidence_gap": "目标知识点不存在"}

    links = (
        db.query(KnowledgePointLink)
        .filter(KnowledgePointLink.link_type == "prerequisite")
        .all()
    )
    prereq_ids: dict[int, list[int]] = {}
    for link in links:
        prereq_ids.setdefault(link.target_kp_id, []).append(link.source_kp_id)
    for values in prereq_ids.values():
        values.sort()

    ordered_ids: list[int] = []
    visited: set[int] = set()

    def visit(kp_id: int, depth: int) -> None:
        if kp_id in visited or len(ordered_ids) >= max_nodes:
            return
        visited.add(kp_id)
        if depth < max_depth:
            for prerequisite_id in prereq_ids.get(kp_id, []):
                visit(prerequisite_id, depth + 1)
        ordered_ids.append(kp_id)

    visit(target_kp_id, 0)
    prerequisite_set = set(ordered_ids) - {target_kp_id}
    if not prerequisite_set:
        evidence_gap = "知识图谱没有该目标的 prerequisite 关系，未推测前置知识"
    else:
        evidence_gap = None

    memories = (
        db.query(Memory)
        .filter(
            Memory.student_id == student_id,
            Memory.status == "active",
            Memory.knowledge_point_id.in_(ordered_ids),
        )
        .all()
    )
    mastery_by_kp: dict[int, str] = {}
    weak_kps: set[int] = set()
    memory_ids_by_kp: dict[int, list[int]] = {}
    for memory in memories:
        if memory.knowledge_point_id is None:
            continue
        memory_ids_by_kp.setdefault(memory.knowledge_point_id, []).append(memory.id)
        predicate = (memory.structured_data or {}).get("predicate")
        if predicate == "薄弱点":
            weak_kps.add(memory.knowledge_point_id)
        if predicate == "掌握状态" or memory.mastery != "不懂":
            mastery_by_kp[memory.knowledge_point_id] = memory.mastery

    wrong_rows = (
        db.query(WrongQuestion)
        .filter(
            WrongQuestion.student_id == student_id,
            WrongQuestion.mastered == 0,
            WrongQuestion.knowledge_point_id.in_(ordered_ids),
        )
        .all()
    )
    wrong_counts: dict[int, int] = {}
    for wrong in wrong_rows:
        wrong_counts[wrong.knowledge_point_id] = wrong_counts.get(wrong.knowledge_point_id, 0) + 1

    now = datetime.now()
    due_rows = (
        db.query(ReviewPlan)
        .filter(
            ReviewPlan.student_id == student_id,
            ReviewPlan.target_type == "knowledge_point",
            ReviewPlan.target_id.in_(ordered_ids),
            ReviewPlan.status == "pending",
            ReviewPlan.next_review_at <= now,
        )
        .all()
    )
    due_ids = {plan.target_id for plan in due_rows}

    path: list[dict] = []
    for kp_id in ordered_ids:
        kp = db.get(KnowledgePoint, kp_id)
        if not kp:
            continue
        mastery = mastery_by_kp.get(kp_id, "不懂")
        wrong_count = wrong_counts.get(kp_id, 0)
        review_due = kp_id in due_ids
        weak = kp_id in weak_kps
        is_target = kp_id == target_kp_id
        mastered_and_clear = (
            mastery in {"熟练", "精通"}
            and wrong_count == 0
            and not review_due
            and not weak
        )
        if not is_target and mastered_and_clear:
            continue

        reasons = []
        if is_target:
            reasons.append("当前学习目标")
        else:
            reasons.append("知识图谱中的前置知识")
        if weak:
            reasons.append("学生薄弱点记忆命中")
        if wrong_count:
            reasons.append(f"存在 {wrong_count} 道未掌握错题")
        if review_due:
            reasons.append("知识点复习任务已到期")
        if not is_target and mastery in {"不懂", "基本会"}:
            reasons.append(f"当前掌握度为{mastery}")

        path.append(
            {
                "id": kp.id,
                "title": kp.title,
                "difficulty": kp.difficulty,
                "subject": kp.subject,
                "grade": kp.grade,
                "is_target": is_target,
                "mastery": mastery,
                "wrong_count": wrong_count,
                "review_due": review_due,
                "reasons": reasons,
                "evidence": {
                    "memory_ids": memory_ids_by_kp.get(kp_id, []),
                    "wrong_question_ids": [
                        row.id for row in wrong_rows if row.knowledge_point_id == kp_id
                    ],
                    "review_plan_ids": [row.id for row in due_rows if row.target_id == kp_id],
                },
            }
        )

    return {"path": path, "evidence_gap": evidence_gap}
