import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import Material, MaterialType
from app.services.material_files import (
    add_pdf,
    delete_files,
    list_files,
    validate_pdf,
)


@pytest.fixture
async def session(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.material_files.MATERIALS_DIR",
        tmp_path / "materials",
    )
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as s:
        yield s
    await engine.dispose()


def test_validate_pdf():
    assert validate_pdf("a.pdf", b"%PDF-1.4") is None
    assert validate_pdf("a.txt", b"hello") is not None


@pytest.mark.asyncio
async def test_add_and_delete_pdfs(session: AsyncSession, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.material_files.MATERIALS_DIR",
        tmp_path / "materials",
    )
    material = Material(
        title="Документ",
        content_type=MaterialType.DOCUMENT.value,
        content="Текст",
        sort_order=1,
        is_active=True,
    )
    session.add(material)
    await session.flush()

    first = await add_pdf(session, material.id, "один.pdf", b"%PDF-1.4 one")
    second = await add_pdf(session, material.id, "два.pdf", b"%PDF-1.4 two")
    rows = await list_files(session, material.id)
    assert [row.original_name for row in rows] == ["один.pdf", "два.pdf"]
    assert (tmp_path / "materials" / str(material.id) / first.stored_name).is_file()

    removed = await delete_files(session, material.id, [second.id])
    assert removed == 1
    left = await list_files(session, material.id)
    assert len(left) == 1
    assert left[0].id == first.id
