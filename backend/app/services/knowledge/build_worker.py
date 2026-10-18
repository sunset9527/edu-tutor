"""MySQL 检查点驱动的最小知识构建 worker。"""

import hashlib
from datetime import datetime
from pathlib import Path

import fitz
from sqlalchemy import func

from app.core.config import BACKEND_DIR
from app.core.database import SessionLocal
from app.models.knowledge import KnowledgePoint
from app.models.knowledge_governance import (
    KnowledgeBuildTask,
    KnowledgeBuildUnit,
    KnowledgeSourceChunk,
    KnowledgeVersion,
    Textbook,
)
from app.services.knowledge.build_repository import append_event
from app.services.knowledge.build_state import transition_task
from app.services.knowledge.pdf_parser import extract_page_record
from app.services.knowledge.versioned_writer import VersionedKnowledgeWriter
from app.services.knowledge.wiki_compiler import WikiCompiler


def _pdf_page_count(path: str) -> int:
    document = fitz.open(path)
    try:
        return document.page_count
    finally:
        document.close()


class KnowledgeBuildWorker:
    def __init__(
        self,
        *,
        page_count_loader=None,
        page_extractor=None,
        compiler=None,
        writer=None,
    ):
        self.page_count_loader = page_count_loader or _pdf_page_count
        self.page_extractor = page_extractor or extract_page_record
        self.compiler = compiler or WikiCompiler().compile_chapter
        self.writer = writer or VersionedKnowledgeWriter()

    def process_task(self, task_id: int, *, worker_id: str) -> dict:
        db = SessionLocal()
        try:
            task = db.get(KnowledgeBuildTask, task_id)
            if not task:
                raise ValueError("构建任务不存在")
            if task.status != "running" or task.lease_owner != worker_id:
                raise ValueError("任务未被当前 worker 认领")
            textbook = db.get(Textbook, task.textbook_id)
            if not textbook or not textbook.file_path:
                return self._fail_task(db, task.id, "precheck", "教材文件不存在")
            pdf_path = Path(textbook.file_path)
            if not pdf_path.is_absolute():
                pdf_path = BACKEND_DIR / pdf_path
            config = task.build_config or {}
            group_size = max(1, int(config.get("group_size", 12)))
            use_ocr = bool(config.get("use_ocr", False))

            version = self._ensure_version(db, task, textbook)
            self._ensure_extract_units(db, task, str(pdf_path))
            failure = self._process_extract_units(
                db, task.id, str(pdf_path), use_ocr=use_ocr
            )
            if failure:
                return failure
            cancellation = self._stop_if_cancelled(db, task.id)
            if cancellation:
                return cancellation

            self._ensure_compile_units(db, task.id, group_size=group_size)
            failure = self._process_compile_units(db, task.id, textbook, version)
            if failure:
                return failure
            cancellation = self._stop_if_cancelled(db, task.id)
            if cancellation:
                return cancellation

            self._ensure_index_units(db, task.id)
            failure = self._process_index_units(db, task.id, textbook, version)
            if failure:
                return failure
            cancellation = self._stop_if_cancelled(db, task.id)
            if cancellation:
                return cancellation

            task = db.get(KnowledgeBuildTask, task.id)
            version = db.get(KnowledgeVersion, version.id)
            version.status = "staged"
            version.source_chunk_count = (
                db.query(KnowledgeSourceChunk)
                .filter(KnowledgeSourceChunk.version_id == version.id)
                .count()
            )
            version.point_count = (
                db.query(KnowledgePoint)
                .filter(KnowledgePoint.version_id == version.id)
                .count()
            ) or sum(
                len((unit.checkpoint or {}).get("point_ids", []))
                for unit in db.query(KnowledgeBuildUnit)
                .filter(
                    KnowledgeBuildUnit.task_id == task.id,
                    KnowledgeBuildUnit.unit_type == "index_chunk",
                )
                .all()
            )
            version.vector_count = version.point_count
            transition_task(task, "succeeded", stage="staged")
            task.completed_units = self._completed_count(db, task.id)
            task.failed_units = 0
            task.finished_at = datetime.now()
            self._release_lease(task)
            append_event(db, task, "构建完成，版本已进入 staged")
            db.commit()
            return {"status": task.status, "version_id": version.id}
        finally:
            db.close()

    def _ensure_version(self, db, task, textbook):
        if task.target_version_id:
            version = db.get(KnowledgeVersion, task.target_version_id)
            if version:
                return version
        latest = (
            db.query(func.max(KnowledgeVersion.version_no))
            .filter(KnowledgeVersion.textbook_id == textbook.id)
            .scalar()
            or 0
        )
        version = KnowledgeVersion(
            textbook_id=textbook.id,
            version_no=latest + 1,
            status="building",
            created_by=task.requested_by,
        )
        db.add(version)
        db.flush()
        task.target_version_id = version.id
        append_event(db, task, f"已创建知识版本 v{version.version_no}")
        db.commit()
        return version

    def _ensure_extract_units(self, db, task, pdf_path: str) -> None:
        exists = db.query(KnowledgeBuildUnit).filter(
            KnowledgeBuildUnit.task_id == task.id,
            KnowledgeBuildUnit.unit_type == "extract_page",
        ).count()
        if exists:
            return
        task.stage = "precheck"
        page_count = self.page_count_loader(pdf_path)
        if page_count < 1:
            raise ValueError("PDF 不包含页面")
        for page in range(1, page_count + 1):
            db.add(
                KnowledgeBuildUnit(
                    task_id=task.id,
                    unit_type="extract_page",
                    sequence=page,
                    start_page=page,
                    end_page=page,
                    status="pending",
                )
            )
        task.total_units += page_count
        append_event(db, task, f"预检完成，共 {page_count} 页")
        db.commit()

    def _process_extract_units(self, db, task_id, pdf_path, *, use_ocr):
        units = db.query(KnowledgeBuildUnit).filter(
            KnowledgeBuildUnit.task_id == task_id,
            KnowledgeBuildUnit.unit_type == "extract_page",
            KnowledgeBuildUnit.status == "pending",
        ).order_by(KnowledgeBuildUnit.sequence).all()
        for unit in units:
            cancellation = self._stop_if_cancelled(db, task_id)
            if cancellation:
                return cancellation
            try:
                unit.status = "running"
                unit.attempts += 1
                unit.started_at = datetime.now()
                record = self.page_extractor(
                    pdf_path, unit.start_page, use_ocr=use_ocr
                )
                unit.checkpoint = record
                unit.status = "completed" if record.get("text", "").strip() else "skipped"
                unit.completed_at = datetime.now()
                task = db.get(KnowledgeBuildTask, task_id)
                task.stage = "extract"
                task.completed_units = self._completed_count(db, task_id)
                db.commit()
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                return self._fail_unit(db, task_id, unit.id, "extract", exc)
        return None

    def _ensure_compile_units(self, db, task_id, *, group_size: int) -> None:
        exists = db.query(KnowledgeBuildUnit).filter(
            KnowledgeBuildUnit.task_id == task_id,
            KnowledgeBuildUnit.unit_type == "compile_chunk",
        ).count()
        if exists:
            return
        extracted = db.query(KnowledgeBuildUnit).filter(
            KnowledgeBuildUnit.task_id == task_id,
            KnowledgeBuildUnit.unit_type == "extract_page",
            KnowledgeBuildUnit.status == "completed",
        ).order_by(KnowledgeBuildUnit.sequence).all()
        groups = [extracted[index:index + group_size] for index in range(0, len(extracted), group_size)]
        for sequence, group in enumerate(groups, 1):
            db.add(
                KnowledgeBuildUnit(
                    task_id=task_id,
                    unit_type="compile_chunk",
                    sequence=sequence,
                    start_page=group[0].start_page,
                    end_page=group[-1].end_page,
                    status="pending",
                    checkpoint={"extract_unit_ids": [unit.id for unit in group]},
                )
            )
        task = db.get(KnowledgeBuildTask, task_id)
        task.total_units += len(groups)
        db.commit()

    def _process_compile_units(self, db, task_id, textbook, version):
        units = db.query(KnowledgeBuildUnit).filter(
            KnowledgeBuildUnit.task_id == task_id,
            KnowledgeBuildUnit.unit_type == "compile_chunk",
            KnowledgeBuildUnit.status == "pending",
        ).order_by(KnowledgeBuildUnit.sequence).all()
        for unit in units:
            cancellation = self._stop_if_cancelled(db, task_id)
            if cancellation:
                return cancellation
            try:
                unit.status = "running"
                unit.attempts += 1
                unit.started_at = datetime.now()
                checkpoint = dict(unit.checkpoint or {})
                extracts = db.query(KnowledgeBuildUnit).filter(
                    KnowledgeBuildUnit.id.in_(checkpoint["extract_unit_ids"])
                ).order_by(KnowledgeBuildUnit.sequence).all()
                records = [row.checkpoint for row in extracts]
                text = "\n".join(row["text"] for row in records)
                chapter = f"第{unit.sequence}块(页{unit.start_page}-{unit.end_page})"
                points = self.compiler(
                    textbook.subject, textbook.grade, chapter, text
                )
                if not points:
                    raise ValueError("LLM 未返回知识点")
                content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
                chunk = KnowledgeSourceChunk(
                    version_id=version.id,
                    build_unit_id=unit.id,
                    sequence=unit.sequence,
                    start_page=unit.start_page,
                    end_page=unit.end_page,
                    region={
                        "pages": [
                            {"page": row["page"], "blocks": row.get("blocks", [])}
                            for row in records
                        ]
                    },
                    raw_text=text,
                    content_hash=content_hash,
                    parse_method="ocr" if any(row["parse_method"] == "ocr" for row in records) else "text",
                    parser_version=",".join(sorted({row["parser_version"] for row in records})),
                )
                db.add(chunk)
                db.flush()
                checkpoint.update({"source_chunk_id": chunk.id, "points": points})
                unit.checkpoint = checkpoint
                unit.input_hash = content_hash
                unit.status = "completed"
                unit.completed_at = datetime.now()
                task = db.get(KnowledgeBuildTask, task_id)
                task.stage = "compile"
                task.completed_units = self._completed_count(db, task_id)
                db.commit()
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                return self._fail_unit(db, task_id, unit.id, "compile", exc)
        return None

    def _ensure_index_units(self, db, task_id):
        exists = db.query(KnowledgeBuildUnit).filter(
            KnowledgeBuildUnit.task_id == task_id,
            KnowledgeBuildUnit.unit_type == "index_chunk",
        ).count()
        if exists:
            return
        compiled = db.query(KnowledgeBuildUnit).filter(
            KnowledgeBuildUnit.task_id == task_id,
            KnowledgeBuildUnit.unit_type == "compile_chunk",
            KnowledgeBuildUnit.status == "completed",
        ).order_by(KnowledgeBuildUnit.sequence).all()
        for row in compiled:
            db.add(
                KnowledgeBuildUnit(
                    task_id=task_id,
                    unit_type="index_chunk",
                    sequence=row.sequence,
                    start_page=row.start_page,
                    end_page=row.end_page,
                    status="pending",
                    checkpoint={"compile_unit_id": row.id},
                )
            )
        task = db.get(KnowledgeBuildTask, task_id)
        task.total_units += len(compiled)
        db.commit()

    def _process_index_units(self, db, task_id, textbook, version):
        units = db.query(KnowledgeBuildUnit).filter(
            KnowledgeBuildUnit.task_id == task_id,
            KnowledgeBuildUnit.unit_type == "index_chunk",
            KnowledgeBuildUnit.status == "pending",
        ).order_by(KnowledgeBuildUnit.sequence).all()
        for unit in units:
            cancellation = self._stop_if_cancelled(db, task_id)
            if cancellation:
                return cancellation
            try:
                unit.status = "running"
                unit.attempts += 1
                unit.started_at = datetime.now()
                checkpoint = dict(unit.checkpoint or {})
                compiled = db.get(KnowledgeBuildUnit, checkpoint["compile_unit_id"])
                compiled_checkpoint = compiled.checkpoint or {}
                rows = self.writer.save_chunk_points(
                    db,
                    version_id=version.id,
                    source_chunk_id=compiled_checkpoint["source_chunk_id"],
                    subject=textbook.subject,
                    grade=textbook.grade,
                    chapter=f"第{unit.sequence}块(页{unit.start_page}-{unit.end_page})",
                    points=compiled_checkpoint["points"],
                )
                checkpoint["point_ids"] = [row.id for row in rows]
                unit.checkpoint = checkpoint
                unit.status = "completed"
                unit.completed_at = datetime.now()
                task = db.get(KnowledgeBuildTask, task_id)
                task.stage = "index"
                task.completed_units = self._completed_count(db, task_id)
                db.commit()
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                return self._fail_unit(db, task_id, unit.id, "index", exc)
        return None

    def _fail_unit(self, db, task_id, unit_id, stage, exc):
        task = db.get(KnowledgeBuildTask, task_id)
        unit = db.get(KnowledgeBuildUnit, unit_id)
        unit.status = "failed"
        unit.attempts += 1
        unit.error_type = type(exc).__name__
        unit.error_detail = str(exc)
        unit.completed_at = datetime.now()
        transition_task(task, "needs_attention", stage=stage)
        db.flush()
        task.failed_units = db.query(KnowledgeBuildUnit).filter(
            KnowledgeBuildUnit.task_id == task.id,
            KnowledgeBuildUnit.status == "failed",
        ).count()
        task.error_summary = str(exc)
        task.completed_units = self._completed_count(db, task_id)
        self._release_lease(task)
        append_event(db, task, f"单元失败: {exc}", level="error", unit_id=unit.id)
        db.commit()
        return {"status": task.status, "version_id": task.target_version_id}

    def _fail_task(self, db, task_id, stage, message):
        task = db.get(KnowledgeBuildTask, task_id)
        transition_task(task, "failed", stage=stage)
        task.error_summary = message
        task.finished_at = datetime.now()
        self._release_lease(task)
        append_event(db, task, message, level="error")
        db.commit()
        return {"status": task.status, "version_id": task.target_version_id}

    @staticmethod
    def _stop_if_cancelled(db, task_id):
        task = db.get(KnowledgeBuildTask, task_id)
        db.refresh(task)
        if task.status == "cancelled":
            return {"status": "cancelled", "version_id": task.target_version_id}
        return None

    @staticmethod
    def _completed_count(db, task_id):
        return db.query(KnowledgeBuildUnit).filter(
            KnowledgeBuildUnit.task_id == task_id,
            KnowledgeBuildUnit.status.in_(("completed", "skipped")),
        ).count()

    @staticmethod
    def _release_lease(task):
        task.lease_owner = None
        task.lease_expires_at = None
        task.heartbeat_at = None
