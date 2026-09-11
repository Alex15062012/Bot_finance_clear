from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from app.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/webhook/max")
async def max_webhook(
    request: Request,
    x_max_bot_api_secret: str | None = Header(default=None, alias="X-Max-Bot-Api-Secret"),
) -> dict[str, str]:
    settings = get_settings()
    if settings.webhook_secret:
        if not x_max_bot_api_secret or x_max_bot_api_secret != settings.webhook_secret:
            raise HTTPException(status_code=403, detail="Invalid webhook secret")

    payload: Any = await request.json()
    updates: list[dict[str, Any]]
    if isinstance(payload, dict) and "updates" in payload:
        updates = list(payload["updates"])
    elif isinstance(payload, list):
        updates = payload
    elif isinstance(payload, dict):
        updates = [payload]
    else:
        logger.warning("Unexpected webhook payload type: %s", type(payload))
        return {"status": "ignored"}

    router_obj = request.app.state.update_router
    session_factory = request.app.state.session_factory

    for update in updates:
        async with session_factory() as session:
            await router_obj.handle(session, update)

    return {"status": "ok"}
