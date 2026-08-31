import asyncio
from typing import List, Dict, Any, AsyncGenerator
from config import settings
from services.cron_logger import cron_logger
from scrapers.filtro_comercial import filtrar_item_comercial

# Import the existing Apify scrapers
from scrapers.facebook_apify import FacebookApifyScraper
from scrapers.instagram_scraper import InstagramApifyScraper
from scrapers.tiktok_apify import TikTokApifyScraper
from scrapers.mercadolibre import MercadoLibreScraper

class ApifyMotorFase2:
    def __init__(self):
        self.fb_apify = FacebookApifyScraper()
        self.ig_apify = InstagramApifyScraper()
        self.tt_apify = TikTokApifyScraper()
        self.ml_scraper = MercadoLibreScraper()

    async def execute(self, keyword: str, plataformas: List[str], provincias: List[str], limite: int) -> AsyncGenerator[Dict[str, Any], None]:
        if not settings.APIFY_API_TOKEN:
            cron_logger.log("❌ [Apify Premium] Error: APIFY_API_TOKEN no configurado.")
            return

        cron_logger.log(f"🚀 [Apify Premium] Iniciando escaneo para '{keyword}' en {len(provincias)} provincias. Límite: {limite}")
        
        # Override the limit in settings temporarily for this run
        original_limit = settings.APIFY_MAX_ITEMS
        settings.APIFY_MAX_ITEMS = limite

        try:
            for platform in plataformas:
                cron_logger.log(f"🌐 [Apify Premium] Escaneando {platform}...")
                
                # If no provinces specified, run once with "Argentina"
                target_locations = provincias if provincias else ["Argentina"]
                
                for loc in target_locations:
                    cron_logger.log(f"📍 [Apify Premium] -> {platform} - Ubicación: {loc}")
                    
                    scraper = None
                    if platform == "facebook":
                        scraper = self.fb_apify
                    elif platform == "instagram":
                        scraper = self.ig_apify
                    elif platform == "tiktok":
                        scraper = self.tt_apify
                    elif platform == "mercadolibre":
                        scraper = self.ml_scraper
                    
                    if not scraper:
                        continue

                    try:
                        count = 0
                        descartados = 0
                        async for item in scraper.scrape(keyword, city_name=loc):
                            # Ensure it's marked as Apify Premium source
                            item["platform_data"] = item.get("platform_data", {})
                            item["platform_data"]["source_engine"] = "Apify_Premium"
                            
                            # Standardize location
                            item["location"] = loc
                            
                            # Normalizar campos devueltos por Apify
                            pd = item.get("platform_data", {})
                            if "seller_profile" not in item:
                                item["seller_profile"] = {}
                                
                            # Titular
                            titular = (
                                pd.get("ownerUsername") or 
                                (pd.get("authorMeta") or {}).get("name") or 
                                pd.get("profileName") or 
                                pd.get("username") or 
                                item["seller_profile"].get("name")
                            )
                            if titular:
                                item["seller_profile"]["name"] = titular
                                
                            # Seguidores
                            seguidores = (
                                pd.get("ownerFollowersCount") or 
                                (pd.get("authorMeta") or {}).get("fans") or 
                                pd.get("followersCount") or 
                                pd.get("followers") or 
                                item["seller_profile"].get("followers")
                            )
                            if seguidores is not None:
                                try:
                                    item["seller_profile"]["followers"] = int(seguidores)
                                except:
                                    pass
                            
                            # ── FILTRO DE RELEVANCIA COMERCIAL ──
                            # Facebook Marketplace y MercadoLibre son inherentemente comerciales
                            # Filtro comercial MOVIDO a cron_manager.py (capa única de filtrado)
                            
                            yield item
                            count += 1
                            if count >= limite:
                                break
                        
                        if descartados > 0:
                            cron_logger.log(f"🚫 [Apify Premium] {descartados} items de {platform} descartados por no ser venta.")
                            
                    except Exception as e:
                        cron_logger.log(f"⚠️ [Apify Premium] Error en {platform} ({loc}): {str(e)}")
                        
        finally:
            # Restore original limit
            settings.APIFY_MAX_ITEMS = original_limit
            
        cron_logger.log("✅ [Apify Premium] Escaneo completado.")

