from __future__ import annotations

from fastapi import APIRouter

from app.admin.views import (
    auth,
    buttons,
    commands,
    dashboard,
    leads,
    materials,
    messages,
    settings,
    users,
)

admin_router = APIRouter(prefix='/admin')
admin_router.include_router(auth.router)
admin_router.include_router(dashboard.router)
admin_router.include_router(messages.router)
admin_router.include_router(commands.router)
admin_router.include_router(buttons.router)
admin_router.include_router(leads.router)
admin_router.include_router(materials.router)
admin_router.include_router(settings.router)
admin_router.include_router(users.router)
