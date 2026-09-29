"""Хранение PDF-вложений материалов на диске."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.material_file import MaterialFile

MATERIALS_DIR = Path("data") / "materials"
MAX_PDF_BYTES = 20 * 1024 * 1024


def material_dir(material_id: int) -> Path:
    path = MATERIALS_DIR / str(material_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def file_path(row: MaterialFile) -> Path:
    return MATERIALS_DIR / str(row.material_id) / row.stored_name


def safe_pdf_name(filename: str) -> str:
    name = Path(filename or "document.pdf").name
    name = re.sub(r"[^\w.\- ()а-яА-ЯёЁ]+", "_", name, flags=re.UNICODE).strip("._")
    if not name.lower().endswith(".pdf"):
        name = f"{name or 'document'}.pdf"
    return name[:180] or "document.pdf"


def validate_pdf(filename: str, data: bytes) -> str | None:
    if not data:
        return "Пустой файл"
    if len(data) > MAX_PDF_BYTES:
        return f"«{filename}» больше 20 МБ"
    looks_pdf = b"%PDF" in data[:1024]
    named_pdf = (filename or "").lower().endswith(".pdf")
    if not looks_pdf and not named_pdf:
        return f"«{filename}» не похож на PDF"
    if not looks_pdf:
        return f"«{filename}» не является PDF"
    return None


async def list_files(session: AsyncSession, material_id: int) -> list[MaterialFile]:
    rows = (
        await session.execute(
            select(MaterialFile)
            .where(MaterialFile.material_id == material_id)
            .order_by(MaterialFile.sort_order.asc(), MaterialFile.id.asc())
        )
    ).scalars().all()
    return list(rows)


async def add_pdf(
    session: AsyncSession,
    material_id: int,
    filename: str,
    data: bytes,
) -> MaterialFile:
    error = validate_pdf(filename, data)
    if error:
        raise ValueError(error)

    existing = await list_files(session, material_id)
    stored = f"{uuid.uuid4().hex}.pdf"
    dest = material_dir(material_id) / stored
    dest.write_bytes(data)

    row = MaterialFile(
        material_id=material_id,
        original_name=safe_pdf_name(filename),
        stored_name=stored,
        size_bytes=len(data),
        sort_order=(existing[-1].sort_order + 1) if existing else 0,
    )
    session.add(row)
    await session.flush()
    return row


async def delete_files(
    session: AsyncSession, material_id: int, file_ids: list[int]
) -> int:
    if not file_ids:
        return 0
    rows = (
        await session.execute(
            select(MaterialFile).where(
                MaterialFile.material_id == material_id,
                MaterialFile.id.in_(file_ids),
            )
        )
    ).scalars().all()
    removed = 0
    for row in rows:
        path = file_path(row)
        if path.is_file():
            path.unlink()
        await session.delete(row)
        removed += 1
    if removed:
        await session.flush()
    return removed
