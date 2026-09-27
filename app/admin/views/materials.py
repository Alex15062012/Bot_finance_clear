from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import db_session, render, require_admin, set_flash
from app.db.models import Material, MaterialType
from app.services.material_export import (
    content_disposition,
    export_material_docx,
    export_material_pdf,
    safe_filename,
)
from app.services.material_files import add_pdf, delete_files, file_path, list_files

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
    files = await list_files(session, row.id)
    return render(
        request,
        "materials/edit.html",
        section="materials",
        title=f"Материал: {row.title}",
        material=row,
        types=list(MaterialType),
        files=files,
    )


@router.get("/{material_id}/export.docx")
async def export_docx(
    material_id: int,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
):
    row = await session.get(Material, material_id)
    if not row:
        return RedirectResponse("/admin/materials", status_code=303)
    data = export_material_docx(row)
    return Response(
        content=data,
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        headers={
            "Content-Disposition": content_disposition(
                safe_filename(row.title, "docx"), row.id, "docx"
            )
        },
    )


@router.get("/{material_id}/export.pdf")
async def export_pdf(
    material_id: int,
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
):
    row = await session.get(Material, material_id)
    if not row:
        return RedirectResponse("/admin/materials", status_code=303)
    try:
        data = export_material_pdf(row)
    except FileNotFoundError as exc:
        set_flash(request, str(exc), "error")
        return RedirectResponse(f"/admin/materials/{material_id}", status_code=303)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": content_disposition(
                safe_filename(row.title, "pdf"), row.id, "pdf"
            )
        },
    )


@router.get("/{material_id}/files/{file_id}")
async def download_material_file(
    material_id: int,
    file_id: int,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
):
    files = await list_files(session, material_id)
    row = next((item for item in files if item.id == file_id), None)
    if not row:
        return RedirectResponse(f"/admin/materials/{material_id}", status_code=303)
    path = file_path(row)
    if not path.is_file():
        return RedirectResponse(f"/admin/materials/{material_id}", status_code=303)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=row.original_name,
    )


@router.post("/{material_id}/files/{file_id}/delete")
async def delete_material_file(
    material_id: int,
    file_id: int,
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
):
    removed = await delete_files(session, material_id, [file_id])
    await session.commit()
    if removed:
        set_flash(request, "PDF удалён")
    else:
        set_flash(request, "Файл не найден", "error")
    return RedirectResponse(f"/admin/materials/{material_id}", status_code=303)


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
    delete_file_ids: list[int] = Form(default=[]),
    pdfs: list[UploadFile] = File(default=[]),
):
    row = await session.get(Material, material_id)
    if not row:
        set_flash(request, "Материал не найден", "error")
        return RedirectResponse("/admin/materials", status_code=303)

    valid_types = {t.value for t in MaterialType}
    if content_type not in valid_types:
        set_flash(request, "Некорректный тип", "error")
        return RedirectResponse(f"/admin/materials/{material_id}", status_code=303)

    prepared: list[tuple[str, bytes]] = []
    for upload in pdfs:
        if not upload.filename:
            continue
        data = await upload.read()
        if not data:
            continue
        from app.services.material_files import validate_pdf

        error = validate_pdf(upload.filename, data)
        if error:
            set_flash(request, error, "error")
            return RedirectResponse(f"/admin/materials/{material_id}", status_code=303)
        prepared.append((upload.filename, data))

    row.title = title.strip()
    row.description = description.strip() or None
    row.content_type = content_type
    row.content = content.strip() or None
    row.url = url.strip() or None
    row.sort_order = sort_order
    row.is_active = is_active == "on"
    await delete_files(session, row.id, delete_file_ids)
    for filename, data in prepared:
        await add_pdf(session, row.id, filename, data)
    await session.commit()
    extra = f" Добавлено PDF: {len(prepared)}." if prepared else ""
    set_flash(request, f"Материал сохранён.{extra}")
    return RedirectResponse(f"/admin/materials/{row.id}", status_code=303)
