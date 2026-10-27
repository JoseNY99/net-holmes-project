import sys
import asyncio
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from config import settings
from database import Base, engine, SessionLocal
from routers import auth, users, brands, cron, reports_defense, dashboard, admin_logs, correlations, chat, whatsapp_webhook, settings as admin_settings, api_keys, fase1_auto_completor

# Configurar Rate Limiter
limiter = Limiter(key_func=get_remote_address)

# Importar modelos para que Base.metadata los registre
import models  # noqa: F401

# Import scheduler
from services.cron_manager import scheduler, update_job_schedule

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Evento de inicio: crea las tablas si no existen y actualiza columnas."""
    Base.metadata.create_all(bind=engine)
    
    from sqlalchemy import text
    with engine.connect() as conn:
        # Migración de auto-reparación de tipos de columna en PostgreSQL
        pg_type_fixes = [
            "ALTER TABLE reportes_brand_defense ALTER COLUMN precio_publico TYPE double precision USING (NULLIF(regexp_replace(precio_publico::text, '[^0-9.]', '', 'g'), '')::double precision);",
            "ALTER TABLE reportes_brand_defense ALTER COLUMN seguidores_infractor TYPE integer USING (NULLIF(regexp_replace(seguidores_infractor::text, '[^0-9]', '', 'g'), '')::integer);",
            "ALTER TABLE reportes_brand_defense ALTER COLUMN url_evidencia TYPE text;",
            "ALTER TABLE reportes_brand_defense ALTER COLUMN descripcion_post TYPE text;",
        ]
        for fix_sql in pg_type_fixes:
            try:
                conn.execute(text(fix_sql))
                conn.commit()
            except Exception:
                conn.rollback()

        # Migración de sesión única (Single Active Device / Session)
        try:
            conn.execute(text("ALTER TABLE users ADD COLUMN session_token VARCHAR(100);"))
            conn.commit()
        except Exception:
            conn.rollback()
            pass

        # Migración de estado en tabla products
        try:
            conn.execute(text("ALTER TABLE products ADD COLUMN estado VARCHAR(20) DEFAULT 'activa';"))
            conn.commit()
        except Exception:
            conn.rollback()
            pass
            
        # Migración de Fase 1 para acomodar scrapeo orgánico (Followers)
        try:
            conn.execute(text("ALTER TABLE reportes_brand_defense ADD COLUMN seguidores_infractor INTEGER;"))
            conn.commit()
        except Exception:
            conn.rollback()
            pass

        try:
            conn.execute(text("ALTER TABLE reportes_brand_defense ADD COLUMN moneda VARCHAR(10) DEFAULT 'ARS';"))
            conn.commit()
        except Exception:
            conn.rollback()
            pass
            
        # Migraciones pendientes del Cron (ej. provincias_seleccionadas, limite_extraccion)
        try:
            conn.execute(text("ALTER TABLE cron_config ADD COLUMN provincias_seleccionadas TEXT DEFAULT '[\"Buenos Aires\"]';"))
            conn.commit()
        except Exception:
            conn.rollback()

        try:
            conn.execute(text("ALTER TABLE cron_config ADD COLUMN pais_seleccionado VARCHAR(100) NOT NULL DEFAULT 'Argentina';"))
            conn.commit()
        except Exception:
            conn.rollback()
            
        try:
            conn.execute(text("ALTER TABLE cron_config ADD COLUMN proveedor VARCHAR(50) DEFAULT 'google_meli_osint';"))
            conn.commit()
        except Exception:
            conn.rollback()
            
        try:
            conn.execute(text("ALTER TABLE cron_config ADD COLUMN limite_extraccion INTEGER DEFAULT 10;"))
            conn.commit()
        except Exception:
            conn.rollback()
            
        # Nuevos límites por plataforma
        for plat in ['fb', 'ig', 'tt', 'ml']:
            try:
                conn.execute(text(f"ALTER TABLE cron_config ADD COLUMN limite_extraccion_{plat} INTEGER DEFAULT 10;"))
                conn.commit()
            except Exception:
                conn.rollback()
            
        try:
            conn.execute(text("ALTER TABLE cron_config ADD COLUMN fecha_inicio TIMESTAMP WITH TIME ZONE;"))
            conn.commit()
        except Exception:
            conn.rollback()
            
        try:
            conn.execute(text("ALTER TABLE cron_config ADD COLUMN fecha_fin TIMESTAMP WITH TIME ZONE;"))
            conn.commit()
        except Exception:
            conn.rollback()

        # ─── Migraciones del módulo Chat / WhatsApp Honeypot ───
        chat_migrations = [
            "ALTER TABLE conversations ADD COLUMN is_bot_active BOOLEAN DEFAULT TRUE;",
            "ALTER TABLE conversations ADD COLUMN whatsapp_phone VARCHAR(30);",
            "ALTER TABLE messages ADD COLUMN whatsapp_message_id VARCHAR(100);",
            "ALTER TABLE messages ADD COLUMN media_url TEXT;",
            "ALTER TABLE messages ADD COLUMN extracted_entities TEXT;",
        ]
        for migration in chat_migrations:
            try:
                conn.execute(text(migration))
                conn.commit()
            except Exception:
                conn.rollback()
    
    # Iniciar el planificador de Cron
    scheduler.start()
    with SessionLocal() as db:
        update_job_schedule(db)
    
    yield
    from services.dashboard_search import dashboard_search
    await dashboard_search.stop()
    scheduler.shutdown()

app = FastAPI(
    title="Net Holmes API",
    version="1.0.0",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Middleware de Cabeceras de Seguridad (Hardening WebVuln-MITRE)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        
        # 1. Protección contra MIME-Sniffing (CVSS 4.3 / T1039)
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # 2. Protección contra Clickjacking / UI Redressing
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        
        # 3. Filtro de protección XSS en navegadores compatibles
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # 4. Política de Referrer para no filtrar datos sensibles
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # 5. HSTS (Strict-Transport-Security) (CVSS 3.7 / T1562.001)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # 6. Content Security Policy permisiva con evidencias multimedia y Google Fonts (CVSS 6.1 / T1059)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "img-src 'self' data: https: blob: http:; "
            "media-src 'self' data: https: blob: http:; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "connect-src 'self' https: http: ws: wss:; "
            "font-src 'self' data: https: https://fonts.gstatic.com; "
            "frame-ancestors 'self';"
        )
        return response

app.add_middleware(SecurityHeadersMiddleware)

# Configuración de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registro de routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(brands.router)
app.include_router(cron.router)
app.include_router(reports_defense.router)
app.include_router(dashboard.router)
app.include_router(admin_logs.router)
app.include_router(correlations.router)
app.include_router(chat.router)
app.include_router(whatsapp_webhook.router)
app.include_router(admin_settings.router)
app.include_router(api_keys.router)
app.include_router(fase1_auto_completor.router)

# Router para finalizar Fase 2 e informes únicos
from routers.chat_fase2_finalizer import router as chat_fase2_router
app.include_router(chat_fase2_router)

# Servir archivos estáticos (Screenshots y Evidencias)
import os
from pathlib import Path
from fastapi.staticfiles import StaticFiles
static_dir = Path(__file__).resolve().parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", tags=["Health"])
def health_check():
    """Endpoint de verificación de salud del servicio."""
    return {"status": "ok", "service": "Net Holmes API"}


from fastapi.responses import HTMLResponse

@app.get("/privacy", response_class=HTMLResponse, tags=["Legal"])
def privacy_policy():
    """Política de privacidad pública requerida por Meta for Developers para pasar a Modo En Vivo."""
    return """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>Net Holmes - Política de Privacidad</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; line-height: 1.6; color: #1e293b; }
            h1 { color: #0B3256; }
            h2 { color: #0369a1; margin-top: 24px; }
        </style>
    </head>
    <body>
        <h1>Política de Privacidad de Net Holmes</h1>
        <p><strong>Última actualización:</strong> Septiembre 2026</p>
        <p>Net Holmes es una plataforma de defensa de marca, ciberseguridad y prevención de infracciones comerciales online. Los canales de mensajería (incluyendo WhatsApp Business Platform) se gestionan de forma estrictamente confidencial para verificación de autenticidad de productos y transacciones.</p>
        <h2>Tratamiento y Protección de Datos</h2>
        <p>Los datos procesados se custodian bajo estándares de seguridad para fines exclusivos de auditoría judicial y peritaje de propiedad industrial. No vendemos ni compartimos datos con terceros con fines publicitarios.</p>
        <h2>Contacto</h2>
        <p>Para consultas sobre el tratamiento de datos o solicitudes de supresión: <strong>compliance@netholmes.tech</strong></p>
    </body>
    </html>
    """
