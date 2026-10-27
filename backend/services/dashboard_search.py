"""Ejecución manual del dashboard, independiente del scheduler y de sus estados."""

import asyncio
from datetime import datetime, timedelta, timezone
import json
import logging
import re
from uuid import uuid4

import httpx
from database import SessionLocal
from models.brand import Brand
from models.reporte import ReporteBrandDefense
from models.perfil_investigacion import PerfilInvestigacion
from models.facebook_data import ReporteFacebookData
from models.instagram_data import ReporteInstagramData
from models.tiktok_data import ReporteTiktokData
from models.mercadolibre_data import ReporteMercadoLibreData
from scrapers.dashboard_scraper import DashboardScraper
from services.api_key_service import get_active_api_key
from services.correlation_engine import CorrelationEngine
from services.dashboard_result_rules import account_key, evidence_key, evaluate_result
from services.dashboard_scope import COUNTRIES, matches_scope, observed_region
from services.dashboard_log import dashboard_log

logger = logging.getLogger("uvicorn.error")

DURATION_SECONDS = {
    "minutes": 60,
    "hours": 60 * 60,
    "days": 24 * 60 * 60,
    "weeks": 7 * 24 * 60 * 60,
    "months": 30 * 24 * 60 * 60,
}


def requested_duration_seconds(options: dict) -> float:
    # duration_minutes conserva compatibilidad con invocaciones internas previas.
    if "duration_value" not in options:
        return float(options.get("duration_minutes", 30)) * 60
    return float(options["duration_value"]) * DURATION_SECONDS[options.get("duration_unit", "minutes")]


def result_context(item: dict) -> str:
    title = " ".join(str(item.get("title") or "").split())[:120]
    return f"plataforma={item.get('plataforma')} titulo={title!r} url={item.get('url')}"


def brand_snapshot(brand: Brand) -> dict:
    return {
        "id": brand.id, "name": brand.nombre,
        "products": [p.nombre for p in brand.products if (p.estado or "activa").casefold() == "activa"],
        "official": [{"platform": c.plataforma, "handle": c.handle_oficial} for c in brand.cuentas_oficiales],
    }


def existing_index(db) -> dict:
    urls = {}
    rows = db.query(ReporteBrandDefense.id, ReporteBrandDefense.url_evidencia).order_by(ReporteBrandDefense.id).yield_per(500)
    for row in rows:
        key = evidence_key(row.url_evidencia or "")
        if key:
            urls.setdefault(key, row.id)
    return urls


def existing_account_index(db) -> dict:
    """Un ticket por cuenta inequívoca, marca y plataforma."""
    accounts = {}
    rows = db.query(
        ReporteBrandDefense.id,
        ReporteBrandDefense.plataforma,
        ReporteBrandDefense.marca_afectada,
        ReporteBrandDefense.titular_cuenta,
    ).order_by(ReporteBrandDefense.id).yield_per(500)
    for row in rows:
        key = account_key(row.plataforma or "", row.marca_afectada or "", row.titular_cuenta or "")
        if key:
            accounts.setdefault(key, row.id)
    return accounts


def parsed_price(text: str) -> float | None:
    match = re.search(r"(?:R\$|\$|ARS|MXN|BRL)\s*(\d[\d.,]*)", text, re.I)
    if not match:
        return None
    value = match[1].rstrip(".,")
    if "," in value and "." in value:
        decimal = "," if value.rfind(",") > value.rfind(".") else "."
        value = value.replace("." if decimal == "," else ",", "").replace(decimal, ".")
    elif "," in value or "." in value:
        separator = "," if "," in value else "."
        parts = value.split(separator)
        value = "".join(parts) if len(parts[-1]) == 3 else "".join(parts[:-1]) + "." + parts[-1]
    try:
        return float(value)
    except ValueError:
        return None


def save_item(db, item: dict, brand: dict, country: str, keyword: str, terms: list[str], existing_id: int | None = None) -> tuple[int, bool]:
    """Mantiene los modelos y las relaciones que usan Reportes e Investigación."""
    existing = db.get(ReporteBrandDefense, existing_id) if existing_id else None
    if existing is None:
        # Revisión al guardar: contempla altas del cron mientras corre el dashboard.
        existing = db.query(ReporteBrandDefense).filter(
            ReporteBrandDefense.url_evidencia == item["url"]
        ).order_by(ReporteBrandDefense.id).first()
    if existing is None:
        identity = account_key(item["plataforma"], brand["name"], item["seller"])
        if identity:
            candidates = db.query(ReporteBrandDefense).filter(
                ReporteBrandDefense.plataforma == item["plataforma"],
                ReporteBrandDefense.marca_afectada == brand["name"],
            ).order_by(ReporteBrandDefense.id).all()
            existing = next((row for row in candidates if account_key(
                row.plataforma, row.marca_afectada, row.titular_cuenta,
            ) == identity), None)
    if existing:
        # Completar vacíos, sin modificar decisiones ni notas del analista.
        for field, value in (("telefono_publico", item["phone"]), ("direccion_publica", item["address"]), ("seguidores_infractor", item["followers"])):
            if not getattr(existing, field) and value:
                setattr(existing, field, value)
        if evidence_key(existing.url_evidencia) != evidence_key(item["url"]) and item["url"] not in (existing.descripcion_post or ""):
            extra = "\n".join((
                "Evidencia adicional del mismo objetivo:",
                f"URL: {item['url']}",
                f"Título: {item['title']}",
                f"Descripción: {item['description'][:1000]}",
            ))
            existing.descripcion_post = (existing.descripcion_post or "") + "\n" + extra
        if existing.perfil and not existing.perfil.email and item["email"]:
            existing.perfil.email = item["email"]
        db.commit()
        return existing.id, False

    location = observed_region(item.get("observed_text", "") + " " + item["title"] + " " + item["description"], country)
    description = f"[INDICIOS DE RÉPLICA: {', '.join(terms)}; pendiente de verificación humana]\n{item['title']}\n{item['description']}"
    report = ReporteBrandDefense(
        pais=country, producto_catalogo=keyword[:255], marca_afectada=brand["name"],
        plataforma=item["plataforma"], titular_cuenta=item["seller"][:255], url_evidencia=item["url"],
        descripcion_post=description, precio_publico=parsed_price(item["description"]),
        moneda=COUNTRIES[country]["currency"], direccion_publica=item["address"] or (f"{location}, {country}" if location else None),
        telefono_publico=item["phone"], seguidores_infractor=item["followers"], estado="Investigando",
    )
    db.add(report)
    db.flush()
    db.add(PerfilInvestigacion(reporte_id=report.id, email=item["email"]))
    images = json.dumps([item["image"]]) if item["image"] else None
    platform = item["plataforma"]
    if platform == "facebook":
        db.add(ReporteFacebookData(reporte_id=report.id, seller_name=item["seller"][:200], seller_location_province=location, image_urls=images))
    elif platform == "instagram":
        db.add(ReporteInstagramData(reporte_id=report.id, username=item["account"], followers=item["followers"], caption_full=item["description"], image_urls=images))
    elif platform == "tiktok":
        db.add(ReporteTiktokData(reporte_id=report.id, username=item["account"], followers=item["followers"], description_full=item["description"], image_urls=images))
    elif platform == "mercadolibre":
        db.add(ReporteMercadoLibreData(reporte_id=report.id, image_urls=images))
    db.commit()
    return report.id, True


class DashboardSearchManager:
    def __init__(self):
        self.task = None
        self.state = None

    def status(self, user_id: int, admin: bool = False) -> dict:
        if not self.state or (self.state["owner_id"] != user_id and not admin):
            return {"is_running": False, "status": "idle"}
        return {k: v for k, v in self.state.items() if k != "owner_id"}

    def start(self, user_id: int, options: dict, brands: list[dict]) -> dict:
        if self.task and not self.task.done():
            raise ValueError("Ya hay una búsqueda del dashboard en ejecución.")
        started = datetime.now(timezone.utc)
        duration_seconds = requested_duration_seconds(options)
        target = options.get("target_objectives")
        self.state = {
            "id": str(uuid4()), "owner_id": user_id, "is_running": True, "status": "running",
            "started_at": started.isoformat(), "deadline_at": (started + timedelta(seconds=duration_seconds)).isoformat(),
            "finished_at": None, "finish_reason": None, "saved": 0, "duplicates": 0, "discarded": 0,
            "queries_done": 0, "queries_total": None, "round": 0,
            "current_platform": None, "current_location": None, "provider": "Serper", "warning": None,
            "pais": options["pais"], "duration_value": options.get("duration_value"),
            "duration_unit": options.get("duration_unit", "minutes"), "duration_seconds": duration_seconds,
            "target_objectives": target,
        }
        self.task = asyncio.create_task(self._run(options, brands), name="dashboard-search")
        return self.status(user_id)

    async def stop(self):
        if self.task and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            # Si se canceló antes del primer paso de la coroutine, su finally no se ejecuta.
            self.state.update(is_running=False, status="stopped", finish_reason="user", finished_at=datetime.now(timezone.utc).isoformat())

    async def _run(self, options: dict, brands: list[dict]):
        state = self.state
        dashboard_log(
            "[DASHBOARD][INICIO] pais=%s regiones=%s duracion=%s %s meta_objetivos=%s plataformas=%s marcas=%s",
            options["pais"], options["provincias"] or ["todas"],
            options.get("duration_value", options.get("duration_minutes", 30)), options.get("duration_unit", "minutes"),
            options.get("target_objectives", "sin límite"), options["plataformas"], [brand["name"] for brand in brands],
        )
        try:
            # Incluye consulta, enriquecimiento y guardado dentro del límite elegido.
            async with asyncio.timeout(requested_duration_seconds(options)):
                await self._collect(options, brands, state)
            if state.get("finish_reason") != "target":
                state.update(status="completed", finish_reason="deadline")
        except TimeoutError:
            state.update(status="completed", finish_reason="deadline")
        except asyncio.CancelledError:
            state.update(status="stopped", finish_reason="user")
        except Exception:
            logger.exception("Falló la búsqueda del dashboard")
            dashboard_log("[DASHBOARD][ERROR] La búsqueda terminó con un error inesperado.")
            state.update(status="failed", finish_reason="error", warning="La búsqueda terminó con errores; los resultados ya guardados se conservaron.")
        finally:
            state.update(is_running=False, finished_at=datetime.now(timezone.utc).isoformat())
            dashboard_log(
                "[DASHBOARD][FIN] motivo=%s guardados=%s duplicados=%s descartados=%s consultas=%s",
                state.get("finish_reason"), state["saved"], state["duplicates"], state["discarded"], state["queries_done"],
            )

    async def _collect(self, options: dict, brands: list[dict], state: dict):
        with SessionLocal() as db:
            key = get_active_api_key("serper", db=db)
            urls = existing_index(db)
            accounts = existing_account_index(db)
        scraper = DashboardScraper(key, options["pais"])
        seen = set()
        state["provider"] = scraper.provider
        async with httpx.AsyncClient(timeout=12, headers={"User-Agent": "Mozilla/5.0 (compatible; NetHolmes/1.0)"}, follow_redirects=False) as client:
            variant = 0
            while True:
                state["round"] = variant + 1
                for brand in brands:
                    keywords = options["keywords"] or brand["products"] or [brand["name"]]
                    for keyword in keywords:
                        query_keyword = keyword if brand["name"].casefold() in keyword.casefold() else f"{brand['name']} {keyword}"
                        for province in options["provincias"] or [None]:
                            # Un turno por plataforma, sin privilegiar Facebook.
                            for platform in options["plataformas"]:
                                state.update(current_platform=platform, current_location=province or options["pais"])
                                items = await scraper.search(client, platform, query_keyword, province, variant)
                                state.update(provider=scraper.provider, warning=scraper.warning)
                                candidates = []
                                for item in items:
                                    dashboard_log("[DASHBOARD][ENTRA] %s", result_context(item))
                                    key = evidence_key(item["url"])
                                    seen_key = (brand["id"], province, key)
                                    if seen_key in seen:
                                        state["duplicates"] += 1
                                        dashboard_log("[DASHBOARD][DUPLICADO-RONDA] %s", result_context(item))
                                        continue
                                    seen.add(seen_key)
                                    terms, reason = evaluate_result(item, brand)
                                    if not terms:
                                        state["discarded"] += 1
                                        dashboard_log("[DASHBOARD][DESCARTADO] motivo=%s %s", reason, result_context(item))
                                        continue
                                    existing_id = urls.get(key)
                                    if existing_id:
                                        # Sin llamadas extra de red para volver a guardar un objetivo conocido.
                                        text = f"{item['title']} {item['description']}"
                                        if matches_scope(
                                            text, item["url"], options["pais"], province,
                                            item.get("searched_country"), item.get("searched_region"),
                                        ):
                                            with SessionLocal() as db:
                                                save_item(db, item, brand, options["pais"], keyword, terms, existing_id)
                                        state["duplicates"] += 1
                                        dashboard_log("[DASHBOARD][DUPLICADO-BD] reporte_id=%s %s", existing_id, result_context(item))
                                        continue
                                    candidates.append(item)
                                # Red en paralelo y acotada. La cancelación interrumpe las tres tareas.
                                for offset in range(0, len(candidates), 3):
                                    enriched = await asyncio.gather(*(scraper.enrich(client, candidate) for candidate in candidates[offset:offset + 3]))
                                    for item in enriched:
                                        text = f"{item['title']} {item['description']} {item.get('observed_text', '')}"
                                        terms, reason = evaluate_result(item, brand)
                                        if not terms:
                                            state["discarded"] += 1
                                            dashboard_log("[DASHBOARD][DESCARTADO] motivo=%s %s", reason, result_context(item))
                                            continue
                                        if not matches_scope(
                                            text, item["url"], options["pais"], province,
                                            item.get("searched_country"), item.get("searched_region"),
                                        ):
                                            state["discarded"] += 1
                                            dashboard_log("[DASHBOARD][DESCARTADO] motivo=fuera del país o región seleccionada %s", result_context(item))
                                            continue
                                        identity = account_key(item["plataforma"], brand["name"], item["seller"])
                                        existing_id = urls.get(evidence_key(item["url"])) or (accounts.get(identity) if identity else None)
                                        with SessionLocal() as db:
                                            report_id, created = save_item(db, item, brand, options["pais"], keyword, terms, existing_id)
                                            if created:
                                                try:
                                                    correlation = CorrelationEngine.analyze_new_reports(db, [report_id])
                                                    dashboard_log(
                                                        "[DASHBOARD][CORRELACION] reporte_id=%s vinculos=%s clusters=%s",
                                                        report_id, correlation["links"], correlation["clusters"],
                                                    )
                                                except Exception as exc:
                                                    db.rollback()
                                                    dashboard_log(
                                                        "[DASHBOARD][CORRELACION] reporte_id=%s no disponible (%s)",
                                                        report_id, type(exc).__name__,
                                                    )
                                        urls[evidence_key(item["url"])] = report_id
                                        if identity:
                                            accounts[identity] = report_id
                                        state["saved" if created else "duplicates"] += 1
                                        dashboard_log(
                                            "[DASHBOARD][%s] reporte_id=%s %s",
                                            "GUARDADO" if created else ("MISMO-OBJETIVO" if identity else "DUPLICADO-BD"),
                                            report_id, result_context(item),
                                        )
                                        target = options.get("target_objectives")
                                        if created and target and state["saved"] >= target:
                                            state.update(status="completed", finish_reason="target")
                                            dashboard_log(
                                                "[DASHBOARD][META-ALCANZADA] objetivos=%s tiempo_restante_hasta=%s",
                                                state["saved"], state["deadline_at"],
                                            )
                                            return
                                state["queries_done"] += 1
                                await asyncio.sleep(0)
                variant += 1
                # Al rotar cinco expresiones y diez páginas, comenzar otra ronda
                # dejando un intervalo para no saturar los proveedores.
                if variant % 50 == 0:
                    await asyncio.sleep(15)


dashboard_search = DashboardSearchManager()
