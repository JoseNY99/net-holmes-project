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
from routers import auth, users, brands, cron, reports_defense, dashboard, admin_logs, correlations, chat, whatsapp_webhook, settings as admin_settings

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
            
        # Migraciones pendientes del Cron (ej. provincias_seleccionadas, limite_extraccion)
        try:
            conn.execute(text("ALTER TABLE cron_config ADD COLUMN provincias_seleccionadas TEXT DEFAULT '[\"Buenos Aires\"]';"))
            conn.commit()
        except Exception:
            conn.rollback()
            
        try:
            conn.execute(text("ALTER TABLE cron_config ADD COLUMN proveedor VARCHAR(50) DEFAULT 'apify';"))
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
        
        # 6. Content Security Policy permisiva con evidencias multimedia (CVSS 6.1 / T1059)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "img-src 'self' data: https: blob: http:; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "connect-src 'self' https: http: ws: wss:; "
            "font-src 'self' data: https:; "
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
