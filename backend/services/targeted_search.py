import asyncio
from datetime import datetime, timezone

from config import settings
from database import SessionLocal
from models.brand import Brand
from services.argentina_scope import normalize_argentina_locations
from services.cron_logger import cron_logger
from services.keyword_generator import generate_keywords
from scrapers.scraper_engine import ScraperEngine

targeted_search_state = {
    "is_running": False,
    "started_at": None,
    "finished_at": None,
    "last_error": None,
    "current_query": None,
    "processed_items": 0,
}


async def run_targeted_search(
    brand_id: int,
    requested_keywords: list[str],
    platforms: list[str],
    locations: list[str],
    limit: int,
    duration_minutes: int = 15,
) -> None:
    from services import cron_service
    from services.cron_manager import process_and_save_single_result

    db = SessionLocal()
    previous_limit = settings.APIFY_MAX_ITEMS
    try:
        brand = db.query(Brand).filter(Brand.id == brand_id, Brand.estado == "activa").first()
        if not brand:
            raise ValueError("La marca seleccionada no existe o está inactiva.")

        config = cron_service.get_cron_config(db)
        provider = getattr(config, "proveedor", "google_meli_osint") or "google_meli_osint"
        scope = normalize_argentina_locations(locations)
        engine = ScraperEngine()
        settings.APIFY_MAX_ITEMS = limit

        cron_logger.log(
            f"[Búsqueda dirigida] Marca={brand.nombre}; plataformas={platforms}; "
            f"ubicaciones={scope}; proveedor={provider}"
        )

        deadline = asyncio.get_running_loop().time() + duration_minutes * 60
        for platform in platforms:
            remaining_seconds = deadline - asyncio.get_running_loop().time()
            if remaining_seconds <= 0:
                cron_logger.log("[Búsqueda dirigida] Duración alcanzada; búsqueda finalizada.")
                return
            try:
                async with asyncio.timeout(remaining_seconds):
                    terms = requested_keywords or await generate_keywords(brand, platform)
            except TimeoutError:
                cron_logger.log("[Búsqueda dirigida] Duración alcanzada; búsqueda finalizada.")
                return
            scrape_method = getattr(engine, f"scrape_{platform}")
            for term in terms:
                for location in scope:
                    remaining_seconds = deadline - asyncio.get_running_loop().time()
                    if remaining_seconds <= 0:
                        cron_logger.log("[Búsqueda dirigida] Duración alcanzada; búsqueda finalizada.")
                        return
                    cron_logger.log(
                        f"[Búsqueda dirigida] Consulta exacta: '{term}' en "
                        f"{platform}/{location}"
                    )
                    targeted_search_state["current_query"] = f"{term} · {location} · {platform}"
                    try:
                        async with asyncio.timeout(remaining_seconds):
                            async for item in scrape_method(term, location, provider):
                                process_and_save_single_result(db, item, brand, term)
                                targeted_search_state["processed_items"] += 1
                                await asyncio.sleep(0)
                    except TimeoutError:
                        cron_logger.log("[Búsqueda dirigida] Duración alcanzada; búsqueda finalizada.")
                        return

        cron_logger.log("[Búsqueda dirigida] Escaneo finalizado.")
    except Exception as error:
        db.rollback()
        targeted_search_state["last_error"] = str(error)
        cron_logger.log(f"[Búsqueda dirigida] Error: {error}")
    finally:
        settings.APIFY_MAX_ITEMS = previous_limit
        targeted_search_state["is_running"] = False
        targeted_search_state["finished_at"] = datetime.now(timezone.utc).isoformat()
        targeted_search_state["current_query"] = None
        db.close()