"""Pruebas aisladas: sin consultar servicios externos ni la BD del cliente."""

import asyncio
import copy
from datetime import datetime, timezone
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
from models.facebook_data import ReporteFacebookData
from models.instagram_data import ReporteInstagramData
from routers.dashboard import DashboardSearchRequest, router
from scrapers.dashboard_scraper import DashboardScraper
from services import dashboard_search as search_module
from services.dashboard_result_rules import canonical_url, evidence_key, direct_link, counterfeit_terms, evaluate_result, qualifies
from services.dashboard_scope import COUNTRIES, normalize_scope, matches_scope
from services.public_contacts import extract_phone, normalize_phone
from services.dashboard_log import dashboard_log
from services.listing_fields import (
    extract_facebook_author,
    extract_instagram_author,
    extract_price,
    instagram_url_identity,
)

BRAND = {"id": 1, "name": "Nike", "products": [], "official": []}


def test_dashboard_log_reaches_visual_cron_console(monkeypatch):
    received = []
    monkeypatch.setattr("services.dashboard_log.cron_logger.log", received.append)
    dashboard_log("[DASHBOARD][DESCARTADO] motivo=%s", "contenido original")
    assert received == ["[DASHBOARD][DESCARTADO] motivo=contenido original"]


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
    ("Argentina", "351 234 5678", "+5493512345678"),
    ("Argentina", "+54 11 4321 5678", None),
    ("Brasil", "+55 (11) 91234-5678", "+5511912345678"),
    ("Brasil", "11 91234-5678", "+5511912345678"),
    ("Brasil", "(21) 2345-6789", None),
    ("México", "+52 55 1234 5678", "+525512345678"),
    ("México", "55 1234 5678", "+525512345678"),
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
    assert extract_phone("Soy de Jujuy hago envios. cel 3885126218", "Argentina") == "+5493885126218"
    assert extract_phone("https://wa.me/5511912345678?text=hola", "Brasil") == "+5511912345678"
    assert extract_phone("Teléfono: +52 55 1234 5678", "México") == "+525512345678"


@pytest.mark.parametrize("text,expected", [
    ("Precio: 25.000.", 25000.0),
    ("Precio $ 18.500", 18500.0),
    ("R$ 180", 180.0),
    ("MXN 1,299", 1299.0),
    ("Precio: 35.000 0 comentarios", 35000.0),
    ("Talles 34 al 39. WhatsApp 5493885297285", None),
])
def test_explicit_listing_price_extraction(text, expected):
    assert extract_price(text) == expected


def test_facebook_post_author_has_priority_over_group():
    item = {
        "groupName": "Compra y venta Puerto Tirol Chaco",
        "author": {"name": "Gustavo Machaca"},
    }
    assert extract_facebook_author(item, description="Precio: 25.000") == "Gustavo Machaca"
    assert extract_facebook_author(
        {}, description="Gustavo Machaca · 18 de diciembre de 2024 · PUMA SUEDE"
    ) == "Gustavo Machaca"
    assert extract_facebook_author(
        {},
        title="Madryn Publica Compras y Ventas",
        description="Marianela Pereyra · 17 de septiembre · Vendo calzado",
    ) == "Marianela Pereyra"
    assert extract_facebook_author(
        {}, description="No sé por que la Puma es tan elegida por los clientes"
    ) is None


def test_dashboard_social_authors_are_saved_from_indexed_byline():
    scraper = DashboardScraper(None, "Argentina")
    facebook = scraper.parse({
        "title": "Madryn Publica Compras y Ventas",
        "snippet": "Marianela Pereyra · 17 de septiembre · Vendo calzado réplica",
        "link": "https://facebook.com/groups/madryn/posts/123",
    }, "facebook", "Google_Serper_OSINT")
    assert facebook["seller"] == "Marianela Pereyra"
    assert facebook["seller_author_verified"] is True

    assert extract_instagram_author("Tienda Ejemplo (@tienda.replica) • Instagram") == "@tienda.replica"
    instagram = scraper.parse({
        "title": "Tienda Ejemplo (@tienda.replica) • Instagram",
        "snippet": "Calzado réplica disponible",
        "link": "https://instagram.com/p/ABC123",
    }, "instagram", "Google_Serper_OSINT")
    assert instagram["seller"] == "@tienda.replica"
    assert instagram["seller_author_verified"] is True

    profile = scraper.parse({
        "title": "ZTS Shoes | Zapatillas importadas calidad G5",
        "snippet": "Puma y Nike réplica. Envíos en Argentina.",
        "link": "https://instagram.com/zts.shoes/",
    }, "instagram", "Google_Serper_OSINT")
    assert profile["seller"] == "@zts.shoes"
    assert profile["account"] == "@zts.shoes"
    assert profile["result_type"] == "profile"
    assert profile["seller_source"] == "instagram_url"


def test_authors_from_real_social_metadata_formats():
    assert extract_instagram_author(
        "3 hours ago · zts.shoes's profile picture · Zapatillas importadas"
    ) == "@zts.shoes"


def test_administrative_scopes_and_cross_country_rejection():
    assert [len(cfg["provincias"]) for cfg in COUNTRIES.values()] == [24, 27, 32]
    assert normalize_scope("Brazil", ["Sao Paulo"]) == ("Brasil", ["São Paulo"])
    assert normalize_scope("Mexico", []) == ("México", [])
    with pytest.raises(ValueError):
        normalize_scope("México", ["Córdoba"])
    assert matches_scope("Venta de réplicas en São Paulo, Brasil", "https://instagram.com/p/a", "Brasil", "São Paulo")
    assert not matches_scope("Envíos en Argentina", "https://instagram.com/p/a", "Brasil", None)
    assert not matches_scope("Réplicas Nike sin ubicación", "https://instagram.com/p/a", "Argentina", None)
    assert matches_scope("Roupas Nike réplica disponíveis", "https://instagram.com/p/a", "Brasil", "São Paulo", "Brasil", "São Paulo")
    assert not matches_scope("Ropa Nike réplica, envíos en Argentina", "https://instagram.com/p/a", "Brasil", None, "Brasil", None)
    assert not matches_scope("Venta en Mendoza, Argentina", "https://instagram.com/p/a", "Argentina", "Córdoba")


def test_url_identity_preserves_content_ids_and_ignores_tracking():
    assert evidence_key("http://m.facebook.com/marketplace/item/123/?ref=x&fbclid=y") == evidence_key("https://www.facebook.com/marketplace/item/123")
    assert evidence_key("https://instagram.com/reel/AbC/?igsh=x") == evidence_key("https://instagram.com/p/AbC")
    assert evidence_key("https://facebook.com/user/posts/123") == evidence_key("https://facebook.com/story.php?story_fbid=123&id=321")
    assert evidence_key("https://tiktok.com/@seller/video/123") != evidence_key("https://tiktok.com/@seller/video/124")
    assert "fbclid" not in canonical_url("https://facebook.com/story.php?story_fbid=123&id=321&fbclid=x")
    assert not direct_link("https://evil.example/instagram.com/p/a", "instagram", "Argentina")
    assert not direct_link("https://instagram.com/explore/", "instagram", "Argentina")
    assert direct_link("https://instagram.com/zts.shoes/", "instagram", "Argentina")
    assert instagram_url_identity("https://instagram.com/zts.shoes/") == ("profile", "@zts.shoes")
    assert instagram_url_identity("https://instagram.com/reel/ABC123") == ("reel", None)
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
    car_part = {**item, "title": "Puma mica trasera de cuarta serie réplica", "description": "Vendo mica nueva. Envíos a Jujuy. Cel 3885126218."}
    assert not qualifies(car_part, {"id": 2, "name": "Puma", "products": [], "official": []})


@pytest.mark.parametrize("title,description,reason", [
    ("¿Tus tenis Nike son fake o no?", "Aquí cinco tips para descubrirlo y reparar tus tenis.", "contenido educativo"),
    ("Nike original", "Tenis 100% originales en venta, aunque otros ofrecen fake.", "producto es original"),
    ("Nike réplica", "Comparativa entre calzado original y fake.", "contenido educativo"),
    ("Nike réplica G5", "Nuevo modelo de tenis para mostrar.", "contenido educativo"),
    ("¿Unos tenis con Inteligencia Artificial?", "PUMA ya lo hizo posible con los INVERSE.", "contenido educativo"),
])
def test_rejects_educational_original_and_non_sales_content(title, description, reason):
    item = {**sample_item(), "title": title, "description": description, "plataforma": "facebook"}
    terms, explanation = evaluate_result(item, BRAND)
    assert terms == [] and reason in explanation


def test_accepts_counterfeit_apparel_sale_even_when_described_as_not_original():
    item = {**sample_item(), "title": "Nike réplica no original", "description": "Venta de zapatillas G5, precio $25000."}
    terms, explanation = evaluate_result(item, BRAND)
    assert terms and "intención de venta" in explanation


def test_rejects_buyer_looking_for_counterfeit_wholesaler():
    item = {
        **sample_item(),
        "title": "Alguien que venda zapatillas Nike por mayor calidad G5",
        "description": "Necesito que la docena sea surtida, soy de CABA.",
    }
    terms, explanation = evaluate_result(item, BRAND)
    assert terms == [] and "solicitud de comprador" in explanation


def test_selected_brand_rejects_other_brand_even_with_counterfeit_sale_terms():
    item = {
        **sample_item(),
        "title": "Zapatillas Nike G5",
        "description": "Venta por mayor, precio $25000 y entrega inmediata.",
    }
    terms, explanation = evaluate_result(item, {**BRAND, "name": "Puma"})
    assert terms == [] and "marca seleccionada" in explanation


def test_rejects_customer_authentication_question_from_mexico():
    item = {
        **sample_item(),
        "title": "Consulta sobre calzado Puma",
        "description": "Alguien ha pedido calzado Puma y el QR no da información. El cliente me dice que son clon. ¿Sabrán si son clon o qué onda? Me pueden ayudar, por favor.",
    }
    terms, explanation = evaluate_result(item, {**BRAND, "name": "Puma"})
    assert terms == [] and "consulta de un cliente" in explanation


def test_rejects_brazilian_store_that_only_sells_originals():
    item = {
        **sample_item(),
        "title": "Vei do Tênis",
        "description": "Nike: só trabalhamos com peças e tênis 100% originais, sem imitação.",
    }
    terms, explanation = evaluate_result(item, BRAND)
    assert terms == [] and "producto es original" in explanation


def test_brazil_uses_only_the_requested_counterfeit_vocabulary():
    ordinary_store = {
        **sample_item(),
        "title": "PUMA 180 EM LOJA",
        "description": "Todas as peças são vendidas em nossa loja física. Compre seu kit. Enviamos para todo o Brasil!",
        "searched_country": "Brasil",
    }
    terms, explanation = evaluate_result(ordinary_store, {**BRAND, "name": "Puma"})
    assert terms == [] and "indicios explícitos" in explanation

    accepted_phrases = (
        "réplica", "falsificado", "primeira linha premium", "linha premium", "espelhado",
        "qualidade 1:1", "UA", "inspirado", "importado",
    )
    for index, phrase in enumerate(accepted_phrases):
        item = {
            **sample_item(f"br{index}"),
            "title": f"Tênis Puma {phrase}",
            "description": "Venda com preço R$ 180 e envio para todo Brasil.",
            "searched_country": "Brasil",
        }
        terms, explanation = evaluate_result(item, {**BRAND, "name": "Puma"})
        assert terms and "intención de venta" in explanation

    rejected = {
        **ordinary_store,
        "title": "Tênis Puma fake G5 AAA clone",
        "description": "Venda por R$ 180 com entrega no Brasil.",
    }
    assert evaluate_result(rejected, {**BRAND, "name": "Puma"})[0] == []


def test_brazil_rejects_original_product_inspired_by_an_older_model():
    item = {
        **sample_item("puma-vs1"),
        "title": "PUMA VS-1 Contact ganha espaço no catálogo",
        "description": (
            "Inspirado nas chuteiras V1 dos anos 2000, o modelo chega agora em duas cores para a primavera. "
            "As versões Green e Bitter Chocolate já estão disponíveis no site da PUMA por 140 dólares. "
            "Disponível do 36 ao 43. Comenta PUMA para receber o link do modelo."
        ),
        "searched_country": "Brasil",
    }
    terms, explanation = evaluate_result(item, {**BRAND, "name": "Puma"})
    assert terms == [] and "contenido educativo" in explanation

    counterfeit_sale = {
        **item,
        "title": "Tênis Puma inspirado",
        "description": "Produto inspirado, venda por R$ 180. Chama no WhatsApp para pedidos.",
    }
    terms, explanation = evaluate_result(counterfeit_sale, {**BRAND, "name": "Puma"})
    assert terms and "intención de venta" in explanation


def test_rejects_puma_outlet_and_legitimate_retail_promotion():
    item = {
        **sample_item(),
        "title": "Último día de esta oferta exclusiva en Puma",
        "description": "En Promoda estrena 3 pares pagando solo 2. Promoción válida del 25 al 28 de julio. Consulta tiendas participantes.",
    }
    terms, explanation = evaluate_result(item, {**BRAND, "name": "Puma"})
    assert terms == [] and "promoción comercial legítima" in explanation

    outlet = {**item, "title": "Puma Outlet", "description": "Tenis Puma con precio especial y stock."}
    terms, explanation = evaluate_result(outlet, {**BRAND, "name": "Puma"})
    assert terms == [] and "outlet" in explanation


@pytest.mark.parametrize("country,phrase", [
    ("Argentina", "calidad 1:1 simil original"),
    ("Brasil", "primeira linha premium"),
    ("México", "calidad espejo clon 1:1"),
])
def test_country_queries_include_priority_counterfeit_terms(country, phrase):
    scraper = DashboardScraper("key", country)
    assert phrase in scraper.query("instagram", "Nike", None, 1)


def test_save_keeps_ticket_and_analyst_decisions(sessions):
    with sessions() as db:
        first, created = search_module.save_item(db, sample_item(), BRAND, "Argentina", "zapatillas", ["replica"])
        assert created
        report = db.get(ReporteBrandDefense, first)
        report.estado = "Descartado"
        report.descripcion_post += "\nNota del analista."
        db.commit()
        reference = report.referencia_interna
        item = sample_item("testA")
        item["phone"] = "+5491123456789"
        second, created = search_module.save_item(db, item, BRAND, "Argentina", "zapatillas", ["g5"])
        assert not created and first == second
        assert db.query(ReporteBrandDefense).count() == 1
        assert report.referencia_interna == reference and report.estado == "Descartado"
        assert report.telefono_publico == item["phone"]
        assert "Nota del analista" in report.descripcion_post
        assert "Fuente:" not in report.descripcion_post
        assert "Fuentes de datos públicos:" not in report.descripcion_post
        assert report.perfil is not None


def test_distinct_listings_from_same_seller_share_one_ticket(sessions):
    with sessions() as db:
        first, created = search_module.save_item(db, sample_item("listingA"), BRAND, "Argentina", "zapatillas", ["replica"])
        assert created
        second, created = search_module.save_item(db, sample_item("listingB"), BRAND, "Argentina", "zapatillas", ["g5"])
        assert not created
        assert first == second
        assert db.query(ReporteBrandDefense).count() == 1
        report = db.get(ReporteBrandDefense, first)
        assert "Evidencia adicional del mismo objetivo" in report.descripcion_post
        assert "https://instagram.com/p/listingB" in report.descripcion_post

        third, created = search_module.save_item(db, sample_item("listingC", "@otra_tienda"), BRAND, "Argentina", "zapatillas", ["g5"])
        assert created and third != first
        assert db.query(ReporteBrandDefense).count() == 2


def test_existing_tracking_variants_are_indexed(sessions):
    with sessions() as db:
        item = sample_item()
        item["url"] = "https://www.instagram.com/reel/testA/?igsh=tracking"
        report_id, _ = search_module.save_item(db, item, BRAND, "Argentina", "zapatillas", ["replica"])
        urls = search_module.existing_index(db)
        assert urls[evidence_key("https://instagram.com/p/testA")] == report_id


def test_existing_result_is_enriched_with_verified_author_and_price(sessions):
    with sessions() as db:
        original = sample_item(seller="Vendedor No Identificado")
        report_id, created = search_module.save_item(
            db, original, BRAND, "Argentina", "zapatillas", ["replica"],
        )
        assert created is True

        rediscovered = sample_item(seller="@tienda.real")
        rediscovered.update({
            "seller_author_verified": True,
            "account": "@tienda.real",
            "seller_source": "instagram_url",
            "result_type": "profile",
            "description": "Zapatillas Nike réplica. Precio: 25.000.",
        })
        same_id, created = search_module.save_item(
            db, rediscovered, BRAND, "Argentina", "zapatillas", ["replica"], report_id,
        )
        db.expire_all()
        report = db.get(ReporteBrandDefense, report_id)
        assert same_id == report_id and created is False
        assert report.titular_cuenta == "@tienda.real"
        assert report.precio_publico == 25000.0
        instagram_data = db.query(ReporteInstagramData).filter_by(reporte_id=report_id).one()
        assert instagram_data.username == "@tienda.real"
        assert instagram_data.tipo_resultado == "profile"
        assert instagram_data.fuente_username == "instagram_url"


def test_facebook_pending_seller_insert_and_duplicate_update(sessions):
    pending = sample_item("fb-post")
    pending.update({
        "url": "https://facebook.com/groups/364439847229615/posts/2961944814145759",
        "plataforma": "facebook",
        "seller": "Vendedor No Identificado",
        "account": None,
        "seller_author_verified": False,
        "seller_source": None,
        "seller_status": "pendiente",
        "seller_verified_at": None,
        "seller_failure_reason": "autor no disponible en fuentes públicas",
    })
    with sessions() as db:
        report_id, created = search_module.save_item(
            db, pending, BRAND, "Argentina", "zapatillas", ["g5"],
        )
        assert created is True
        report = db.get(ReporteBrandDefense, report_id)
        facebook_data = db.query(ReporteFacebookData).filter_by(reporte_id=report_id).one()
        assert facebook_data.seller_name is None
        assert facebook_data.estado_vendedor == "pendiente"

        verified = {**pending,
            "seller": "Maxi Damian",
            "seller_author_verified": True,
            "seller_source": "facebook_playwright",
            "seller_status": "identificado",
            "seller_verified_at": datetime.now(timezone.utc),
            "seller_failure_reason": None,
        }
        same_id, created = search_module.save_item(
            db, verified, BRAND, "Argentina", "zapatillas", ["g5"], report_id,
        )
        db.expire_all()
        report = db.get(ReporteBrandDefense, report_id)
        assert same_id == report_id and created is False
        assert report.titular_cuenta == "Maxi Damian"
        facebook_data = db.query(ReporteFacebookData).filter_by(reporte_id=report_id).one()
        assert facebook_data.seller_name == "Maxi Damian"
        assert facebook_data.fuente_vendedor == "facebook_playwright"
        assert facebook_data.estado_vendedor == "identificado"

        search_module.save_item(db, pending, BRAND, "Argentina", "zapatillas", ["g5"], report_id)
        db.expire_all()
        report = db.get(ReporteBrandDefense, report_id)
        facebook_data = db.query(ReporteFacebookData).filter_by(reporte_id=report_id).one()
        assert report.titular_cuenta == "Maxi Damian"
        assert facebook_data.seller_name == "Maxi Damian"
        assert facebook_data.estado_vendedor == "identificado"


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
    correlated = []
    def correlate(db, report_ids):
        correlated.extend(report_ids)
        return {"links": 0, "clusters": 0}
    monkeypatch.setattr(search_module.CorrelationEngine, "analyze_new_reports", correlate)
    async def run():
        manager = search_module.DashboardSearchManager()
        options = {"pais": "Argentina", "provincias": ["Córdoba"], "keywords": [], "duration_minutes": 5, "plataformas": ["facebook", "instagram", "tiktok", "mercadolibre"]}
        manager.start(1, options, [BRAND])
        while manager.state["queries_done"] < 12:
            await asyncio.sleep(0.001)
        await manager.stop()
        assert manager.state["status"] == "stopped"
        assert manager.state["saved"] == 1 and manager.state["duplicates"] >= 5
        assert manager.state["queries_done"] >= 12
        assert all(platforms.count(p) >= 3 for p in options["plataformas"])
        assert len(enrichment_calls) == 1
        assert len(correlated) == 1
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


def test_editable_duration_units_and_limits():
    request = DashboardSearchRequest(
        brand_ids=[1], duration_value=3, duration_unit="weeks", target_objectives=25,
    )
    assert search_module.requested_duration_seconds(request.model_dump()) == 3 * 7 * 24 * 60 * 60
    assert request.target_objectives == 25
    with pytest.raises(ValueError):
        DashboardSearchRequest(brand_ids=[1], duration_value=121, duration_unit="months", target_objectives=1)


def test_runner_stops_when_unique_objective_target_is_reached(monkeypatch, sessions):
    monkeypatch.setattr(search_module, "SessionLocal", sessions)
    monkeypatch.setattr(search_module, "get_active_api_key", lambda *args, **kwargs: "test-key")
    counter = 0

    async def fake_search(self, client, platform, keyword, province, variant):
        nonlocal counter
        counter += 1
        return [sample_item(f"target{counter}", f"@target_seller_{counter}")]

    async def fake_enrich(self, client, item):
        return item

    monkeypatch.setattr(DashboardScraper, "search", fake_search)
    monkeypatch.setattr(DashboardScraper, "enrich", fake_enrich)

    async def run():
        manager = search_module.DashboardSearchManager()
        options = {
            "pais": "Argentina", "provincias": ["Córdoba"], "keywords": [],
            "duration_value": 1, "duration_unit": "days", "target_objectives": 2,
            "plataformas": ["instagram"],
        }
        manager.start(1, options, [BRAND])
        await manager.task
        assert manager.state["status"] == "completed"
        assert manager.state["finish_reason"] == "target"
        assert manager.state["saved"] == 2
        assert not manager.state["is_running"]

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
