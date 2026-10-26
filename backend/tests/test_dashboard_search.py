"""Pruebas aisladas: sin consultar servicios externos ni la BD del cliente."""

import asyncio
import copy
import os
from types import SimpleNamespace

os.environ["DATABASE_URL"] = "sqlite://"

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models  # noqa: F401
from database import Base, get_db
from middleware.auth_middleware import get_current_user
from models.reporte import ReporteBrandDefense
from routers.dashboard import router
from scrapers.dashboard_scraper import DashboardScraper
from services import dashboard_search as search_module
from services.dashboard_result_rules import canonical_url, evidence_key, direct_link, counterfeit_terms, qualifies
from services.dashboard_scope import COUNTRIES, normalize_scope, matches_scope
from services.public_contacts import extract_phone, normalize_phone

BRAND = {"id": 1, "name": "Nike", "products": [], "official": []}


@pytest.fixture
def sessions():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    engine.dispose()


def sample_item(code="testA", seller="@tienda_ejemplo"):
    return {
        "url": f"https://instagram.com/p/{code}", "title": f"Nike réplica G5 ({seller})",
        "description": "Zapatillas Nike réplica G5. Venta y envíos en Córdoba, Argentina.",
        "plataforma": "instagram", "seller": seller, "account": seller, "phone": None,
        "followers": None, "image": None, "source": "Google_Serper_OSINT", "address": None,
        "email": None, "contact_sources": [],
    }


@pytest.mark.parametrize("country,value,expected", [
    ("Argentina", "+54 9 11 2345-6789", "+5491123456789"),
    ("Argentina", "011 15 2345 6789", "+5491123456789"),
    ("Argentina", "0351 15 2345678", "+5493512345678"),
    ("Argentina", "+54 11 4321 5678", "+541143215678"),
    ("Brasil", "+55 (11) 91234-5678", "+5511912345678"),
    ("Brasil", "(21) 2345-6789", "+552123456789"),
    ("México", "+52 55 1234 5678", "+525512345678"),
    ("México", "+52 1 55 1234 5678", "+525512345678"),
    ("México", "044 55 1234 5678", "+525512345678"),
    ("México", "12345", None),
    ("Argentina", "+55 11 912345678", None),
    ("Brasil", "+54 9 11 23456789", None),
    ("Brasil", "(20) 91234-5678", None),
    ("Brasil", "(11) 81234-5678", None),
])
def test_phone_formats(country, value, expected):
    assert normalize_phone(value, country) == expected


def test_phone_requires_context_and_supports_whatsapp_links():
    assert extract_phone("Publicación 1123456789 precio $ 1234567890", "Argentina") is None
    assert extract_phone("https://wa.me/5511912345678?text=hola", "Brasil") == "+5511912345678"
    assert extract_phone("Teléfono: +52 55 1234 5678", "México") == "+525512345678"


def test_administrative_scopes_and_cross_country_rejection():
    assert [len(cfg["provincias"]) for cfg in COUNTRIES.values()] == [24, 27, 32]
    assert normalize_scope("Brazil", ["Sao Paulo"]) == ("Brasil", ["São Paulo"])
    assert normalize_scope("Mexico", []) == ("México", [])
    with pytest.raises(ValueError):
        normalize_scope("México", ["Córdoba"])
    assert matches_scope("Venta de réplicas en São Paulo, Brasil", "https://instagram.com/p/a", "Brasil", "São Paulo")
    assert not matches_scope("Envíos en Argentina", "https://instagram.com/p/a", "Brasil", None)
    assert not matches_scope("Réplicas Nike sin ubicación", "https://instagram.com/p/a", "Argentina", None)
    assert not matches_scope("Venta en Mendoza, Argentina", "https://instagram.com/p/a", "Argentina", "Córdoba")


def test_url_identity_preserves_content_ids_and_ignores_tracking():
    assert evidence_key("http://m.facebook.com/marketplace/item/123/?ref=x&fbclid=y") == evidence_key("https://www.facebook.com/marketplace/item/123")
    assert evidence_key("https://instagram.com/reel/AbC/?igsh=x") == evidence_key("https://instagram.com/p/AbC")
    assert evidence_key("https://facebook.com/user/posts/123") == evidence_key("https://facebook.com/story.php?story_fbid=123&id=321")
    assert evidence_key("https://tiktok.com/@seller/video/123") != evidence_key("https://tiktok.com/@seller/video/124")
    assert "fbclid" not in canonical_url("https://facebook.com/story.php?story_fbid=123&id=321&fbclid=x")
    assert not direct_link("https://evil.example/instagram.com/p/a", "instagram", "Argentina")
    assert not direct_link("https://instagram.com/explore/", "instagram", "Argentina")
    assert direct_link("https://produto.mercadolivre.com.br/MLB-1234567-produto", "mercadolibre", "Brasil")


@pytest.mark.parametrize("text", [
    "Nike original 100% auténtico. Venta en Argentina",
    "Nike calidad premium importada, precio barato",
    "No vendemos réplicas. Solo Nike original",
    "Tênis Nike. Não vendemos réplicas",
    "Cómo identificar réplicas de Nike",
])
def test_originals_ambiguous_claims_and_negations_are_rejected(text):
    assert counterfeit_terms(text) == []


def test_brand_product_and_official_filters_use_evidence_not_query():
    item = sample_item()
    assert qualifies(item, BRAND)
    assert not qualifies({**item, "title": "Otra marca réplica", "description": "Venta G5 Argentina"}, BRAND)
    assert not qualifies(item, {**BRAND, "products": ["camperas"]})
    assert not qualifies(item, {**BRAND, "official": [{"platform": "instagram", "handle": "tienda_ejemplo"}]})
    assert not qualifies({**item, "seller": "@nikebr"}, BRAND)


def test_save_keeps_ticket_and_analyst_decisions(sessions):
    with sessions() as db:
        first, created = search_module.save_item(db, sample_item(), BRAND, "Argentina", "zapatillas", ["replica"])
        assert created
        report = db.get(ReporteBrandDefense, first)
        report.estado = "Descartado"
        report.descripcion_post += "\nNota del analista."
        db.commit()
        reference = report.referencia_interna
        item = sample_item("testB")
        item["phone"] = "+5491123456789"
        second, created = search_module.save_item(db, item, BRAND, "Argentina", "zapatillas", ["g5"])
        assert not created and first == second
        assert db.query(ReporteBrandDefense).count() == 1
        assert report.referencia_interna == reference and report.estado == "Descartado"
        assert report.telefono_publico == item["phone"]
        assert "Nota del analista" in report.descripcion_post
        assert item["url"] in report.descripcion_post
        assert report.perfil is not None


def test_existing_tracking_variants_are_indexed(sessions):
    with sessions() as db:
        item = sample_item()
        item["url"] = "https://www.instagram.com/reel/testA/?igsh=tracking"
        report_id, _ = search_module.save_item(db, item, BRAND, "Argentina", "zapatillas", ["replica"])
        urls, accounts = search_module.existing_index(db)
        assert urls[evidence_key("https://instagram.com/p/testA")] == report_id
        assert accounts[("instagram", "nike", "@tienda_ejemplo")] == report_id


def test_serper_failure_falls_back_once_per_run(monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(402, json={"message": "Not enough credits"})
    free_calls = []
    def free_search(query, region):
        free_calls.append((query, region))
        return [{"href": "https://instagram.com/p/testA", "title": "Nike réplica venda São Paulo Brasil", "body": "Tênis disponíveis"}]
    monkeypatch.setattr(DashboardScraper, "_free_search", staticmethod(free_search))
    async def run():
        scraper = DashboardScraper("test-key", "Brasil")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            for _ in range(2):
                items = await scraper.search(client, "instagram", "Nike", "São Paulo")
                assert items and items[0]["source"] == "DuckDuckGo_OSINT"
        assert len(calls) == 1 and len(free_calls) == 2
        assert free_calls[0][1] == "br-pt" and "Argentina" not in free_calls[0][0]
        assert DashboardScraper("test-key", "Brasil").key == "test-key"
    asyncio.run(run())


def test_public_page_enrichment(monkeypatch):
    html = '''<html><head><meta property="og:description" content="Nike réplica venta Córdoba Argentina">
    <script type="application/ld+json">{"@type":"Store","telephone":"+54 9 11 2345 6789","email":"contacto@example.com","address":{"streetAddress":"Calle de prueba 123","addressRegion":"Córdoba","addressCountry":"Argentina"}}</script></head><body></body></html>'''
    async def get_html(client, url):
        return html
    monkeypatch.setattr(DashboardScraper, "_public_html", staticmethod(get_html))
    async def run():
        async with httpx.AsyncClient() as client:
            item = await DashboardScraper(None, "Argentina").enrich(client, sample_item())
        assert item["phone"] == "+5491123456789"
        assert item["email"] == "contacto@example.com"
        assert "Calle de prueba 123" in item["address"]
        assert len(item["contact_sources"]) == 1
    asyncio.run(run())


def test_runner_deduplication_and_platform_coverage(monkeypatch, sessions):
    monkeypatch.setattr(search_module, "SessionLocal", sessions)
    monkeypatch.setattr(search_module, "get_active_api_key", lambda *args, **kwargs: "test-key")
    platforms = []
    async def fake_search(self, client, platform, keyword, province, variant):
        self.successful_queries += 1
        platforms.append(platform)
        return [sample_item(), copy.deepcopy(sample_item())] if platform == "instagram" else []
    enrichment_calls = []
    async def enrich(self, client, item):
        enrichment_calls.append(item["url"])
        return item
    monkeypatch.setattr(DashboardScraper, "search", fake_search)
    monkeypatch.setattr(DashboardScraper, "enrich", enrich)
    async def run():
        manager = search_module.DashboardSearchManager()
        options = {"pais": "Argentina", "provincias": ["Córdoba"], "keywords": [], "duration_minutes": 5, "plataformas": ["facebook", "instagram", "tiktok", "mercadolibre"]}
        manager.start(1, options, [BRAND])
        await manager.task
        assert manager.state["status"] == "completed"
        assert manager.state["saved"] == 1 and manager.state["duplicates"] == 5
        assert manager.state["queries_done"] == 12
        assert all(platforms.count(p) == 3 for p in options["plataformas"])
        assert len(enrichment_calls) == 1
    asyncio.run(run())


def test_stop_deadline_and_single_active_run(monkeypatch):
    async def stall(self, options, brands, state):
        await asyncio.Event().wait()
    monkeypatch.setattr(search_module.DashboardSearchManager, "_collect", stall)
    options = {"pais": "Argentina", "provincias": [], "keywords": [], "duration_minutes": 5, "plataformas": ["instagram"]}
    async def run():
        manager = search_module.DashboardSearchManager()
        manager.start(1, options, [BRAND])
        with pytest.raises(ValueError):
            manager.start(1, options, [BRAND])
        assert manager.status(2) == {"is_running": False, "status": "idle"}
        await manager.stop()  # También cubre cancelación antes de iniciar la coroutine.
        assert manager.state["status"] == "stopped" and not manager.state["is_running"]
        manager.start(1, {**options, "duration_minutes": 0.0001}, [BRAND])
        await manager.task
        assert manager.state["finish_reason"] == "deadline" and not manager.state["is_running"]
    asyncio.run(run())


def test_endpoints_authentication_scope_and_stop_permissions(monkeypatch, sessions):
    manager = search_module.DashboardSearchManager()
    monkeypatch.setattr("routers.dashboard.dashboard_search", manager)
    app = FastAPI()
    app.include_router(router)
    user = SimpleNamespace(id=2, rol="analista")
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/api/dashboard/search/status")).status_code == 403
            app.dependency_overrides[get_current_user] = lambda: user
            def get_test_db():
                with sessions() as db:
                    yield db
            app.dependency_overrides[get_db] = get_test_db
            locations = (await client.get("/api/dashboard/search/locations")).json()
            assert [c["pais"] for c in locations] == ["Argentina", "Brasil", "México"]
            assert (await client.post("/api/dashboard/search/start", json={"brand_ids": [1], "pais": "México", "provincias": ["Córdoba"]})).status_code == 422
            assert (await client.post("/api/dashboard/search/start", json={"brand_ids": [1], "duration_minutes": 100})).status_code == 422
            manager.state = {"owner_id": 1, "is_running": True}
            assert (await client.post("/api/dashboard/search/stop")).status_code == 403
    asyncio.run(run())
