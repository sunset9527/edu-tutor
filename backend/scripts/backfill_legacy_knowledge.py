"""把 v1.7 之前的知识点幂等归入明确标记的 legacy 版本。

默认只预览；传入 ``--apply`` 才提交数据库变更。
"""

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.models.knowledge import KnowledgePoint, KnowledgePointLink  # noqa: E402
from app.models.knowledge_governance import KnowledgeVersion, Textbook  # noqa: E402


def _identity_key(subject: str, grade: str) -> str:
    digest = hashlib.sha256(f"{subject}\0{grade}".encode("utf-8")).hexdigest()
    return f"legacy:{digest}"


def _school_stage(grade: str) -> str | None:
    if grade.startswith(("一", "二", "三", "四", "五", "六")) and grade.endswith("年级"):
        return "小学"
    if grade.startswith("初"):
        return "初中"
    if grade.startswith("高"):
        return "高中"
    return None


def backfill_legacy_knowledge(
    db: Session, *, point_ids: list[int] | None = None
) -> dict[str, int]:
    query = db.query(KnowledgePoint).filter(KnowledgePoint.version_id.is_(None))
    if point_ids is not None:
        query = query.filter(KnowledgePoint.id.in_(point_ids))
    groups: dict[tuple[str, str], list[KnowledgePoint]] = defaultdict(list)
    for point in query.order_by(KnowledgePoint.id).all():
        groups[(point.subject or "未知", point.grade or "未知")].append(point)

    report = {"groups_created": 0, "versions_created": 0, "points_linked": 0}
    for (subject, grade), points in groups.items():
        identity_key = _identity_key(subject, grade)
        textbook = (
            db.query(Textbook).filter(Textbook.identity_key == identity_key).first()
        )
        if textbook is None:
            textbook = Textbook(
                identity_key=identity_key,
                school_stage=_school_stage(grade),
                grade=grade,
                subject=subject,
                source_kind="legacy",
                source_note="v1.7 前已有知识点回填；原始教材来源未知",
                license_note=None,
            )
            db.add(textbook)
            db.flush()
            report["groups_created"] += 1

        version = (
            db.query(KnowledgeVersion)
            .filter(
                KnowledgeVersion.textbook_id == textbook.id,
                KnowledgeVersion.version_no == 1,
            )
            .first()
        )
        if version is None:
            version = KnowledgeVersion(
                textbook_id=textbook.id,
                version_no=1,
                status="active",
            )
            db.add(version)
            db.flush()
            report["versions_created"] += 1

        textbook.active_version_id = version.id
        point_id_set = {point.id for point in points}
        for point in points:
            point.version_id = version.id
            point.source_chunk_id = None
            point.source_excerpt = None
            point.provenance_gap = True
            report["points_linked"] += 1
        db.flush()

        version.point_count = (
            db.query(KnowledgePoint)
            .filter(KnowledgePoint.version_id == version.id)
            .count()
        )
        version.edge_count = (
            db.query(KnowledgePointLink)
            .filter(KnowledgePointLink.source_kp_id.in_(point_id_set))
            .count()
            if point_id_set
            else 0
        )

    db.flush()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="回填 v1.7 legacy 知识版本")
    parser.add_argument("--apply", action="store_true", help="提交变更；默认只预览")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        report = backfill_legacy_knowledge(db)
        report["mode"] = "apply" if args.apply else "dry-run"
        if args.apply:
            db.commit()
        else:
            db.rollback()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"legacy 回填失败: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
