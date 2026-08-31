"""
Configuración central de la aplicación Net Holmes.
Utiliza pydantic-settings para cargar variables de entorno con valores por defecto.
"""

from pathlib import Path
from pydantic_settings import BaseSettings

PROVINCIAS_AR = [
    {"lat": -34.6037, "lon": -58.3816, "name": "CABA", "marketplace_slug": "buenosaires"},
    {"lat": -34.9205, "lon": -57.9536, "name": "Buenos Aires", "marketplace_slug": "buenosaires"},
    {"lat": -28.4696, "lon": -65.7852, "name": "Catamarca", "marketplace_slug": "catamarca"},
    {"lat": -27.4606, "lon": -58.9839, "name": "Chaco", "marketplace_slug": "resistencia"},
    {"lat": -43.3002, "lon": -65.1023, "name": "Chubut", "marketplace_slug": "rawson"},
    {"lat": -31.4201, "lon": -64.1888, "name": "Córdoba", "marketplace_slug": "cordoba"},
    {"lat": -27.4692, "lon": -58.8306, "name": "Corrientes", "marketplace_slug": "corrientes"},
    {"lat": -31.7319, "lon": -60.5288, "name": "Entre Ríos", "marketplace_slug": "parana"},
    {"lat": -26.1849, "lon": -58.1731, "name": "Formosa", "marketplace_slug": "formosa"},
    {"lat": -24.1858, "lon": -65.2995, "name": "Jujuy", "marketplace_slug": "sansalvadordejujuy"},
    {"lat": -36.6167, "lon": -64.2833, "name": "La Pampa", "marketplace_slug": "santarosa"},
    {"lat": -29.4135, "lon": -66.8565, "name": "La Rioja", "marketplace_slug": "larioja"},
    {"lat": -32.8895, "lon": -68.8458, "name": "Mendoza", "marketplace_slug": "mendoza"},
    {"lat": -27.3671, "lon": -55.8961, "name": "Misiones", "marketplace_slug": "posadas"},
    {"lat": -38.9516, "lon": -68.0591, "name": "Neuquén", "marketplace_slug": "neuquen"},
    {"lat": -41.1456, "lon": -71.3082, "name": "Río Negro", "marketplace_slug": "viedma"},
    {"lat": -24.7821, "lon": -65.4232, "name": "Salta", "marketplace_slug": "salta"},
    {"lat": -31.5375, "lon": -68.5364, "name": "San Juan", "marketplace_slug": "sanjuan"},
    {"lat": -33.2950, "lon": -66.3356, "name": "San Luis", "marketplace_slug": "sanluis"},
    {"lat": -51.6226, "lon": -69.2181, "name": "Santa Cruz", "marketplace_slug": "riogallegos"},
    {"lat": -31.6333, "lon": -60.7000, "name": "Santa Fe", "marketplace_slug": "santafe"},
    {"lat": -27.7951, "lon": -64.2615, "name": "Santiago del Estero", "marketplace_slug": "santiagodelestero"},
    {"lat": -54.8019, "lon": -68.3030, "name": "Tierra del Fuego", "marketplace_slug": "ushuaia"},
    {"lat": -26.8241, "lon": -65.2226, "name": "Tucumán", "marketplace_slug": "tucuman"}
]

PROVINCIAS_SIGLAS = {
    "CABA": ["CABA", "Ciudad de Buenos Aires", "Capital Federal"],
    "Buenos Aires": ["Buenos Aires", "BsAs", "Provincia de Buenos Aires", "PBA"],
    "Catamarca": ["Catamarca"],
    "Chaco": ["Chaco"],
    "Chubut": ["Chubut"],
    "Córdoba": ["Córdoba", "Cba"],
    "Corrientes": ["Corrientes"],
    "Entre Ríos": ["Entre Ríos", "Entre Rios"],
    "Formosa": ["Formosa"],
    "Jujuy": ["Jujuy"],
    "La Pampa": ["La Pampa"],
    "La Rioja": ["La Rioja"],
    "Mendoza": ["Mendoza", "Mza"],
    "Misiones": ["Misiones"],
    "Neuquén": ["Neuquén", "Neuquen"],
    "Río Negro": ["Río Negro", "Rio Negro"],
    "Salta": ["Salta"],
    "San Juan": ["San Juan"],
    "San Luis": ["San Luis"],
    "Santa Cruz": ["Santa Cruz"],
    "Santa Fe": ["Santa Fe", "Rosario"],
    "Santiago del Estero": ["Santiago del Estero"],
    "Tierra del Fuego": ["Tierra del Fuego"],
    "Tucumán": ["Tucumán", "Tucuman"]
}

EXTRACTION_LIMITS = [2, 5, 10, 20, 25, 50, 75, 100]

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://postgres:root@localhost:5432/brand_check_defense_db"
    SECRET_KEY: str = "f7a3b2e91d4c08f65e2a7b3d9c1f4e8a6b0d2c5e7f9a1b3d5e7f0a2c4e6b8d0"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    CRON_HOUR: int = 2
    CRON_MINUTE: int = 0
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]
    CEREBRAS_API_KEY: str | None = None
    RAPIDAPI_KEY: str | None = None
    APIFY_API_TOKEN: str | None = None
    
    # Feature Flags para RapidAPI Fallback
    USE_RAPIDAPI_FB: bool = False
    USE_RAPIDAPI_IG: bool = False
    USE_RAPIDAPI_TT: bool = False
    
    # Actores de Apify Parametrizados
    APIFY_ACTOR_FB: str = "apify/facebook-marketplace-scraper"
    APIFY_ACTOR_TT: str = "clockworks/tiktok-scraper"
    APIFY_ACTOR_IG: str = "apify/instagram-scraper"
    
    # Límites
    APIFY_MAX_ITEMS: int = 30
    APIFY_MAX_DAYS: int = 90
    DEFAULT_CITY: str = "Buenos Aires"
    DEFAULT_PROXY_COUNTRY: str = "AR"
    
    # Retries Scraper
    SCRAPER_MAX_RETRIES: int = 3
    SCRAPER_RETRY_BASE_DELAY: int = 2
    
    # Apify Cloud — Backup Invisible (Nivel 3)
    # False por defecto: solo se activa si el analista lo fuerza
    USE_APIFY: bool = False
    
    # Apify Motor Independiente (Fase 2)
    USE_APIFY_FASE2: bool = False
    
    CRON_ENABLED: bool = False
    TIMEZONE: str = 'America/Argentina/Buenos_Aires'

    # Limites Globales de Apify (pueden sobreescribirse por variable)
    MAX_PUBLICATIONS_PER_CITY: int = 100
    MAX_COMMENTS_PER_PUBLICATION: int = 50

    # ─── WhatsApp Cloud API (Meta Business Platform) ───
    WHATSAPP_ACCESS_TOKEN: str | None = None
    WHATSAPP_PHONE_NUMBER_ID: str | None = None
    WHATSAPP_BUSINESS_ACCOUNT_ID: str | None = None
    # ─── Google Serper / Custom Search API ───
    SERPER_API_KEY: str | None = None
    GOOGLE_CSE_API_KEY: str | None = None
    GOOGLE_CSE_CX: str | None = None

    # ─── Mercado Libre Developers API (developers.mercadolibre.com.ar) ───
    MERCADOLIBRE_APP_ID: str | None = None
    MERCADOLIBRE_CLIENT_SECRET: str | None = None
    MERCADOLIBRE_ACCESS_TOKEN: str | None = None

    # ─── Certstream / SSL Transparency Monitor ───
    ENABLE_CERTSTREAM_SCAN: bool = True

    model_config = {
        "env_file": (
            str(Path(__file__).resolve().parent / ".env"),
            str(Path(__file__).resolve().parent.parent / ".env"),
            ".env",
        ),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

settings = Settings()
