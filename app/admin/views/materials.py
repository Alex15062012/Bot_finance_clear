from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import db_session, render, require_admin, set_flash
from app.db.models import Material, MaterialType

router = APIRouter(
    prefix="/materials",
    tags=["admin-materials"],
)


@router.get("")
async def list_materials(
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
):
    rows = (
        await session.execute(
            select(Material).order_by(Material.sort_order.asc(), Material.id.asc())
        )
    ).scalars().all()
    return render(
        request,
        "materials/list.html",
        section="materials",
        title="Материалы",
        materials=rows,
    )


@router.get("/{material_id}")
async def edit_material_page(
    material_id: int,
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
):
    row = await session.get(Material, material_id)
    if not row:
        set_flash(request, "Материал не найден", "error")
        return RedirectResponse("/admin/materials", status_code=303)
    return render(
        request,
        "materials/edit.html",
        section="materials",
        title=f"Материал: {row.title}",
        material=row,
        types=list(MaterialType),
    )


@router.post("/{material_id}")
async def save_material(
    material_id: int,
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
    title: str = Form(...),
    description: str = Form(""),
    content_type: str = Form(...),
    content: str = Form(""),
    url: str = Form(""),
    sort_order: int = Form(0),
    is_active: str | None = Form(None),
):
    row = await session.get(Material, material_id)
    if not row:
        set_flash(request, "Материал не найден", "error")
        return RedirectResponse("/admin/materials", status_code=303)

    valid_types = {t.value for t in MaterialType}
    if content_type not in valid_types:
        set_flash(request, "Некорректный тип", "error")
        return RedirectResponse(f"/admin/materials/{material_id}", status_code=303)

    row.title = title.strip()
    row.description = description.strip() or None
    row.content_type = content_type
    row.content = content.strip() or None
    row.url = url.strip() or None
    row.sort_order = sort_order
    row.is_active = is_active == "on"
    await session.commit()
    set_flash(request, "Материал сохранён")
    return RedirectResponse(f"/admin/materials/{row.id}", status_code=303)
