"""教材文件校验、幂等存储与元数据序列化。"""

import hashlib
import json
import uuid
from pathlib import Path

import fitz
from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import BACKEND_DIR, settings
from app.models.knowledge_governance import Textbook


class TextbookValidationError(ValueError):
    pass


class TextbookConflictError(ValueError):
    pass


def textbook_identity(metadata: dict[str, str]) -> str:
    fields = (
        "school_stage",
        "grade",
        "subject",
        "publisher",
        "edition",
        "volume",
    )
    canonical = {
        field: (metadata.get(field) or "").strip().lower() for field in fields
    }
    digest = hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return f"textbook:{digest}"


def _storage_dir() -> Path:
    configured = Path(settings.textbook_storage_dir)
    path = configured if configured.is_absolute() else BACKEND_DIR / configured
    path = path.resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def serialize_textbook(textbook: Textbook, *, created: bool | None = None) -> dict:
    payload = {
        "id": textbook.id,
        "school_stage": textbook.school_stage,
        "grade": textbook.grade,
        "subject": textbook.subject,
        "publisher": textbook.publisher,
        "edition": textbook.edition,
        "volume": textbook.volume,
        "original_filename": textbook.original_filename,
        "file_path": textbook.file_path,
        "mime_type": textbook.mime_type,
        "file_size": textbook.file_size,
        "page_count": textbook.page_count,
        "file_sha256": textbook.file_sha256,
        "source_url": textbook.source_url,
        "source_note": textbook.source_note,
        "license_note": textbook.license_note,
        "source_kind": textbook.source_kind,
        "active_version_id": textbook.active_version_id,
        "created_at": textbook.created_at.isoformat() if textbook.created_at else None,
    }
    if created is not None:
        payload["created"] = created
    return payload


async def store_textbook_upload(
    db: Session,
    upload: UploadFile,
    *,
    metadata: dict[str, str],
    uploaded_by: int,
) -> tuple[Textbook, bool]:
    required_labels = {
        "school_stage": "学段",
        "grade": "年级",
        "subject": "学科",
        "publisher": "出版社",
        "edition": "版次",
        "volume": "册次",
        "source_note": "来源说明",
        "license_note": "授权说明",
    }
    for field, label in required_labels.items():
        if not (metadata.get(field) or "").strip():
            raise TextbookValidationError(f"{label}不能为空")

    filename = (upload.filename or "").strip()
    if not filename.lower().endswith(".pdf"):
        raise TextbookValidationError("只允许上传 PDF 文件")
    if upload.content_type not in {"application/pdf", "application/x-pdf"}:
        raise TextbookValidationError("文件 MIME 类型不是 PDF")

    storage = _storage_dir()
    temporary = storage / f".upload-{uuid.uuid4().hex}.tmp"
    digest = hashlib.sha256()
    size = 0
    final_path: Path | None = None
    try:
        with temporary.open("wb") as handle:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > settings.textbook_max_file_bytes:
                    raise TextbookValidationError("PDF 超过允许的文件大小")
                digest.update(chunk)
                handle.write(chunk)
        if size < 5:
            raise TextbookValidationError("PDF 文件为空或不完整")
        with temporary.open("rb") as handle:
            if handle.read(5) != b"%PDF-":
                raise TextbookValidationError("文件头不是有效 PDF")

        try:
            document = fitz.open(temporary)
            page_count = document.page_count
            document.close()
        except Exception as exc:  # noqa: BLE001
            raise TextbookValidationError(f"PDF 无法解析: {exc}") from exc
        if page_count < 1:
            raise TextbookValidationError("PDF 不包含页面")
        if page_count > settings.textbook_max_pages:
            raise TextbookValidationError("PDF 页数超过允许上限")

        sha256 = digest.hexdigest()
        identity_key = textbook_identity(metadata)
        existing_hash = (
            db.query(Textbook).filter(Textbook.file_sha256 == sha256).first()
        )
        if existing_hash:
            if existing_hash.identity_key != identity_key:
                raise TextbookConflictError("相同文件已使用不同教材元数据登记")
            temporary.unlink(missing_ok=True)
            return existing_hash, False

        existing_identity = (
            db.query(Textbook).filter(Textbook.identity_key == identity_key).first()
        )
        if existing_identity:
            raise TextbookConflictError("同一教材身份已登记不同文件")

        final_path = storage / f"{sha256}.pdf"
        if final_path.exists():
            raise TextbookConflictError("存储中已存在同哈希文件但数据库缺少记录")
        temporary.replace(final_path)
        try:
            relative_path = final_path.relative_to(BACKEND_DIR.resolve()).as_posix()
        except ValueError as exc:
            raise TextbookValidationError("教材目录必须位于后端受管目录内") from exc

        textbook = Textbook(
            identity_key=identity_key,
            school_stage=metadata["school_stage"].strip(),
            grade=metadata["grade"].strip(),
            subject=metadata["subject"].strip(),
            publisher=metadata["publisher"].strip(),
            edition=metadata["edition"].strip(),
            volume=metadata["volume"].strip(),
            original_filename=filename,
            file_path=relative_path,
            mime_type="application/pdf",
            file_size=size,
            page_count=page_count,
            file_sha256=sha256,
            source_url=(metadata.get("source_url") or "").strip() or None,
            source_note=metadata["source_note"].strip(),
            license_note=metadata["license_note"].strip(),
            source_kind="uploaded",
            uploaded_by=uploaded_by,
        )
        db.add(textbook)
        db.commit()
        db.refresh(textbook)
        return textbook, True
    except Exception:
        db.rollback()
        temporary.unlink(missing_ok=True)
        if final_path and final_path.exists():
            final_path.unlink()
        raise
    finally:
        await upload.close()
