from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import db_session, render, require_admin, set_flash
from app.max_api.client import MaxApiError
from app.services.bot_groups import list_groups, sync_groups_from_api

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/groups",
    tags=["admin-groups"],
)


@router.get("")
async def list_bot_groups(
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
):
    rows = await list_groups(session)
    return render(
        request,
        "groups/list.html",
        section="groups",
        title="Группы",
        groups=rows,
    )


@router.post("/refresh")
async def refresh_bot_groups(
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
):
    api = getattr(request.app.state, "api", None)
    if api is None:
        set_flash(request, "Нет подключения к MAX", "error")
        return RedirectResponse("/admin/groups", status_code=303)
    try:
        count = await sync_groups_from_api(session, api)
        await session.commit()
    except MaxApiError:
        logger.warning("Не удалось проверить группы и каналы в MAX")
        await session.rollback()
        set_flash(request, "Не удалось проверить чаты в MAX", "error")
        return RedirectResponse("/admin/groups", status_code=303)
    except Exception:
        logger.exception("Ошибка проверки групп и каналов")
        await session.rollback()
        set_flash(request, "Не удалось проверить чаты в MAX", "error")
        return RedirectResponse("/admin/groups", status_code=303)
    if count:
        set_flash(request, f"Проверка выполнена. Каналов и групп: {count}.")
    else:
        set_flash(request, "Проверка выполнена. Бот не состоит ни в одной группе или канале.")
    return RedirectResponse("/admin/groups", status_code=303)
