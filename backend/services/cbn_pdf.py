"""
Generador de Reporte PDF Oficial CBN International.
Replica la estructura visual del documento institucional 025-26-IN-PU.
"""
import os
import io
import json
import html
import requests
from PIL import Image as PILImage
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer,
    Table, TableStyle, Image as RLImage, PageBreak
)
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.units import cm
from sqlalchemy.orm import Session
from sqlalchemy import or_

# ── CBN Corporate Palette ────────────────────────────────────────────────────
CBN_NAVY      = colors.HexColor("#0A2540")
CBN_DARK      = colors.HexColor("#0D1B2A")
CBN_ACCENT    = colors.HexColor("#00639B")
CBN_TEXT      = colors.HexColor("#1B1C1D")
CBN_TABLE_BG  = colors.HexColor("#F0F4F9")
CBN_WHITE     = colors.white

ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")


# ── Canvas Decorators ────────────────────────────────────────────────────────

def _draw_cover(canvas, doc):
    """Page 1: Full bleed cover."""
    canvas.saveState()
    w, h = A4

    # Solid navy background
    canvas.setFillColor(CBN_NAVY)
    canvas.rect(0, 0, w, h, fill=1, stroke=0)

    # Decorative wave strokes
    canvas.setStrokeColor(CBN_ACCENT)
    canvas.setLineWidth(1.5)
    for i in range(8):
        y = i * 35
        canvas.bezier(0, y, w * 0.3, y + 250, w * 0.7, y - 250, w, y)
    for i in range(4):
        y = h - i * 45
        canvas.bezier(0, y, w * 0.25, y - 180, w * 0.75, y + 180, w, y)

    # Logo or fallback
    logo = os.path.join(ASSETS_DIR, "cbn_logo.png")
    if os.path.exists(logo):
        canvas.drawImage(logo, 2 * cm, h - 4 * cm, width=6 * cm,
                         preserveAspectRatio=True, mask="auto")
    else:
        canvas.setFillColor(CBN_ACCENT)
        canvas.rect(2 * cm, h - 3.5 * cm, 5.5 * cm, 1.6 * cm, fill=1, stroke=0)
        canvas.setFillColor(CBN_WHITE)
        canvas.setFont("Helvetica-Bold", 18)
        canvas.drawString(2.3 * cm, h - 2.7 * cm, "CBN")
        canvas.setFont("Helvetica", 13)
        canvas.drawString(4.2 * cm, h - 2.7 * cm, "INTERNATIONAL")

    # Tagline
    canvas.setStrokeColor(CBN_ACCENT)
    canvas.line(8.5 * cm, h - 2.8 * cm, w - 2 * cm, h - 2.8 * cm)
    canvas.setFillColor(CBN_WHITE)
    canvas.setFont("Helvetica", 10)
    canvas.drawString(8.7 * cm, h - 2.6 * cm, "CORPORATE INTELLIGENCE IN ACTION")

    # Main titles
    canvas.setFont("Helvetica-Bold", 40)
    canvas.drawString(2 * cm, h / 2 + 2.5 * cm, "INTELLIGENCE")
    canvas.drawString(2 * cm, h / 2 + 0.5 * cm, "REPORT")
    canvas.setFont("Helvetica-Bold", 26)
    canvas.drawString(2 * cm, h / 2 - 2 * cm, "CONFIDENTIAL")

    # IAS badge
    ias_logo = os.path.join(ASSETS_DIR, "ias_logo.png")
    if os.path.exists(ias_logo):
        canvas.drawImage(ias_logo, w - 5 * cm, 2 * cm, width=3 * cm,
                         preserveAspectRatio=True, mask="auto")
    else:
        canvas.setFillColor(CBN_WHITE)
        canvas.roundRect(w - 5 * cm, 1.8 * cm, 3.2 * cm, 1.8 * cm, 4, fill=1, stroke=0)
        canvas.setFillColor(CBN_NAVY)
        canvas.setFont("Helvetica-Bold", 14)
        canvas.drawCentredString(w - 3.4 * cm, 2.5 * cm, "IAS ACCREDITED")

    # Footer certifications
    canvas.setFillColor(colors.HexColor("#AAAAAA"))
    canvas.setFont("Helvetica", 8)
    canvas.drawString(2 * cm, 1.5 * cm, "Certified: ISO 27001 \u2022 ISO 9001")

    canvas.restoreState()


def _draw_header_footer(canvas, doc):
    """Pages 2+: header bar + footer."""
    canvas.saveState()
    w, h = A4

    # Header stripe
    canvas.setFillColor(CBN_NAVY)
    canvas.rect(0, h - 2.8 * cm, w, 2.8 * cm, fill=1, stroke=0)

    logo = os.path.join(ASSETS_DIR, "cbn_logo.png")
    if os.path.exists(logo):
        canvas.drawImage(logo, 1.5 * cm, h - 2.4 * cm, width=3.5 * cm,
                         preserveAspectRatio=True, mask="auto")
    else:
        canvas.setFillColor(CBN_WHITE)
        canvas.setFont("Helvetica-Bold", 14)
        canvas.drawString(1.5 * cm, h - 1.8 * cm, "CBN INTERNATIONAL")

    canvas.setFillColor(CBN_WHITE)
    canvas.setFont("Helvetica", 9)
    canvas.drawRightString(w - 1.5 * cm, h - 1.5 * cm, "CORPORATE INTELLIGENCE IN ACTION")
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawRightString(w - 1.5 * cm, h - 2.0 * cm, "CONFIDENTIAL REPORT")

    # Footer
    canvas.setFillColor(CBN_NAVY)
    canvas.rect(0, 0, w, 2 * cm, fill=1, stroke=0)
    canvas.setFillColor(CBN_WHITE)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(1.5 * cm, 0.8 * cm, "Certified: ISO 27001 \u2022 ISO 9001")
    canvas.drawRightString(w - 1.5 * cm, 0.8 * cm, f"Page {doc.page}")

    ias = os.path.join(ASSETS_DIR, "ias_logo.png")
    if os.path.exists(ias):
        canvas.drawImage(ias, w / 2 - 1 * cm, 0.3 * cm, width=2 * cm,
                         preserveAspectRatio=True, mask="auto")

    canvas.restoreState()


def _draw_final_header_footer(canvas, doc):
    """Compact corporate masthead for the final investigation report."""
    canvas.saveState()
    width, height = A4
    header_height = 2.15 * cm

    canvas.setFillColor(CBN_NAVY)
    canvas.rect(0, height - header_height, width, header_height, fill=1, stroke=0)
    canvas.setFillColor(CBN_WHITE)
    canvas.setFont("Helvetica-Bold", 13)
    canvas.drawString(1.5 * cm, height - 1.35 * cm, "CBN INTERNATIONAL")
    canvas.setFont("Helvetica", 8.5)
    canvas.drawRightString(width - 1.5 * cm, height - 0.95 * cm, "CORPORATE INTELLIGENCE IN ACTION")
    canvas.setFont("Helvetica-Bold", 8.5)
    canvas.drawRightString(width - 1.5 * cm, height - 1.45 * cm, "CONFIDENTIAL REPORT")

    canvas.setStrokeColor(colors.HexColor("#CCCCCC"))
    canvas.setLineWidth(0.5)
    canvas.line(1.5 * cm, 1.35 * cm, width - 1.5 * cm, 1.35 * cm)
    canvas.setFillColor(CBN_TEXT)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(1.5 * cm, 0.95 * cm, "NET HOLMES OSINT | CONFIDENCIAL")
    canvas.drawRightString(width - 1.5 * cm, 0.95 * cm, f"PÁGINA {doc.page}")
    canvas.restoreState()


# ── Styles ───────────────────────────────────────────────────────────────────

def _styles():
    ss = getSampleStyleSheet()
    title = ParagraphStyle("CBNTitle", parent=ss["Heading1"], fontName="Helvetica-Bold",
                           fontSize=16, textColor=CBN_NAVY, spaceAfter=12, spaceBefore=4)
    normal = ParagraphStyle("CBNNormal", parent=ss["Normal"], fontName="Helvetica",
                            fontSize=9, textColor=CBN_TEXT, spaceAfter=4, leading=12)
    bold = ParagraphStyle("CBNBold", parent=normal, fontName="Helvetica-Bold")
    header_white = ParagraphStyle("CBNHeaderWhite", parent=ss["Normal"],
                                  fontName="Helvetica-Bold", fontSize=10,
                                  textColor=CBN_WHITE, alignment=TA_CENTER)
    small = ParagraphStyle("CBNSmall", parent=normal, fontSize=8, textColor=colors.HexColor("#555555"))
    return ss, title, normal, bold, header_white, small


def _section_header_table(text):
    """Returns a full-width navy header bar for a section."""
    _, _, _, _, hw, _ = _styles()
    t = Table([[Paragraph(f"<b>{text}</b>", hw)]], colWidths=[16 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CBN_NAVY),
        ("TEXTCOLOR", (0, 0), (-1, -1), CBN_WHITE),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def _overview_table_style():
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CBN_TABLE_BG),
        ("TEXTCOLOR", (0, 0), (0, -1), CBN_NAVY),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (0, -1), 9),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (1, 0), (1, -1), CBN_TABLE_BG),
        ("TEXTCOLOR", (1, 0), (1, -1), CBN_TEXT),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (1, 0), (1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ])


# ── Image helpers ────────────────────────────────────────────────────────────

def _fetch_image(url, max_w=800, max_h=800, quality=50):
    """Download and compress an image, return BytesIO or None."""
    try:
        r = requests.get(url, timeout=8)
        if r.status_code != 200:
            return None
        img = PILImage.open(io.BytesIO(r.content))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.thumbnail((max_w, max_h), PILImage.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        buf.seek(0)
        return buf
    except Exception:
        return None


def _collect_evidence_images(reporte, limit=6):
    """Gather up to `limit` product images from local disk, platform data, and main reporte record."""
    from pathlib import Path
    base_dir = Path(__file__).resolve().parent.parent
    images = []
    
    # 1. Direct local disk evidence file check (highest priority)
    local_candidates = [
        base_dir / "static" / "evidencias" / f"reporte_{reporte.id}.jpg",
        base_dir / "static" / "screenshots" / f"reporte_{reporte.id}.jpg"
    ]
    for local_f in local_candidates:
        if local_f.exists() and local_f.stat().st_size > 1000:
            try:
                img = PILImage.open(local_f)
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                img.thumbnail((800, 800), PILImage.Resampling.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=80)
                buf.seek(0)
                images.append(buf)
                break
            except Exception:
                pass

    # 2. Extract URLs from platform data and main reporte
    urls = []
    if getattr(reporte, "imagen_urls", None):
        try:
            parsed = json.loads(str(reporte.imagen_urls).replace("'", '"'))
            if isinstance(parsed, list):
                urls.extend(parsed)
            elif isinstance(parsed, str):
                urls.append(parsed)
        except Exception:
            urls.append(str(reporte.imagen_urls))

    for attr in ("instagram_data", "tiktok_data", "facebook_data", "mercadolibre_data"):
        pd = getattr(reporte, attr, None)
        if isinstance(pd, (list, tuple)):
            pd = pd[0] if pd else None
        if pd and getattr(pd, "image_urls", None):
            try:
                parsed = json.loads(pd.image_urls)
                if isinstance(parsed, list):
                    urls.extend(parsed)
                elif isinstance(parsed, str):
                    urls.append(parsed)
            except Exception:
                urls.append(str(pd.image_urls))
                    
    for u in urls:
        if len(images) >= limit:
            break
        if not u:
            continue
        u_str = str(u).strip()
        if u_str.startswith("/static"):
            # Local static relative path
            local_path = base_dir / u_str.lstrip("/")
            if local_path.exists() and local_path.stat().st_size > 1000:
                try:
                    img = PILImage.open(local_path)
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")
                    img.thumbnail((800, 800), PILImage.Resampling.LANCZOS)
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=80)
                    buf.seek(0)
                    images.append(buf)
                except Exception:
                    pass
        elif u_str.startswith("http"):
            img = _fetch_image(u_str)
            if img:
                images.append(img)
                
    return images


def _capture_report_evidence(reporte):
    """Capture the public listing when its stored product image is unavailable."""
    from services.screenshot_service import STATIC_SCREENSHOTS_DIR, take_screenshot_threaded

    screenshot_path = STATIC_SCREENSHOTS_DIR / f"reporte_{reporte.id}.jpg"
    if screenshot_path.exists() and screenshot_path.stat().st_size > 1000:
        return
    url = getattr(reporte, "url_evidencia", None)
    if url and str(url).startswith("http"):
        try:
            take_screenshot_threaded(str(url), screenshot_path, timeout=30)
        except Exception:
            pass


# ── Main Generator ───────────────────────────────────────────────────────────

def generate_cbn_investigation_pdf(db: Session, reporte, perfil):
    buffer = io.BytesIO()
    doc = BaseDocTemplate(
        buffer, pagesize=A4,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=2.75 * cm, bottomMargin=1.8 * cm,
    )

    body_frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="final")
    doc.addPageTemplates([
        PageTemplate(id="Final", frames=body_frame, onPage=_draw_final_header_footer),
    ])

    ss, title_s, normal, bold_s, hw, small = _styles()
    S = []  # Story

    estado = getattr(reporte.estado, "value", reporte.estado) or "N/D"
    estado_upper = html.escape(str(estado).upper())
    estado_color = {
        "CONFIRMADO": colors.HexColor("#2D8A56"),
        "DESCARTADO": colors.HexColor("#687782"),
        "PENDIENTE": colors.HexColor("#D35400"),
        "INVESTIGANDO": colors.HexColor("#00639B"),
        "SOSPECHOSO": colors.HexColor("#C0392B"),
    }.get(str(estado).upper(), colors.HexColor("#D35400"))
    banner_data = [[
        Paragraph("<b>NET HOLMES OSINT — INFORME FINAL DE INVESTIGACIÓN</b>", hw),
        Paragraph(f"<b>ESTADO: {estado_upper}</b>", hw),
    ]]
    banner = Table(banner_data, colWidths=[12.5 * cm, 5.5 * cm])
    banner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), CBN_NAVY),
        ("BACKGROUND", (1, 0), (1, 0), estado_color),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    S.append(banner)
    S.append(Spacer(1, 8))

    pais = (reporte.pais or "ARGENTINA").upper()
    marca = html.escape(str(reporte.marca_afectada or "N/D").upper())
    plataforma = html.escape(str(reporte.plataforma or "N/D").upper())
    S.append(Paragraph(f"INFORME FINAL — {marca} ({plataforma})", title_s))
    fecha_captura = reporte.fecha_captura.strftime("%d/%m/%Y %H:%M") if reporte.fecha_captura else "N/D"
    referencia = html.escape(str(reporte.referencia_interna or "N/D"))
    S.append(Paragraph(
        f"Referencia técnica: #{referencia} | Fecha de captura: {fecha_captura} | País: {html.escape(pais)}",
        small,
    ))
    S.append(Spacer(1, 8))

    username = reporte.titular_cuenta or "Desconocido"
    username_clean = username.replace("@", "").strip()

    # Pull perfil fields safely
    def pf(attr, default="\u2014"):
        return getattr(perfil, attr, None) or default if perfil else default

    banco_parts = []
    if pf("banco") != "\u2014":
        banco_parts.append(Paragraph(f"<b>{pf('banco')}</b>", normal))
    if pf("alias_bancario") != "\u2014":
        banco_parts.append(Paragraph(f"Alias: {pf('alias_bancario')}", normal))
    if pf("cvu_cbu") != "\u2014":
        banco_parts.append(Paragraph(f"CVU/CBU: {pf('cvu_cbu')}", normal))
    if not banco_parts:
        banco_parts = [Paragraph("\u2014", normal)]

    safe_url = html.escape(str(reporte.url_evidencia or ""), quote=True)
    safe_url_link = Paragraph(
        f"<a href='{safe_url}' color='#00639B'>{safe_url}</a>", normal
    )
    precio_publicado = (
        f"{getattr(reporte, 'moneda', None) or 'ARS'} {reporte.precio_publico:,.2f}"
        if reporte.precio_publico is not None else "No especificado"
    )
    detection_data = [
        [Paragraph("<b>MARCA AFECTADA</b>", bold_s), Paragraph(html.escape(str(reporte.marca_afectada or "N/D")), normal),
         Paragraph("<b>PLATAFORMA</b>", bold_s), Paragraph(plataforma, normal)],
        [Paragraph("<b>PRODUCTO / KEYWORD</b>", bold_s), Paragraph(html.escape(str(reporte.producto_catalogo or "Búsqueda general")), normal),
         Paragraph("<b>PRECIO PUBLICADO</b>", bold_s), Paragraph(html.escape(precio_publicado), normal)],
        [Paragraph("<b>USUARIO / TITULAR</b>", bold_s), Paragraph(html.escape(username_clean), normal),
         Paragraph("<b>TELÉFONO PÚBLICO</b>", bold_s), Paragraph(html.escape(str(reporte.telefono_publico or "No detectado")), normal)],
        [Paragraph("<b>UBICACIÓN DETECTADA</b>", bold_s), Paragraph(html.escape(str(reporte.direccion_publica or reporte.pais or "N/D")), normal),
         Paragraph("<b>SEGUIDORES / REP.</b>", bold_s), Paragraph(str(reporte.seguidores_infractor if reporte.seguidores_infractor is not None else "N/D"), normal)],
    ]
    detection_table = Table(detection_data, colWidths=[4 * cm, 5 * cm, 4 * cm, 5 * cm])
    detection_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CBN_TABLE_BG),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    S.append(detection_table)
    S.append(Spacer(1, 8))
    url_table = Table(
        [[Paragraph("<b>ENLACE DIRECTO:</b>", bold_s), safe_url_link]],
        colWidths=[3.5 * cm, 14.5 * cm],
    )
    url_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EBF5FB")),
        ("BOX", (0, 0), (-1, -1), 1, CBN_ACCENT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    S.append(url_table)
    S.append(Spacer(1, 10))

    sales_desc = Paragraph(
        f"Según el relevamiento, se detectó una publicación asociada a la marca "
        f"<b>{marca}</b>. La información se presenta como evidencia para revisión del analista.",
        normal,
    )

    overview_data = [
        [Paragraph("<b>DATOS DEL RELEVAMIENTO</b>", hw), ""],
        ["Titular / vendedor", Paragraph(html.escape(username_clean), normal)],
        ["DNI / cédula", Paragraph(html.escape(str(pf("dni_cedula"))), normal)],
        ["CUIT / CUIL / RUC", Paragraph(html.escape(str(pf("cuit_cuil_ruc"))), normal)],
        ["Banco / cuenta", banco_parts],
        ["Dirección relevada", Paragraph(html.escape(str(pf("direccion_exacta"))), normal)],
        ["Teléfono privado", Paragraph(html.escape(str(pf("telefono_privado"))), normal)],
        ["Correo electrónico", Paragraph(html.escape(str(pf("email"))), normal)],
        ["Resultado", sales_desc],
        ["Evidencia fotográfica", Paragraph("Ver sección de evidencia", normal)],
    ]
    t = Table(overview_data, colWidths=[5 * cm, 11 * cm])
    st = _overview_table_style()
    st.add("SPAN", (0, 0), (1, 0))
    st.add("BACKGROUND", (0, 0), (1, 0), CBN_NAVY)
    st.add("TEXTCOLOR", (0, 0), (1, 0), CBN_WHITE)
    t.setStyle(st)
    S.append(t)
    S.append(Spacer(1, 15))

    # Internal info
    precio_cotizado = pf("precio_final_cotizado", "USD 450")
    int_data = [
        [Paragraph("<b>INTERNAL INFORMATION</b>", hw), ""],
        ["PROPOSED FEES", Paragraph(str(precio_cotizado), normal)],
        ["INTERNAL REFERENCE", Paragraph(reporte.referencia_interna, normal)],
    ]
    ti = Table(int_data, colWidths=[5 * cm, 11 * cm])
    si = _overview_table_style()
    si.add("SPAN", (0, 0), (1, 0))
    si.add("BACKGROUND", (0, 0), (1, 0), CBN_NAVY)
    si.add("TEXTCOLOR", (0, 0), (1, 0), CBN_WHITE)
    ti.setStyle(si)
    S.append(ti)

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 3 ─ Identity & Traceability
    # ══════════════════════════════════════════════════════════════════════════
    S.append(PageBreak())
    S.append(_section_header_table("IDENTITY & TRACEABILITY"))
    S.append(Spacer(1, 10))

    id_data = [
        ["CUIT/CUIL", Paragraph(pf("cuit_cuil_ruc"), normal)],
        ["DNI", Paragraph(pf("dni_cedula"), normal)],
        ["ALIAS BANCARIO", Paragraph(pf("alias_bancario"), normal)],
        ["CVU/CBU", Paragraph(pf("cvu_cbu"), normal)],
        ["BANCO", Paragraph(pf("banco"), normal)],
        ["TEL\u00c9FONO", Paragraph(pf("telefono_privado"), normal)],
        ["DIRECCI\u00d3N", Paragraph(pf("direccion_exacta"), normal)],
    ]
    tid = Table(id_data, colWidths=[5 * cm, 11 * cm])
    tid.setStyle(_overview_table_style())
    S.append(tid)
    S.append(Spacer(1, 15))
    S.append(Paragraph("<i>Attach identity documents (CUIL certificate, bank proof, storefront photos) below if available.</i>", small))

    # ══════════════════════════════════════════════════════════════════════════
    # PAGES 4-5 ─ Chat / Honeypot Evidence
    # ══════════════════════════════════════════════════════════════════════════
    S.append(PageBreak())
    S.append(_section_header_table("CHAT TRANSCRIPTION / HONEYPOT EVIDENCE"))
    S.append(Spacer(1, 10))

    # Try to pull chat messages from the conversation system
    has_chat = False
    try:
        from models.conversation import Conversation, Message as ChatMessage
        conv = db.query(Conversation).filter(Conversation.reporte_id == reporte.id).first()
        if conv:
            messages = db.query(ChatMessage).filter(
                ChatMessage.conversation_id == conv.id
            ).order_by(ChatMessage.created_at.asc()).all()
            if messages:
                has_chat = True
                for msg in messages:
                    sender = msg.sender_type or "agent"
                    bubble_bg = CBN_TABLE_BG if sender == "agent" else colors.HexColor("#E8F5E9")
                    align = "LEFT" if sender == "agent" else "RIGHT"
                    bubble_style = ParagraphStyle(
                        f"bubble_{msg.id}", parent=normal, fontSize=8,
                        alignment=TA_LEFT if sender == "agent" else TA_RIGHT,
                    )
                    text = (msg.contenido or "").replace("\n", "<br/>")
                    label = "\ud83e\udd16 Agent" if sender == "agent" else "\ud83d\udc64 Subject"
                    row = [[Paragraph(f"<b>{label}:</b> {text}", bubble_style)]]
                    bt = Table(row, colWidths=[14 * cm])
                    bt.setStyle(TableStyle([
                        ("BACKGROUND", (0, 0), (-1, -1), bubble_bg),
                        ("ROUNDEDCORNERS", [6, 6, 6, 6]),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ]))
                    S.append(bt)
                    S.append(Spacer(1, 4))
    except Exception:
        pass

    if not has_chat:
        S.append(Paragraph(
            "<i>No automated chat transcription available for this investigation. "
            "Attach WhatsApp/DM screenshots manually if applicable.</i>", small
        ))

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 6 ─ Social Networks & Cross-Platform Correlation
    # ══════════════════════════════════════════════════════════════════════════
    S.append(PageBreak())
    S.append(_section_header_table("SOCIAL NETWORKS & CROSS-PLATFORM CORRELATION"))
    S.append(Spacer(1, 10))

    # Build social rows from ALL platform data on this reporte
    social_rows = []

    def get_plat_item(attr):
        val = getattr(reporte, attr, None)
        if isinstance(val, list) or hasattr(val, '__iter__') and not isinstance(val, dict):
            return val[0] if len(val) > 0 else None
        return val

    ig = get_plat_item("instagram_data")
    if ig:
        ig_url = reporte.url_evidencia if reporte.plataforma.lower() == "instagram" else ""
        social_rows.append([
            Paragraph("<b>INSTAGRAM</b>", hw),
            [Paragraph(f"<a href='{ig_url}' color='#00639B'>{ig_url}</a>", normal) if ig_url else Paragraph("\u2014", normal),
             Paragraph(f"User: <b>@{getattr(ig, 'username', 'N/A')}</b> | Followers: {getattr(ig, 'followers', 'N/A')} | Posts: {getattr(ig, 'likes_count', 'N/A')}", normal),
             Paragraph(f"Bio: {(getattr(ig, 'bio_text', 'N/A') or 'N/A')[:120]}", small)]
        ])

    tt = get_plat_item("tiktok_data")
    if tt:
        tt_url = reporte.url_evidencia if reporte.plataforma.lower() == "tiktok" else ""
        social_rows.append([
            Paragraph("<b>TIKTOK</b>", hw),
            [Paragraph(f"<a href='{tt_url}' color='#00639B'>{tt_url}</a>", normal) if tt_url else Paragraph("\u2014", normal),
             Paragraph(f"User: <b>@{getattr(tt, 'username', 'N/A')}</b> | Fans: {getattr(tt, 'followers', 'N/A')} | Likes: {getattr(tt, 'likes', 'N/A')}", normal),
             Paragraph(f"Bio: {(getattr(tt, 'bio_text', 'N/A') or 'N/A')[:120]}", small)]
        ])

    fb = get_plat_item("facebook_data")
    if fb:
        fb_url = getattr(fb, "seller_profile_url", None) or (reporte.url_evidencia if reporte.plataforma.lower() == "facebook" else "")
        social_rows.append([
            Paragraph("<b>FACEBOOK</b>", hw),
            [Paragraph(f"<a href='{fb_url}' color='#00639B'>{fb_url}</a>", normal) if fb_url else Paragraph("\u2014", normal),
             Paragraph(f"Seller: <b>{getattr(fb, 'seller_name', 'N/A')}</b> | Location: {getattr(fb, 'seller_location_city', 'N/A')}, {getattr(fb, 'seller_location_province', '')}", normal)]
        ])

    ml = get_plat_item("mercadolibre_data")
    if ml:
        ml_url = reporte.url_evidencia if reporte.plataforma.lower() == "mercadolibre" else ""
        social_rows.append([
            Paragraph("<b>MERCADO LIBRE</b>", hw),
            [Paragraph(f"<a href='{ml_url}' color='#00639B'>{ml_url}</a>", normal) if ml_url else Paragraph("\u2014", normal),
             Paragraph(f"Seller: <b>{getattr(ml, 'seller_nickname', 'N/A')}</b> | Rep: {getattr(ml, 'seller_reputation_level', 'N/A')} | Sales: {getattr(ml, 'seller_transactions_completed', 'N/A')}", normal)]
        ])

    # Plataforma Genérica (Web / Clasificados / Portales)
    is_generico = str(reporte.plataforma).lower() in ("generico", "web", "clasificados", "clasificado", "generic", "portal")
    
    if is_generico:
        from urllib.parse import urlparse
        parsed_domain = urlparse(reporte.url_evidencia).netloc or "Sitio Web / Clasificado"
        
        extracted_emails = []
        extracted_phones = []
        if getattr(reporte, "platform_data", None):
            try:
                pdata = json.loads(str(reporte.platform_data))
                extracted_emails = pdata.get("extracted_emails", [])
                extracted_phones = pdata.get("extracted_phones", [])
            except Exception:
                pass

        emails_str = ", ".join(extracted_emails) if extracted_emails else (pf("email") if pf("email") != "\u2014" else "No detectado")
        phones_str = ", ".join(extracted_phones) if extracted_phones else (reporte.telefono_publico or pf("telefono_privado") or "No detectado")

        gen_details = [
            Paragraph(f"<b>PORTAL / DOMINIO:</b> {parsed_domain.upper()}", normal),
            Paragraph(f"<b>PUBLICACIÓN:</b> {reporte.titulo_publicacion or 'Publicación en Clasificados / Web'}", normal),
            Paragraph(f"<b>URL DIRECTA:</b> <a href='{reporte.url_evidencia}' color='#00639B'>{reporte.url_evidencia}</a>", normal),
            Paragraph(f"<b>VENDEDOR / PUBLICANTE:</b> {reporte.titular_cuenta or 'No especificado'}", normal),
            Paragraph(f"<b>UBICACIÓN:</b> {reporte.ubicacion_infractor or 'Argentina'}", normal),
            Paragraph(f"<b>TELÉFONOS EXTRAÍDOS:</b> {phones_str}", normal),
            Paragraph(f"<b>CORREOS EXTRAÍDOS:</b> {emails_str}", normal),
        ]

        social_rows.append([
            Paragraph("<b>WEB / CLASIFICADOS</b>", hw),
            gen_details
        ])

    if not social_rows:
        plat = str(reporte.plataforma).upper()
        social_rows.append([
            Paragraph(f"<b>{plat}</b>", hw),
            Paragraph(f"<a href='{reporte.url_evidencia}' color='#00639B'>{reporte.url_evidencia}</a>", normal)
        ])

    ts = Table(social_rows, colWidths=[4 * cm, 12 * cm])
    ts.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), CBN_NAVY),
        ("TEXTCOLOR", (0, 0), (0, -1), CBN_WHITE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    S.append(ts)
    S.append(Spacer(1, 15))

    # Correlation links
    S.append(Paragraph("<b>Análisis de correlaciones entre plataformas</b>", bold_s))
    S.append(Spacer(1, 6))

    try:
        from models.correlation_link import CorrelationLink
        links = db.query(CorrelationLink).filter(
            or_(CorrelationLink.reporte_a_id == reporte.id,
                CorrelationLink.reporte_b_id == reporte.id)
        ).all()

        if links:
            corr_data = [["TYPE", "SUBTYPE", "LINKED TO", "SCORE"]]
            for lk in links:
                other_id = lk.reporte_b_id if lk.reporte_a_id == reporte.id else lk.reporte_a_id
                corr_data.append([
                    lk.tipo_correlacion.upper(),
                    lk.subtipo or "\u2014",
                    f"Report #{other_id}",
                    f"{(lk.score * 100):.0f}%",
                ])
            tc = Table(corr_data, colWidths=[3.5 * cm, 4 * cm, 4.5 * cm, 3 * cm])
            tc.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), CBN_ACCENT),
                ("TEXTCOLOR", (0, 0), (-1, 0), CBN_WHITE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("BACKGROUND", (0, 1), (-1, -1), CBN_TABLE_BG),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            S.append(tc)
        else:
            S.append(Paragraph("<i>No cross-platform correlations detected for this subject.</i>", small))
    except Exception:
        S.append(Paragraph("<i>Correlation module unavailable.</i>", small))

    # ══════════════════════════════════════════════════════════════════════════
    # PAGES 7-10 ─ Evidence (Product Grid)
    # ══════════════════════════════════════════════════════════════════════════
    S.append(PageBreak())
    S.append(_section_header_table("EVIDENCE \u2013 INFRINGING PRODUCTS"))
    S.append(Spacer(1, 10))

    imgs = _collect_evidence_images(reporte, limit=6)
    if not imgs:
        _capture_report_evidence(reporte)
        imgs = _collect_evidence_images(reporte, limit=6)

    if imgs:
        for idx, im in enumerate(imgs):
            try:
                rl = RLImage(im, width=11 * cm, height=11 * cm, kind="proportional")
                rl.hAlign = "CENTER"
                S.append(rl)
            except Exception:
                pass
            S.append(Spacer(1, 8))
            precio_str = f"ARS {reporte.precio_publico:,.2f}" if reporte.precio_publico else "Price N/A"
            S.append(Paragraph(
                f"<b>Product {idx + 1}:</b> {reporte.producto_catalogo or 'N/A'} "
                f"| <b>Brand:</b> {reporte.marca_afectada} | <b>Price:</b> {precio_str}",
                normal,
            ))
            S.append(Spacer(1, 15))
    else:
        S.append(Paragraph(
            "<i>(No photographic evidence captured for this report. "
            "Attach product screenshots manually.)</i>", small
        ))

    # Build
    doc.build(S)
    buffer.seek(0)
    return buffer


def generate_fase1_preview_pdf(db: Session, reporte) -> io.BytesIO:
    """
    Genera el Reporte de Vista Previa / Ficha Preliminar de Detección (Fase 1 - Triage).
    Especialmente diseñado para reportes en estado 'Pendiente' o 'Descartado'.
    Estilo visual institucional CBN Argentina.
    """
    buffer = io.BytesIO()
    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=2.8 * cm,
        bottomMargin=2.2 * cm,
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f1_normal")
    doc.addPageTemplates([
        PageTemplate(id="inner", frames=frame, onPage=_draw_header_footer)
    ])

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "F1Title", parent=styles["Heading1"],
        fontName="Helvetica-Bold", fontSize=15, leading=19,
        textColor=CBN_NAVY, spaceAfter=4
    )
    subtitle_style = ParagraphStyle(
        "F1Subtitle", parent=styles["Normal"],
        fontName="Helvetica", fontSize=9, leading=12,
        textColor=CBN_ACCENT, spaceAfter=10
    )
    normal = ParagraphStyle(
        "F1Normal", parent=styles["Normal"],
        fontName="Helvetica", fontSize=8.5, leading=12, textColor=CBN_TEXT
    )
    bold_s = ParagraphStyle(
        "F1Bold", parent=normal, fontName="Helvetica-Bold", textColor=CBN_DARK
    )
    hw = ParagraphStyle("F1Hw", parent=normal, fontName="Helvetica-Bold", textColor=CBN_WHITE)
    small = ParagraphStyle(
        "F1Small", parent=styles["Normal"],
        fontName="Helvetica-Oblique", fontSize=7.5, leading=10, textColor=colors.HexColor("#555555")
    )

    S = []

    # Banner Superior de Triage / Fase 1
    estado_upper = str(reporte.estado).upper()
    is_descartado = estado_upper == "DESCARTADO"
    badge_bg = colors.HexColor("#7F8C8D") if is_descartado else colors.HexColor("#D35400")

    banner_data = [[
        Paragraph("<b>NET HOLMES OSINT \u2014 FICHA PRELIMINAR DE DETECCIÓN (FASE 1)</b>", hw),
        Paragraph(f"<b>ESTADO: {estado_upper}</b>", hw)
    ]]
    tb_banner = Table(banner_data, colWidths=[12.5 * cm, 5.5 * cm])
    tb_banner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), CBN_NAVY),
        ("BACKGROUND", (1, 0), (1, 0), badge_bg),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    S.append(tb_banner)
    S.append(Spacer(1, 10))

    # Título Principal
    S.append(Paragraph(f"VISTA PREVIA DE EVIDENCIA \u2014 {reporte.marca_afectada.upper()} ({reporte.plataforma.upper()})", title_style))
    S.append(Paragraph(f"Referencia Técnica: #{reporte.referencia_interna} | Fecha de Captura: {reporte.fecha_captura.strftime('%d/%m/%Y %H:%M') if reporte.fecha_captura else 'N/D'}", subtitle_style))
    S.append(Spacer(1, 6))

    # Tabla de Datos de Detección (Fase 1)
    precio_str = f"ARS {reporte.precio_publico:,.2f}" if reporte.precio_publico else "No especificado"
    
    det_rows = [
        [Paragraph("<b>MARCA AFECTADA</b>", bold_s), Paragraph(reporte.marca_afectada or "N/D", normal),
         Paragraph("<b>PLATAFORMA</b>", bold_s), Paragraph(str(reporte.plataforma).upper(), normal)],
        [Paragraph("<b>PRODUCTO / KEYWORD</b>", bold_s), Paragraph(reporte.producto_catalogo or "Búsqueda general", normal),
         Paragraph("<b>PRECIO PUBLICADO</b>", bold_s), Paragraph(precio_str, normal)],
        [Paragraph("<b>USUARIO / TITULAR</b>", bold_s), Paragraph(reporte.titular_cuenta or "No identificado", normal),
         Paragraph("<b>TELÉFONO PÚBLICO</b>", bold_s), Paragraph(reporte.telefono_publico or "No detectado", normal)],
        [Paragraph("<b>UBICACIÓN DETECTADA</b>", bold_s), Paragraph(reporte.direccion_publica or reporte.pais or "Argentina", normal),
         Paragraph("<b>SEGUIDORES / REP</b>", bold_s), Paragraph(str(reporte.seguidores_infractor) if reporte.seguidores_infractor is not None else "N/D", normal)],
    ]
    t_det = Table(det_rows, colWidths=[4 * cm, 5 * cm, 4 * cm, 5 * cm])
    t_det.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CBN_TABLE_BG),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    S.append(t_det)
    S.append(Spacer(1, 10))

    # URL Directa de Evidencia
    url_box = [
        [Paragraph("<b>ENLACE DIRECTO:</b>", bold_s),
         Paragraph(f"<a href='{reporte.url_evidencia}' color='#00639B'><b>{reporte.url_evidencia}</b></a>", normal)]
    ]
    t_url = Table(url_box, colWidths=[3.5 * cm, 14.5 * cm])
    t_url.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EBF5FB")),
        ("BOX", (0, 0), (-1, -1), 1, CBN_ACCENT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    S.append(t_url)
    S.append(Spacer(1, 10))

    # Texto / Descripción de la Publicación
    if reporte.descripcion_post:
        S.append(Paragraph("<b>CONTENIDO DE LA PUBLICACIÓN (SNIPPET CAPTURADO)</b>", bold_s))
        S.append(Spacer(1, 4))
        desc_clean = reporte.descripcion_post.replace("<", "&lt;").replace(">", "&gt;")[:600]
        t_desc = Table([[Paragraph(f"<i>\"{desc_clean}\"</i>", small)]], colWidths=[18 * cm])
        t_desc.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F9F9F9")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))
        S.append(t_desc)
        S.append(Spacer(1, 10))

    # Fotografías de Evidencia Capturadas (Grid)
    imgs = _collect_evidence_images(reporte, limit=2)
    if imgs:
        S.append(Paragraph("<b>EVIDENCIA FOTOGRÁFICA / CAPTURA DE PANTALLA</b>", bold_s))
        S.append(Spacer(1, 6))
        img_cells = []
        for im in imgs:
            try:
                rl = RLImage(im, width=8.5 * cm, height=8.5 * cm, kind="proportional")
                rl.hAlign = "CENTER"
                img_cells.append(rl)
            except Exception:
                pass
        if img_cells:
            t_imgs = Table([img_cells], colWidths=[9 * cm] * len(img_cells))
            t_imgs.setStyle(TableStyle([
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            S.append(t_imgs)
            S.append(Spacer(1, 10))

    # Aviso Legal de Fase 1
    notice_text = (
        "<b>AVISO DE CONTROL DE CALIDAD \u2014 FASE 1 (TRIAGE):</b> Este documento es una ficha preliminar de detección "
        "forense automatizada. No constituye un dictamen pericial definitivo. Para habilitar el informe oficial "
        "con relevamiento de titularidad bancaria, cruce de CUIT/DNI, trazabilidad de pagos y actas periciales, "
        "el analista debe promover el caso a <b>Fase 2 (Investigando / Sospechoso)</b> desde el panel de Net Holmes."
    )
    t_notice = Table([[Paragraph(notice_text, small)]], colWidths=[18 * cm])
    t_notice.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FEF9E7")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#F39C12")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    S.append(t_notice)

    doc.build(S)
    buffer.seek(0)
    return buffer
