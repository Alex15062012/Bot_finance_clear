from app.db.models import Material, MaterialType
from app.services.material_export import export_material_docx, export_material_pdf


def test_export_docx_and_pdf():
    material = Material(
        id=1,
        title="Тестовый материал",
        description="Краткое описание",
        content_type=MaterialType.TEXT.value,
        content="Текст с кириллицей для проверки экспорта.",
        url="https://example.com/doc",
        sort_order=1,
        is_active=True,
    )
    docx = export_material_docx(material)
    assert docx[:2] == b"PK"
    pdf = export_material_pdf(material)
    assert pdf.startswith(b"%PDF")
