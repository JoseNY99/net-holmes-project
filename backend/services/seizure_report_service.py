"""Negocio, almacenamiento y generación documental de Seizure Reports."""

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import json
import re
import uuid
import zipfile

from fastapi import HTTPException, UploadFile
from PIL import Image
import pytesseract
from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image as RLImage, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import or_
from sqlalchemy.orm import Session
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from models.brand import Brand
from models.seizure_report import (
    SeizureAuditEvent, SeizureDocumentVersion, SeizureFile, SeizureHistory, SeizureProduct, SeizureReportBrand,
    SeizureReport, SeizureSequence, SeizureTarget,
)
from services.procedure_reference_service import assign_reference, brand_code as official_brand_code, normalize_report_type


STORAGE = Path(__file__).resolve().parent.parent / "assets" / "seizure_reports"
STORAGE.mkdir(parents=True, exist_ok=True)
TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "assets" / "seizure_templates"
PACKAGED_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "seizure_reports"
NAVY, CYAN = colors.HexColor("#172f53"), colors.HexColor("#10c5c9")
DISCLAIMER = (
    "The information contained in this report has been obtained through lawful and publicly available sources, "
    "in compliance with applicable regulations of the Argentine Republic, including Article 43 of the National "
    "Constitution, Law No. 25,326 on Personal Data Protection, Law No. 27,401 on Corporate Criminal Liability and "
    "related compliance standards. This report is strictly limited to the information, images, records and documents "
    "expressly included herein and is provided solely for internal compliance, intellectual property protection, "
    "risk assessment and enforcement purposes. Underlying records and working papers remain confidential."
)
BRAND_CODES = {
    "puma":"PU", "new era":"NE", "lacoste":"LC", "tommy hilfiger":"TH", "calvin klein":"CK",
    "under armour":"UA", "mlb":"MLB", "nba":"NBA", "wella company":"WC", "polo":"PRL",
    "ralph lauren":"PRL", "among us":"AU", "universal studios":"US", "lego":"LE",
    "victoria's secret":"VP", "ray ban":"RB", "chanel":"CH", "alo":"AL", "nike":"NI",
}
POLICE_AGENCIES = (
    (r"POLIC[IÍ]A\s+DE\s+LA\s+CIUDAD(?:\s+DE\s+BUENOS\s+AIRES)?", "Policía de la Ciudad de Buenos Aires"),
    (r"POLIC[IÍ]A\s+FEDERAL(?:\s+ARGENTINA)?|\bPFA\b", "Policía Federal Argentina"),
    (r"GENDARMER[IÍ]A(?:\s+NACIONAL(?:\s+ARGENTINA)?)?|\bGNA\b", "Gendarmería Nacional Argentina"),
    (r"PREFECTURA(?:\s+NAVAL(?:\s+ARGENTINA)?)?|\bPNA\b", "Prefectura Naval Argentina"),
    (r"POLIC[IÍ]A\s+DE\s+LA\s+PROVINCIA\s+DE\s+BUENOS\s+AIRES|POLIC[IÍ]A\s+BONAERENSE", "Policía de la Provincia de Buenos Aires"),
)
STATUSES = {"BORRADOR", "REVISION", "APROBACION"}
TRANSITIONS = {
    "BORRADOR": {"REVISION"},
    "REVISION": {"APROBACION"},
    "APROBACION": set(),
}


def brand_code(name: str | None) -> str:
    return official_brand_code(name)


def _seizure_template_asset(filename: str) -> Path:
    """Devuelve un recurso empaquetado, incluso cuando /app/assets es un volumen."""
    packaged = PACKAGED_TEMPLATE_DIR / filename
    return packaged if packaged.exists() else TEMPLATE_DIR / filename


def get_report(db: Session, report_id: int) -> SeizureReport:
    report = db.query(SeizureReport).filter_by(id=report_id).first()
    if not report:
        raise HTTPException(404, "Informe de allanamiento no encontrado")
    return report


def list_reports(db, *, search=None, status=None, brand_id=None, country=None, skip=0, limit=20):
    query = db.query(SeizureReport)
    if search:
        value = f"%{search.strip()}%"
        query = query.filter(or_(SeizureReport.internal_reference.ilike(value), SeizureReport.client_case_number.ilike(value)))
    if status:
        query = query.filter(SeizureReport.status == status)
    if brand_id:
        query = query.outerjoin(SeizureReportBrand).filter(or_(
            SeizureReport.brand_id == brand_id, SeizureReportBrand.brand_id == brand_id,
        )).distinct()
    if country:
        query = query.filter(SeizureReport.country == country)
    total = query.count()
    items = query.order_by(SeizureReport.updated_at.desc()).offset(skip).limit(limit).all()
    return {"items": items, "total": total}


def audit_event(db: Session, report_id: int, user_id: int, action: str, *,
                entity_type: str = "report", entity_id: int | None = None, details=None):
    row = SeizureAuditEvent(
        report_id=report_id, user_id=user_id, action=action,
        entity_type=entity_type, entity_id=entity_id,
        details=json.dumps(details, ensure_ascii=False, default=str) if details is not None else None,
    )
    db.add(row)
    return row


def apply_payload(db: Session, report: SeizureReport, data, user_id: int):
    is_new = report.id is None
    data.report_type = normalize_report_type(data.report_type)
    scalar = data.model_dump(exclude={"targets", "products", "brand_names"})
    if not scalar.get("internal_reference") or scalar["internal_reference"].strip().casefold() in {"n/a", "na"}:
        scalar["internal_reference"] = None
    requested_names = []
    seen_names = set()
    for raw_name in data.brand_names:
        name = raw_name.strip()
        key = name.casefold()
        if name and key not in seen_names:
            requested_names.append(name)
            seen_names.add(key)
    selected_catalogue = None
    if data.brand_id:
        selected_catalogue = db.get(Brand, data.brand_id)
        if not selected_catalogue:
            raise HTTPException(422, "La marca seleccionada no existe")
        if selected_catalogue.nombre.casefold() not in seen_names:
            requested_names.insert(0, selected_catalogue.nombre)
            seen_names.add(selected_catalogue.nombre.casefold())
    catalogue = db.query(Brand).all() if requested_names else []
    catalogue_by_name = {item.nombre.casefold(): item for item in catalogue}
    resolved = [(name, catalogue_by_name.get(name.casefold())) for name in requested_names]
    primary_name, primary_brand = resolved[0] if resolved else (None, None)
    scalar["brand_id"] = primary_brand.id if primary_brand else None
    scalar["brand_name"] = primary_name
    scalar["brand_code"] = ((data.brand_code or brand_code(primary_name)).upper() if primary_name else None)
    for key, value in scalar.items():
        setattr(report, key, value)
    report.targets[:] = [SeizureTarget(**target.model_dump()) for target in data.targets]
    # La restricción única es (report_id, brand_name). En una actualización,
    # PostgreSQL puede recibir los INSERT antes que los DELETE pendientes de la
    # colección y rechazar marcas que ya pertenecían al informe. Eliminamos y
    # confirmamos esa colección antes de volver a crearla.
    if not is_new:
        db.query(SeizureReportBrand).filter(
            SeizureReportBrand.report_id == report.id
        ).delete(synchronize_session=False)
        db.flush()
        db.expire(report, ["report_brands"])
    report.report_brands = [
        SeizureReportBrand(brand_id=item.id if item else None, brand_name=name)
        for name, item in resolved
    ]
    report.products[:] = [SeizureProduct(**product.model_dump()) for product in data.products]
    report.seized_goods_total = sum(product.quantity for product in data.products)
    if is_new:
        db.add(report)
        db.flush()
        db.add(SeizureHistory(report_id=report.id, to_status="BORRADOR", comment="Borrador creado", user_id=user_id))
    audit_event(db, report.id, user_id, "REPORT_CREATED" if is_new else "REPORT_UPDATED", details={
        "targets": len(data.targets), "products": len(data.products), "brands": requested_names,
        "seized_goods_total": report.seized_goods_total,
    })
    db.commit(); db.refresh(report)
    return report


def transition(db, report, target, comment, user):
    target = target.upper()
    if target not in STATUSES or target not in TRANSITIONS.get(report.status, set()):
        raise HTTPException(409, f"Transición no permitida: {report.status} → {target}")
    if target in {"REVISION", "APROBACION"}:
        missing = []
        photos = [row for row in report.files if row.kind == "photo"]
        documents = [row for row in report.files if row.kind == "document"]
        if not photos: missing.append("fotografías de la operación")
        if not documents: missing.append("acta o documentación policial")
        if not report.targets: missing.append("domicilio u objetivo")
        if not report.products or report.seized_goods_total <= 0: missing.append("cantidades incautadas")
        if missing:
            raise HTTPException(409, "Información pendiente: " + ", ".join(missing))
    old = report.status
    report.status = target
    db.add(SeizureHistory(report_id=report.id, from_status=old, to_status=target, comment=comment, user_id=user.id))
    audit_event(db, report.id, user.id, "STATUS_CHANGED", details={"from": old, "to": target, "comment": comment})
    if target == "APROBACION" and not report.internal_reference:
        report.internal_reference, report.brand_code = assign_reference(
            db, report.report_type, report.brand_name or report.client_name,
            brand_code_value=report.brand_code,
        )
    db.commit(); db.refresh(report)
    return report


async def store_upload(db, report, upload: UploadFile, kind: str, user_id: int, position: int = 0):
    allowed = {"photo": {"image/jpeg", "image/png", "image/webp"}, "document": {"application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}}
    if upload.content_type not in allowed[kind]:
        raise HTTPException(415, f"Formato no permitido: {upload.content_type}")
    content = await upload.read()
    if not content or len(content) > 20 * 1024 * 1024:
        raise HTTPException(413, "El archivo debe pesar entre 1 byte y 20 MB")
    suffix = Path(upload.filename or "file").suffix.lower()
    stored = f"{report.id}_{uuid.uuid4().hex}{suffix}"
    target = STORAGE / stored
    target.write_bytes(content)
    if kind == "photo":
        try:
            with Image.open(target) as image: image.verify()
        except Exception:
            target.unlink(missing_ok=True); raise HTTPException(415, "La imagen no es válida")
    elif upload.content_type == "application/pdf":
        try:
            PdfReader(BytesIO(content))
        except Exception:
            target.unlink(missing_ok=True); raise HTTPException(415, "El PDF no es válido")
    elif not zipfile.is_zipfile(BytesIO(content)):
        target.unlink(missing_ok=True); raise HTTPException(415, "El documento Word no es válido")
    row = SeizureFile(report_id=report.id, kind=kind, original_name=Path(upload.filename or "archivo").name,
                      stored_name=stored, mime_type=upload.content_type, size_bytes=len(content), position=position,
                      uploaded_by=user_id, document_type="ACTA_POLICIAL" if kind == "document" else None)
    db.add(row); db.flush()
    audit_event(db, report.id, user_id, "FILE_UPLOADED", entity_type="file", entity_id=row.id,
                details={"kind": kind, "name": row.original_name, "size_bytes": row.size_bytes})
    db.commit(); db.refresh(row)
    return row


def extract_police_pdf(path_or_bytes) -> dict:
    reader = PdfReader(path_or_bytes)
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    clean_text = extracted.replace("\r", "\n")
    clean_text = re.sub(r"[ \t]+", " ", clean_text)

    labels = (
        r"ASUNTO|MAGISTRADO(?:\s+(?:INTERVENTOR|INTERVINIENTE))?|CAUSA|CAR[ÁA]TULA|FECHA(?:\s+DE\s+LA\s+OPERACI[ÓO]N)?|"
        r"DETENIDOS?|IMPUTADOS?|INVESTIGADOS?|DOMICILIO|LUGAR(?:ES)?|PERSONAL(?:\s+AFECTADO)?|"
        r"UNIDAD|DIVISI[ÓO]N|ORGANISMOS?(?:\s+(?:ACTUANTES|INTERVINIENTES?))?|"
        r"FUERZAS?\s+INTERVINIENTES?|INTERVINIENTES?|INTERVIENEN?|"
        r"RECURSOS|ELEMENTOS\s+SECUESTRADOS|SECUESTRO|"
        r"(?:BREVE\s+)?RESE[ÑN]A|VALOR\s+ESTIMATIVO|OBSERVACIONES|ESTADO|FIRMA"
    )

    def one(pattern, flags=re.I):
        match = re.search(pattern, clean_text, flags)
        return " ".join(match.group(1).split()).strip(" .-") if match else None

    def section(label):
        match = re.search(rf"(?:^|\n)\s*(?:{label})\s*:\s*(.*?)(?=\n\s*(?:{labels})\s*:|$)", clean_text, re.I | re.S)
        if not match:
            return None
        lines = [" ".join(line.split()).strip() for line in match.group(1).splitlines()]
        return "\n".join(line for line in lines if line).strip()

    def compact(value):
        return " ".join((value or "").split()).strip(" .-") or None

    date_text = compact(section(r"FECHA(?:\s+DE\s+LA\s+OPERACI[ÓO]N)?"))
    iso_date = None
    numeric_date = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", date_text or "")
    if numeric_date:
        iso_date = f"{numeric_date.group(3)}-{int(numeric_date.group(2)):02d}-{int(numeric_date.group(1)):02d}"

    places_text = section(r"(?:LUGAR(?:ES)?|DOMICILIO)")
    places = []
    if places_text:
        numbered = re.findall(r"(?:^|\n)\s*\d+[).]\s*(.+?)(?=\n\s*\d+[).]|$)", places_text, re.S)
        places = [" ".join(value.split()) for value in numbered] if numbered else [" ".join(places_text.split())]

    infringers = compact(section(r"(?:IMPUTADOS?|DETENIDOS?|INVESTIGADOS?)"))
    court = (
        compact(section(r"MAGISTRADO(?:\s+(?:INTERVENTOR|INTERVINIENTE))?"))
        or one(r"JUZGADO\s*:\s*([^\n]+)")
        or one(r"(?:^|\n)\s*INTERVIENE(?:N)?\s*:?\s*((?:JUZGADO|FISCAL[IÍ]A|TRIBUNAL)\b[^\n]+)")
    )
    seizure = section(r"(?:ELEMENTOS\s+SECUESTRADOS|SECUESTRO)")
    # La reseña conserva sus saltos y puntuación porque se reproduce como
    # cuerpo principal del informe policial en el Word.
    summary = section(r"(?:BREVE\s+)?RESE[ÑN]A")
    subject = compact(section(r"ASUNTO"))
    intervening_section = section(
        r"(?:ORGANISMOS?(?:\s+(?:ACTUANTES|INTERVINIENTES?))?|FUERZAS?\s+INTERVINIENTES?|INTERVINIENTES?)"
    )
    explicit_unit = compact(section(r"(?:UNIDAD|DIVISI[ÓO]N)"))
    intervening_lines = []
    for raw_line in (intervening_section or "").splitlines():
        line = raw_line.strip(" .-")
        if not line:
            continue
        # El salto de línea separa las entradas. Los guiones internos forman
        # parte del nombre o dependencia informada y deben conservarse.
        intervening_lines.append(line)
    intervening_agencies = " / ".join(intervening_lines) or None

    merchandise_terms = r"zapatillas?|calzados?|buzos?|remeras?|camperones?|shorts?|camisetas?|prendas?|pantalones?|gorras?|medias?|camisas?|vestidos?|chaquetas?|bolsos?|carteras?"
    product_rows = []
    other_items = []
    for line in (seizure or "").splitlines():
        normalized_line = " ".join(line.split()).strip(" .-")
        quantity_match = re.search(r"\(\s*([\d.]+)\s*\)\s+(.+)$", normalized_line)
        if not quantity_match:
            continue
        quantity = int(quantity_match.group(1).replace(".", ""))
        item = quantity_match.group(2).strip(" .-")
        if re.search(merchandise_terms, item, re.I):
            product_rows.append((quantity, item))
        else:
            other_items.append(f"{quantity} {item}")

    known_brands = sorted({name.title() for name in BRAND_CODES} | {"Nike", "Jordan", "Adidas", "Levis", "Converse", "Gucci", "Dior", "Versace", "Diesel", "Boss"}, key=len, reverse=True)
    brand_source = " ".join(filter(None, [seizure, summary, subject]))
    identified_brands = [name for name in known_brands if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", brand_source, re.I)]
    amount = sum(quantity for quantity, _ in product_rows) or None
    detected_brand_label = ", ".join(identified_brands) or "Pendiente de clasificación por cliente"
    products = [{
        "brand_name": detected_brand_label,
        "category": item,
        "description": f"Mercadería informada en el acta. Marcas mencionadas: {', '.join(identified_brands) or 'sin detalle'}",
        "quantity": quantity, "unit": "unidades",
        "notes": "Distribución por cliente o marca pendiente de validación humana",
    } for quantity, item in product_rows]
    if not products and seizure:
        amount_match = re.search(r"\(\s*([\d.]+)\s*\)", seizure)
        if amount_match:
            amount = int(amount_match.group(1).replace(".", ""))
            products = [{
                "brand_name": detected_brand_label, "category": "Mercadería incautada",
                "description": f"Total informado por el acta. Marcas mencionadas: {', '.join(identified_brands) or 'sin detalle'}",
                "quantity": amount, "unit": "unidades",
                "notes": "Cantidad total confirmada; distribución por cliente pendiente de validación humana",
            }]

    heading_lines = [" ".join(line.split()) for line in clean_text.splitlines()[:30] if line.strip()]
    institution_lines = [line for line in heading_lines if re.fullmatch(r"(?:SUPERINTENDENCIA|DIRECCI[ÓO]N|DEPARTAMENTO|DIVISI[ÓO]N|DCC|DIC).{0,120}", line, re.I)]
    # Dirección, Departamento y División describen la unidad orgánica, no la
    # fuerza. El organismo sólo se completa cuando está nombrado expresamente.
    # Cuando el parte enumera expresamente los organismos, ese bloque tiene
    # prioridad y se conserva completo, aunque incluya entidades no policiales.
    # Si no existe la sección, el campo queda vacío para revisión humana.
    police_agency = intervening_agencies
    police_unit = explicit_unit or (" / ".join(dict.fromkeys(institution_lines)) or None)

    city = province = None
    location_match = re.search(r"localidad\s+de\s+([^,]+),\s*(?:Provincia(?:\s+de)?\s+)?([^,.]+)", places_text or subject or "", re.I)
    if location_match:
        city, province = " ".join(location_match.group(1).split()), " ".join(location_match.group(2).split())
    elif re.search(r"\bCABA\b", places_text or "", re.I):
        city = province = "CABA"

    judge = prosecution = prosecutor = None
    if court:
        judge_matches = re.findall(r"a\s+cargo\s+del?\s+(?:Dr[a]?\.?\s+)?([^,.-]+)", court, re.I)
        judge = " ".join(judge_matches[0].split()) if judge_matches else None
        prosecutor = " ".join(judge_matches[1].split()) if len(judge_matches) > 1 else None
        prosecution_match = re.search(r"(Secretar[íi]a\s+(?:N[°ºo.]*)?\s*\d+)", court, re.I)
        prosecution = " ".join(prosecution_match.group(1).split()) if prosecution_match else None

    case_number = compact(section(r"CAUSA")) or one(r"\b(OS\s*\d+/\d{4})\b")
    action_type = "Allanamiento" if re.search(r"allanamiento", " ".join(filter(None, [subject, summary])), re.I) else None
    origin = None
    if re.search(r"\bdenuncia\b", clean_text, re.I):
        origin = "Denuncia"
    elif re.search(r"\boficio\b", clean_text, re.I):
        origin = "Oficio"
    target_details = [{
        "establishment_name": None, "address": address, "city": city, "province": province,
        "country": "Argentina", "investigated_party": infringers, "description": subject,
    } for address in places]

    return {
        "operation_date_text": date_text, "operation_date": iso_date,
        "case_origin": origin, "case_subject": subject, "action_type": action_type,
        "police_agency": police_agency, "police_unit": police_unit,
        "intervening_agencies_explicit": bool(intervening_agencies),
        "court": court, "judge": judge, "prosecution": prosecution, "prosecutor": prosecutor,
        "court_case_number": case_number, "targets": places, "target_details": target_details,
        "city": city, "province": province, "infringers": infringers,
        "seized_goods_total": amount, "identified_brands": identified_brands, "products": products,
        "other_seized_items": other_items,
        "authorities_notes": "; ".join(other_items) if other_items else None,
        "operation_summary": summary, "background": summary,
        "media_impact": "N/A" if re.search(r"negativo\s+medios", clean_text, re.I) else None,
        "raw_text": clean_text[:20000],
    }


def extract_image_text(content: bytes) -> str:
    """OCR local; no envía evidencia a servicios externos."""
    with Image.open(BytesIO(content)) as image:
        image = image.convert("RGB")
        return pytesseract.image_to_string(image, lang="spa+eng", config="--psm 6")


def identify_police_agency_from_images(contents: list[bytes]) -> dict:
    texts = []
    for content in contents:
        try:
            texts.append(extract_image_text(content))
        except Exception:
            continue
    observed = "\n".join(texts)
    for pattern, name in POLICE_AGENCIES:
        if re.search(pattern, observed, re.I):
            return {"police_agency": name, "evidence": "photo_ocr", "text_detected": observed[:4000]}
    return {"police_agency": None, "evidence": None, "text_detected": observed[:4000]}


def parse_product_list_text(text: str) -> list[dict]:
    canonical = sorted(
        {name.title() for name in BRAND_CODES} |
        {"Nike", "Jordan", "Adidas", "Converse", "Levis", "Victoria's Secret", "Tommy Hilfiger", "Under Armour", "Calvin Klein", "New Era", "Chanel"},
        key=len, reverse=True,
    )
    canonical = [
        {"victoria's secret": "Victoria's Secret", "mlb": "MLB", "nba": "NBA"}.get(name.casefold(), name)
        for name in canonical
    ]
    code_to_brand = {}
    for name in canonical:
        code = BRAND_CODES.get(name.casefold())
        if code:
            code_to_brand[code.upper()] = name
    rows = []
    for source_line in text.splitlines():
        line = " ".join(source_line.replace("—", "-").split()).strip(" ,;-")
        if not line:
            continue
        code_match = re.match(r"^([A-Z]{2,3})\s+(.+)$", line, re.I)
        coded_brand = code_to_brand.get(code_match.group(1).upper()) if code_match else None
        if coded_brand:
            line = code_match.group(2).strip()
        line = re.sub(r"^NEW\s+ERA(?=\d)", "New Era ", line, flags=re.I)
        line = re.sub(r"^VICTORIAS?\s+SECRETS?", "Victoria's Secret", line, flags=re.I)
        line = re.sub(r"^MBL(?=\s|,|;|-|\d)", "MLB", line, flags=re.I)
        brand = next((name for name in canonical if re.match(rf"^{re.escape(name)}(?=\s|,|;|-|\d)", line, re.I)), None)
        brand = brand or coded_brand
        if not brand:
            continue
        remainder = line[len(brand):] if line.casefold().startswith(brand.casefold()) else ""
        numbers = re.findall(r"(?<![A-Za-z])([\d.]+|\?+)", remainder)
        if not numbers or not numbers[0].replace(".", "").isdigit():
            rows.append({"brand_name": brand, "quantity": 0, "proposed_fees": None})
            continue
        quantity = int(numbers[0].replace(".", ""))
        fee_match = re.search(r"(?:U(?:S)?D|US\$|U\$S|\$)\s*([^\s,;-]+)", remainder, re.I)
        fee = fee_match.group(1) if fee_match else None
        fee_digits = fee.replace(".", "").replace(",", "") if fee else ""
        if "?" in remainder or not fee_digits.isdigit() or int(fee_digits) < 100:
            fee = None
        if brand.casefold() == "mlb":
            brand = "MLB"
        elif brand.casefold() == "nba":
            brand = "NBA"
        rows.append({"brand_name": brand, "quantity": quantity, "proposed_fees": fee})
    unique = {}
    for row in rows:
        unique[row["brand_name"].casefold()] = row
    return list(unique.values())


def _photo_dimensions(path, max_w, max_h):
    with Image.open(path) as image: w, h = image.size
    scale = min(max_w / w, max_h / h)
    return w * scale, h * scale


def _report_values(report):
    targets = "; ".join(filter(None, [f"{t.establishment_name + ': ' if t.establishment_name else ''}{t.address}" for t in report.targets])) or "N/A"
    breakdown = {}
    for product in getattr(report, "products", []):
        key = product.client_name or product.brand_name or "Pending classification"
        breakdown[key] = breakdown.get(key, 0) + (product.quantity or 0)
    breakdown_text = "; ".join(f"{name}: {quantity}" for name, quantity in breakdown.items()) or "N/A"
    products = list(getattr(report, "products", []) or [])
    fee_text = (
        " · ".join(f"{product.brand_name}: {product.notes or 'N/A'}" for product in products)
        if len(products) > 1
        else f"{report.currency or ''} {report.proposed_fees or 'N/A'}".strip()
    )
    return [
        ("TARGET", ", ".join(getattr(report, "brand_names", []) or []) or report.client_name or "N/A"), ("DATE", report.operation_date.strftime("%d/%m/%Y") if report.operation_date else "N/A"),
        ("ORIGIN OF THE CASE", report.case_origin or "N/A"), ("SEARCH AND WARRANT TARGETS", targets),
        ("AMOUNT OF SEIZED GOODS", str(report.seized_goods_total)), ("SEIZED GOODS BY CLIENT / BRAND", breakdown_text),
        ("INFRINGERS", "; ".join(t.investigated_party for t in report.targets if t.investigated_party) or "N/A"),
        ("LAW ENFORCEMENT AGENCY", " - ".join(filter(None, [report.police_agency, report.police_unit])) or "N/A"),
        ("JUDGE", " - ".join(filter(None, [report.court, report.judge])) or "N/A"), ("MEDIA", report.media_impact or "N/A"),
        ("POLITICS", report.political_impact or "N/A"), ("PROPOSED FEES", fee_text),
        ("INTERNAL REFERENCE", report.internal_reference or "N/A"),
    ]


def _photo_caption(photo, index, fallback_brand=None):
    parts = [getattr(photo, "caption", None), getattr(photo, "brand_name", None), getattr(photo, "establishment", None)]
    value = " · ".join(value for value in parts if value) or fallback_brand or f"Evidence {index + 1}"
    return value.title() if value.islower() else value


def _report_sections(report):
    values = dict(_report_values(report))
    return [
        ("TARGET", [(key, values[key]) for key in ("DATE", "ORIGIN OF THE CASE", "SEARCH AND WARRANT TARGETS", "AMOUNT OF SEIZED GOODS", "SEIZED GOODS BY CLIENT / BRAND", "INFRINGERS")]),
        ("AUTHORITIES", [(key, values[key]) for key in ("LAW ENFORCEMENT AGENCY", "JUDGE")]),
        ("EXTERNAL IMPACT", [(key, values[key]) for key in ("MEDIA", "POLITICS")]),
        ("INTERNAL INFORMATION", [(key, values[key]) for key in ("PROPOSED FEES", "INTERNAL REFERENCE")]),
    ]


def _shade_cell(cell, fill):
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), fill)
    cell._tc.get_or_add_tcPr().append(shading)


def _set_cell_text(cell, text, *, color="000000", bold=False, size=9):
    cell.text = ""
    paragraph = cell.paragraphs[0]
    run = paragraph.add_run(str(text))
    run.bold = bold
    run.font.name = "Arial"
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor.from_string(color)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def _set_report_body(cell, text):
    cell.text = ""
    lines = str(text or "N/A").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for index, raw_line in enumerate(lines):
        line = raw_line.rstrip()
        paragraph = cell.paragraphs[0] if index == 0 else cell.add_paragraph()
        paragraph.paragraph_format.space_before = Pt(0)
        paragraph.paragraph_format.space_after = Pt(6 if line else 3)
        paragraph.paragraph_format.line_spacing = 1.12
        run = paragraph.add_run(line)
        run.font.name = "Arial"
        run.font.size = Pt(12)
        normalized = line.strip()
        run.bold = bool(
            normalized.endswith(":")
            or re.match(r"^(?:FECHA DE LA OPERACI[ÓO]N|LUGAR|FUERZA INTERVINIENTE|OBJETO|OBSERVACIONES DE CAMPO)\s*:", normalized, re.I)
        )
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP


def _prevent_row_split(row):
    properties = row._tr.get_or_add_trPr()
    cant_split = OxmlElement("w:cantSplit")
    properties.append(cant_split)


def _repeat_table_header(row):
    properties = row._tr.get_or_add_trPr()
    header = OxmlElement("w:tblHeader")
    header.set(qn("w:val"), "true")
    properties.append(header)


def _add_corporate_table(doc, title, rows):
    table = doc.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    table.autofit = False
    table.columns[0].width, table.columns[1].width = Cm(5.2), Cm(11.5)
    heading = table.rows[0].cells
    heading[0].merge(heading[1])
    _set_cell_text(heading[0], title, color="1E4459", bold=True, size=11)
    for label, value in rows:
        cells = table.add_row().cells
        cells[0].width, cells[1].width = Cm(5.2), Cm(11.5)
        _shade_cell(cells[0], "1E4459")
        _set_cell_text(cells[0], label, color="FFFFFF", bold=True)
        _set_cell_text(cells[1], value, size=9)
    doc.add_paragraph().paragraph_format.space_after = Pt(1)
    return table


def generate_pdf(report, user_id):
    output = STORAGE / f"report_{report.id}_{uuid.uuid4().hex}.pdf"
    styles = getSampleStyleSheet(); styles.add(ParagraphStyle(name="Section", parent=styles["Heading1"], textColor=NAVY, fontSize=18, spaceAfter=14))
    styles.add(ParagraphStyle(name="WhiteBody", parent=styles["BodyText"], textColor=colors.white))
    styles.add(ParagraphStyle(name="WhiteLabel", parent=styles["BodyText"], textColor=colors.white, fontName="Helvetica-Bold"))
    disclaimer = Table([
        [Paragraph("COMPLIANCE DISCLAIMER", styles["WhiteLabel"])],
        [Paragraph(DISCLAIMER, styles["WhiteBody"])],
    ], colWidths=[16.7*cm])
    disclaimer.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#C00000")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#8A0000")),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story = [Spacer(1, 1), PageBreak(), Paragraph(f"{report.country.upper()} – SEIZURE REPORT", styles["Section"]), disclaimer, Spacer(1, .5*cm)]
    rows, section_rows = [], []
    for title, values in _report_sections(report):
        section_rows.append(len(rows)); rows.append([Paragraph(f"<b>{title}</b>", styles["BodyText"]), ""])
        rows.extend([Paragraph(key, styles["WhiteLabel"]), Paragraph(str(value), styles["BodyText"])] for key, value in values)
    table = Table(rows, colWidths=[5.2*cm, 11.5*cm], repeatRows=0)
    commands = [("GRID",(0,0),(-1,-1),.35,colors.HexColor("#9aa7b7")),("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6)]
    for index in range(len(rows)):
        if index in section_rows:
            commands += [("SPAN",(0,index),(1,index)),("TEXTCOLOR",(0,index),(1,index),NAVY),("BACKGROUND",(0,index),(1,index),colors.white)]
        else:
            commands += [("BACKGROUND",(0,index),(0,index),NAVY),("TEXTCOLOR",(0,index),(0,index),colors.white)]
    table.setStyle(TableStyle(commands)); story += [table]
    def pdf_section_heading(title):
        heading = Table([[Paragraph(title, styles["WhiteLabel"])]], colWidths=[16.7*cm])
        heading.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), NAVY), ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
            ("BOX", (0, 0), (-1, -1), .5, NAVY), ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        return heading
    photos = [f for f in report.files if f.kind == "photo" and f.include_in_report]
    if photos: story += [PageBreak(), pdf_section_heading("PICTURES OF THE OPERATION"), Spacer(1, .35*cm)]
    for index, photo in enumerate(photos):
        path = STORAGE/photo.stored_name; w,h = _photo_dimensions(path, 16.5*cm, 10.5*cm)
        story += [RLImage(str(path), width=w, height=h), Paragraph(_photo_caption(photo, index), styles["BodyText"]), Spacer(1,.4*cm)]
        if index % 2 == 1 and index < len(photos)-1: story.append(PageBreak())
    documents = [f for f in report.files if f.kind == "document" and f.include_in_report and f.mime_type == "application/pdf"]
    if documents:
        story += [PageBreak(), pdf_section_heading("POLICE REPORT: CONFIDENTIAL"), Spacer(1, .4*cm),
                  Paragraph("The original police documentation is attached in full on the following pages.", styles["BodyText"])]
    def page_decoration(canvas, document):
        canvas.saveState()
        cover = _seizure_template_asset("cover.png")
        if document.page == 1 and cover.exists():
            canvas.drawImage(str(cover), 0, 0, width=A4[0], height=A4[1], preserveAspectRatio=True, mask="auto")
            canvas.restoreState()
            return
        logo = _seizure_template_asset("cba-logo.png")
        if logo.exists():
            canvas.drawImage(str(logo), 1.7*cm, A4[1]-1.2*cm, width=3.6*cm, height=.8*cm, preserveAspectRatio=True, mask="auto")
        canvas.setFillColor(NAVY); canvas.setFont("Helvetica", 7)
        canvas.drawRightString(A4[0]-1.7*cm, A4[1]-.85*cm, "CORPORATE INTELLIGENCE IN ACTION")
        canvas.setStrokeColor(CYAN); canvas.setLineWidth(1)
        canvas.line(1.7*cm, 1.25*cm, A4[0]-1.7*cm, 1.25*cm)
        canvas.setFillColor(NAVY); canvas.setFont("Helvetica-Bold", 8)
        canvas.drawString(1.7*cm, .8*cm, "CONFIDENTIAL REPORT")
        canvas.drawRightString(A4[0]-1.7*cm, .8*cm, f"PAGE {document.page}")
        canvas.restoreState()
    SimpleDocTemplate(str(output), pagesize=A4, rightMargin=1.7*cm,leftMargin=1.7*cm,topMargin=1.6*cm,bottomMargin=1.6*cm, title="Seizure Report").build(story, onFirstPage=page_decoration, onLaterPages=page_decoration)
    if documents:
        merged = PdfWriter();
        for page in PdfReader(str(output)).pages: merged.add_page(page)
        for attachment in documents:
            for page in PdfReader(str(STORAGE/attachment.stored_name)).pages: merged.add_page(page)
        with output.open("wb") as stream: merged.write(stream)
    return output


def generate_docx(report, user_id):
    # `assets` se monta como volumen en producción y puede ocultar los archivos
    # incluidos en la imagen. La plantilla canónica vive fuera de ese volumen;
    # la ruta anterior se conserva para instalaciones existentes.
    template = PACKAGED_TEMPLATE_DIR / "corporate-seizure-report.docx"
    if not template.exists():
        template = TEMPLATE_DIR / "corporate-seizure-report.docx"
    if not template.exists():
        raise HTTPException(500, "No se encontró la plantilla corporativa del Seizure Report")

    output = STORAGE / f"report_{report.id}_{uuid.uuid4().hex}.docx"
    doc = Document(str(template))
    values = dict(_report_values(report))

    for paragraph in doc.paragraphs:
        if "SEIZURE REPORT" in paragraph.text.upper():
            paragraph.text = f"{(report.country or 'ARGENTINA').upper()} – SEIZURE REPORT"
            break

    target = doc.tables[1]
    for row, key in enumerate(("DATE", "ORIGIN OF THE CASE", "SEARCH AND WARRANT TARGETS", "AMOUNT OF SEIZED GOODS", "INFRINGERS"), 1):
        _set_cell_text(target.cell(row, 1), values[key])

    authorities = doc.tables[2]
    for row, key in ((1, "LAW ENFORCEMENT AGENCY"), (2, "JUDGE"), (5, "MEDIA"), (6, "POLITICS")):
        _set_cell_text(authorities.cell(row, 1), values[key])

    internal = doc.tables[3]
    _set_cell_text(internal.cell(1, 1), values["PROPOSED FEES"])
    _set_cell_text(internal.cell(2, 1), values["INTERNAL REFERENCE"])

    products = list(getattr(report, "products", []) or [])
    product_table = doc.add_table(rows=2, cols=4)
    product_table.style = "Table Grid"
    product_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    product_table.autofit = False
    widths = (Cm(4.15), Cm(4.15), Cm(4.15), Cm(4.15))
    for row in product_table.rows:
        for cell, width in zip(row.cells, widths):
            cell.width = width
        _prevent_row_split(row)
    title_cells = product_table.rows[0].cells
    title_cells[0].merge(title_cells[-1])
    _shade_cell(title_cells[0], "1E4459")
    _set_cell_text(title_cells[0], "SEIZED PRODUCTS", color="FFFFFF", bold=True, size=12)
    for cell, label in zip(product_table.rows[1].cells, ("BRAND / CLIENT", "DETAIL", "QUANTITY", "PROPOSED FEES")):
        _shade_cell(cell, "1E4459")
        _set_cell_text(cell, label, color="FFFFFF", bold=True, size=10)
    _repeat_table_header(product_table.rows[0])
    _repeat_table_header(product_table.rows[1])
    if products:
        for product in products:
            cells = product_table.add_row().cells
            _prevent_row_split(product_table.rows[-1])
            detail = " · ".join(filter(None, [product.category, product.description])) or "Mercadería incautada"
            fee = product.notes or (values["PROPOSED FEES"] if len(products) == 1 else "N/A")
            row_values = (product.client_name or product.brand_name or "N/A", detail, f"{product.quantity or 0} {product.unit or 'unidades'}", fee)
            for cell, value in zip(cells, row_values):
                _set_cell_text(cell, value, size=10)
    else:
        cells = product_table.add_row().cells
        cells[0].merge(cells[-1])
        _set_cell_text(cells[0], "N/A")
    # Se mantiene el flujo del Word original: la tabla aprovecha el espacio
    # disponible y Word pasa filas completas a la página siguiente.
    product_spacer = doc.add_paragraph()
    product_spacer.paragraph_format.space_before = Pt(2)
    product_spacer.paragraph_format.space_after = Pt(2)
    internal._tbl.addnext(product_spacer._p)
    product_spacer._p.addnext(product_table._tbl)

    photo_table = next(table for table in doc.tables if table.cell(0, 0).text.strip() == "PICTURES OF THE OPERATION")
    photo_cell = photo_table.cell(1, 0)
    photo_cell.text = ""
    photos = [item for item in report.files if item.kind == "photo" and item.include_in_report]
    if not photos:
        _set_cell_text(photo_cell, "N/A")
    report_brands = list(getattr(report, "brand_names", []) or [])
    for index, photo in enumerate(photos):
        path = STORAGE / photo.stored_name
        width, height = _photo_dimensions(path, 15.8 * cm, 19.0 * cm)
        paragraph = photo_cell.paragraphs[0] if index == 0 else photo_cell.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.add_run().add_picture(str(path), width=Cm(width / cm), height=Cm(height / cm))
        fallback_brand = report_brands[0] if len(report_brands) == 1 else None
        caption = photo_cell.add_paragraph(_photo_caption(photo, index, fallback_brand))
        caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if index < len(photos) - 1:
            caption.paragraph_format.page_break_after = True

    police_table = next(table for table in doc.tables if table.cell(0, 0).text.strip() == "POLICE REPORT: CONFIDENTIAL")
    police_table.cell(0, 0).paragraphs[0].paragraph_format.page_break_before = True
    summary_cell = police_table.cell(1, 0)
    report_body = getattr(report, "operation_summary", None)
    # Los borradores creados con versiones anteriores guardaron la reseña en
    # una sola línea. Recuperamos su formato desde el PDF original al generar.
    if report_body and "\n" not in report_body:
        source_document = next((item for item in report.files if item.kind == "document" and item.mime_type == "application/pdf"), None)
        if source_document:
            try:
                extracted_body = extract_police_pdf(STORAGE / source_document.stored_name).get("operation_summary")
                if extracted_body:
                    report_body = extracted_body
            except Exception:
                pass
    _set_report_body(summary_cell, report_body or "N/A")
    _repeat_table_header(police_table.rows[0])
    doc.save(output)
    return output


def register_version(db, report, path, fmt, user_id):
    version = (db.query(SeizureDocumentVersion).filter_by(report_id=report.id, format=fmt).count() + 1)
    row=SeizureDocumentVersion(report_id=report.id,version=version,format=fmt,stored_name=path.name,generated_by=user_id)
    db.add(row); db.flush()
    audit_event(db, report.id, user_id, "DOCUMENT_GENERATED", entity_type="document_version", entity_id=row.id,
                details={"format": fmt, "version": version, "file": path.name})
    db.commit()
    return row
