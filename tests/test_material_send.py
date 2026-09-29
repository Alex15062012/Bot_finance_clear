import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import Material, MaterialType
from app.max_api.client import MaxApiError, is_attachment_not_ready
from app.services.material_files import add_pdf, list_files
from app.services.messaging import MessagingService

NOT_READY = (
    '{"code":"attachment.not.ready",'
    '"message":"Key: errors.process.attachment.file.not.processed"}'
)


class _Api:
    def __init__(self, fail_times: int):
        self.fail_times = fail_times
        self.chat_calls: list[dict] = []
        self.user_calls: list[dict] = []
        self.uploads = 0

    async def upload_file(self, filename: str, content: bytes, **kwargs):
        self.uploads += 1
        assert content.startswith(b"%PDF")
        assert filename.endswith(".pdf")
        return "file-token"

    async def send_message_to_chat(self, chat_id, text, *, attachments=None, format=None):
        self.chat_calls.append(
            {"chat_id": chat_id, "text": text, "attachments": attachments, "format": format}
        )
        if attachments and len(self.chat_calls) <= self.fail_times:
            raise MaxApiError("not ready", status_code=400, body=NOT_READY)
        return {"ok": True}

    async def send_message_to_user(self, user_id, text, *, attachments=None, format=None):
        self.user_calls.append({"user_id": user_id})
        raise AssertionError("user_id fallback must not run on attachment.not.ready")


@pytest.fixture
async def session(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.material_files.MATERIALS_DIR",
        tmp_path / "materials",
    )

    async def _sleep(_delay):
        return None

    monkeypatch.setattr("app.services.messaging.asyncio.sleep", _sleep)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as s:
        yield s
    await engine.dispose()


def test_not_ready_detector():
    exc = MaxApiError("x", status_code=400, body=NOT_READY)
    assert is_attachment_not_ready(exc)
    other = MaxApiError("x", status_code=403, body='{"code":"chat.denied"}')
    assert not is_attachment_not_ready(other)


@pytest.mark.asyncio
async def test_send_material_retries_until_file_ready(session, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.material_files.MATERIALS_DIR",
        tmp_path / "materials",
    )
    material = Material(title="Где прибыль", content_type=MaterialType.TEXT.value, content="Текст")
    session.add(material)
    await session.flush()
    await add_pdf(session, material.id, "doc.pdf", b"%PDF-1.4 test")

    api = _Api(fail_times=2)
    messaging = MessagingService(session, api, content=None)  # type: ignore[arg-type]
    result = await messaging.send_material(5600001, material, chat_id=383694387)

    assert result == {"ok": True}
    assert api.uploads == 1
    assert api.user_calls == []
    assert len(api.chat_calls) == 3
    assert api.chat_calls[-1]["attachments"] == [
        {"type": "file", "payload": {"token": "file-token"}}
    ]
    files = await messaging._pdf_attachments(await list_files(session, material.id))
    assert files[0][0].max_token == "file-token"
    assert api.uploads == 1
