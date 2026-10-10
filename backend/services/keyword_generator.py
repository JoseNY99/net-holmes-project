"""Servicio generador de palabras clave a partir de marcas y comportamientos."""

import httpx
import json
from config import settings
from models.brand import Brand
from services.cron_logger import cron_logger

async def generate_keywords(marca: Brand, plataforma: str = "general") -> list[str]:
    """
    Usa Cerebras AI (Llama 3.3 70B) como analista OSINT para generar jerga de mercado negro 
    específica de la plataforma y así minimizar consultas en Apify.
    """
    # Recopilar contexto de la marca
    productos = [p.nombre for p in marca.products if getattr(p, "estado", "activa") == "activa"] if getattr(marca, "products", None) else []
    comportamientos = [c.nombre for c in marca.comportamientos] if getattr(marca, "comportamientos", None) else []
    
    # Si el administrador cargó productos (palabras clave exactas), usarlas con variantes
    if productos:
        productos_con_marca = []
        for p in productos:
            productos_con_marca.append(f"{marca.nombre} {p}")
            productos_con_marca.append(f"{marca.nombre} {p} réplica")
        cron_logger.log(f"[Keywords] Usando palabras clave configuradas con variantes de réplica: {productos_con_marca}")
        return productos_con_marca

    # Si no hay productos, generar la marca junto con los términos clave de réplicas e importadas
    fallback_keywords = [
        f"{marca.nombre} réplica",
        f"{marca.nombre} importadas",
        f"{marca.nombre} G5",
        marca.nombre
    ]
    cron_logger.log(f"[Keywords] Usando términos de mercado informal para '{marca.nombre}': {fallback_keywords}")
    return fallback_keywords
