import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.db.models.channel_schedule import ChannelSchedule
from app.db.session import SessionLocal
from app.main import app


def _schedule_id(send_time: str) -> int | None:
    async def load() -> int | None:
        async with SessionLocal() as session:
            return await session.scalar(
                select(ChannelSchedule.id).where(ChannelSchedule.send_time == send_time)
            )

    return asyncio.run(load())


def test_admin_can_add_and_remove_schedule():
    get_settings.cache_clear()
    settings = get_settings()
    client = TestClient(app)
    login = client.post(
        "/admin/login",
        data={"username": settings.admin_username, "password": settings.admin_password},
        follow_redirects=False,
    )
    assert login.status_code == 303

    page = client.get("/admin/schedules")
    assert page.status_code == 200
    assert "Каждый день" in page.text
    assert "Расписание" in page.text

    added = client.post(
        "/admin/schedules",
        data={
            "mode": "weekday",
            "weekday": "4",
            "on_date": "",
            "send_time": "03:33",
        },
        follow_redirects=False,
    )
    assert added.status_code == 303
    schedule_id = _schedule_id("03:33")
    assert schedule_id is not None
    try:
        page = client.get("/admin/schedules")
        assert "03:33" in page.text
        assert "Пятница" in page.text
        deleted = client.post(
            f"/admin/schedules/{schedule_id}/delete",
            follow_redirects=False,
        )
        assert deleted.status_code == 303
        page = client.get("/admin/schedules")
        assert "03:33" not in page.text
    finally:
        leftover = _schedule_id("03:33")
        if leftover is not None:
            client.post(f"/admin/schedules/{leftover}/delete", follow_redirects=False)
