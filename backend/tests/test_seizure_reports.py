"""Pruebas del núcleo documental del módulo Seizure Report."""

from datetime import date
from pathlib import Path
from types import SimpleNamespace

from docx import Document
from PIL import Image
from pypdf import PdfReader
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401 - registra el metadata completo
from database import Base
from models.brand import Brand
from models.seizure_report import SeizureFile, SeizureReport
from models.user import User
from schemas.seizure_report import ProductIn, SeizureReportIn, TargetIn
from services import seizure_report_service as service
from services.procedure_reference_service import assign_reference


def fake_report():
    return SimpleNamespace(
        id=99, country="Argentina", province="CABA", city="CABA", operation_date=date(2026, 9, 7),
        case_origin="Inspección", client_name="Nike", brand_name="Nike", brand_code="NI",
        police_agency="Policía de la Ciudad", police_unit="División Conductas Ilícitas",
        court="Juzgado PCyF 35", judge="Dra. Celsa Ramírez", media_impact="N/A", political_impact="N/A",
        proposed_fees="450", currency="USD", internal_reference="001-26-NI", seized_goods_total=1250,
        targets=[SimpleNamespace(establishment_name=None,address="Castelli 264, CABA",investigated_party=None)],
        files=[],
    )


def test_brand_codes_from_corporate_catalogue():
    assert service.brand_code("Puma") == "PU"
    assert service.brand_code("New Era") == "NE"
    assert service.brand_code("Alo") == "AL"


def test_official_reference_formats_and_emission_year(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'references.db'}")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    intelligence, _ = assign_reference(db, "INTELIGENCIA", "Puma")
    market_study, _ = assign_reference(db, "ESTUDIO_MERCADO", "Nike")
    seizure, _ = assign_reference(db, "ALLANAMIENTO", "Puma")
    assert intelligence.endswith("-IN-PU") and intelligence[:3] == "001"
    assert market_study.endswith("-IN-NI") and market_study[:3] == "002"
    assert seizure.endswith("-PU") and "-IN-" not in seizure and seizure[:3] == "001"


def test_word_and_pdf_without_photos(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "STORAGE", tmp_path)
    report = fake_report()
    pdf = service.generate_pdf(report, 1)
    word = service.generate_docx(report, 1)
    assert len(PdfReader(str(pdf)).pages) == 2
    opened = Document(str(word))
    assert any("SEIZURE REPORT" in paragraph.text for paragraph in opened.paragraphs)
    assert pdf.stat().st_size > 1000 and word.stat().st_size > 1000


def test_extract_police_report_fields():
    # La extracción tolera documentos parciales: se prueban patrones sobre un PDF mínimo generado.
    from reportlab.pdfgen import canvas
    from io import BytesIO
    stream=BytesIO(); pdf=canvas.Canvas(stream); pdf.drawString(30,800,"FECHA: MIERCOLES 07/10/2026"); pdf.drawString(30,780,"CAUSA: MPF 146240/2026"); pdf.save(); stream.seek(0)
    data=service.extract_police_pdf(stream)
    assert "07/10/2026" in data["operation_date_text"]
    assert data["court_case_number"] == "MPF 146240/2026"


def test_extract_real_police_structure_fields():
    from reportlab.pdfgen import canvas
    from io import BytesIO
    stream=BytesIO(); pdf=canvas.Canvas(stream)
    lines=["DCC 3", "ASUNTO: INSPECCION LEY DE MARCAS OS 7998/2026", "FECHA: 23/09/2026",
           "LUGAR: Pueyrredón 241, CABA", "IMPUTADO: Persona identificada",
           "MAGISTRADO INTERVENTOR: Fiscalía PCyF Nro 4", "RECURSOS: Personal de brigada",
           "SECUESTRO: SEIS MIL TRESCIENTOS NUEVE (6.309) prendas marcas NIKE, PUMA, LACOSTE",
           "RESEÑA: Resultado positivo de la inspección."]
    for index,line in enumerate(lines): pdf.drawString(30,800-index*22,line)
    pdf.save(); stream.seek(0)
    data=service.extract_police_pdf(stream)
    assert data["operation_date"] == "2026-09-23"
    assert data["targets"] == ["Pueyrredón 241, CABA"]
    assert data["seized_goods_total"] == 6309
    assert {"Nike", "Puma", "Lacoste"}.issubset(set(data["identified_brands"]))


def test_crud_totals_workflow_history_and_reference(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    user = User(nombre="Ana", apellido="Test", correo="ana@example.com", password_hash="x", rol="admin")
    db.add(user); db.flush()
    brand = Brand(nombre="Puma", created_by=user.id)
    db.add(brand); db.commit()
    payload = SeizureReportIn(
        brand_id=brand.id, operation_date="2026-10-28",
        targets=[TargetIn(address="Castelli 264, Ciudad Autónoma de Buenos Aires")],
        products=[ProductIn(brand_name="Puma", quantity=12), ProductIn(brand_name="New Era", quantity=8)],
    )
    report = service.apply_payload(db, SeizureReport(created_by=user.id), payload, user.id)
    assert report.seized_goods_total == 20
    assert report.audit_events[0].action == "REPORT_CREATED"
    assert report.audit_events[0].user_id == user.id
    db.add_all([
        SeizureFile(report_id=report.id,kind="photo",original_name="evidence.jpg",stored_name="test-evidence.jpg",mime_type="image/jpeg",size_bytes=10,position=0,uploaded_by=user.id,brand_name="Puma"),
        SeizureFile(report_id=report.id,kind="document",document_type="ACTA_POLICIAL",original_name="acta.pdf",stored_name="test-acta.pdf",mime_type="application/pdf",size_bytes=10,position=1,uploaded_by=user.id),
    ]); db.commit(); db.refresh(report)
    service.transition(db, report, "PENDIENTE_REVISION", "Listo", user)
    service.transition(db, report, "APROBADO_INTERNAMENTE", "Aprobado", user)
    assert report.internal_reference == "001-26-PU"
    assert [row.to_status for row in report.history] == ["BORRADOR", "PENDIENTE_REVISION", "APROBADO_INTERNAMENTE"]


def test_save_long_investigated_parties_from_police_report(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'long-fields.db'}")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    user = User(nombre="Ana", apellido="Test", correo="long@example.com", password_hash="x", rol="admin")
    db.add(user); db.commit()
    investigated = "; ".join(f"Persona investigada número {index} con documento 12.345.{index:03d}" for index in range(40))
    payload = SeizureReportIn(
        police_unit="División de investigaciones " * 30,
        targets=[TargetIn(address="Pueyrredón 241, CABA", investigated_party=investigated)],
    )
    report = service.apply_payload(db, SeizureReport(created_by=user.id), payload, user.id)
    db.expire_all()
    saved = db.get(SeizureReport, report.id)
    assert saved.targets[0].investigated_party == investigated
    assert len(saved.targets[0].investigated_party) > 250


def test_pdf_layout_with_1_5_20_and_50_mixed_photos(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "STORAGE", tmp_path)
    files = []
    for index in range(50):
        name = f"photo_{index}.jpg"
        size = (1600, 900) if index % 2 == 0 else (800, 1400)
        Image.new("RGB", size, (20 + index, 70, 120)).save(tmp_path / name)
        files.append(SimpleNamespace(kind="photo", include_in_report=True, stored_name=name,
                                     caption=f"Evidencia {index + 1}", mime_type="image/jpeg"))
    report = fake_report()
    for count in (1, 5, 20, 50):
        report.files = files[:count]
        pdf = service.generate_pdf(report, 1)
        reader = PdfReader(str(pdf))
        assert len(reader.pages) >= 3
        assert all(page.mediabox.width > 0 and page.mediabox.height > 0 for page in reader.pages)
