"""
Scraper Login-Free para Facebook usando facebook-scraper.
Apunta exclusivamente a Páginas Públicas para extraer posts sin inyectar cookies.
"""
from facebook_scraper import get_posts
import asyncio
from services.cron_logger import cron_logger

async def scrape_facebook_public(keyword: str, max_results: int = 10, city_name: str = "Argentina"):
    results = []
    
    # En Facebook Login-Free, lo ideal es buscar dentro de páginas conocidas
    # Agregamos la provincia/Argentina para acotar si quisiéramos, pero para no perder resultados 
    # buscamos la página base de la marca.
    pages_to_scan = [keyword.strip().replace(" ", "")]
    cron_logger.log(f"[Facebook] Modo Login-Free. Escaneando páginas estimadas: {pages_to_scan}")
    
    for page in pages_to_scan:
        try:
            cron_logger.log(f"[Facebook] Extrayendo posts de la página: {page} (limitando a 2 'pages' internas)")
            # get_posts es síncrono y bloqueante, usamos to_thread si estuviéramos en un server real.
            # Aquí lo llamamos directamente para simplificar.
            count = 0
            for post in get_posts(page, pages=2):
                if count >= max_results:
                    break
                    
                url = post.get('post_url', '')
                desc = post.get('text', '')
                username = post.get('username', page)
                
                # Check si la keyword está en el texto para filtrar
                if keyword.lower() in desc.lower() or True: # True para capturar de la página
                    results.append({
                        "plataforma": "facebook",
                        "titular_cuenta": username,
                        "producto_catalogo": keyword,
                        "url_evidencia": url,
                        "descripcion_post": desc,
                        "seguidores_infractor": None, # Difícil extraer likes de página desde get_posts sin llamadas extra
                        "platform_data": {
                            "facebook": {
                                "seller_name": username,
                                "comments_text": "",
                                "image_urls": "[]"
                            }
                        }
                    })
                    count += 1
                    cron_logger.log(f"[Facebook] 📝 Post extraído de {username} ({count}/{max_results})")
                    
        except Exception as e:
            cron_logger.log(f"⚠️ [Facebook] Error scraping Facebook page {page}: {e}")
            
    cron_logger.log(f"[Facebook] Extracción exitosa: {len(results)} posts parseados.")
    return results

if __name__ == "__main__":
    res = asyncio.run(scrape_facebook_public("nintendo", 2))
    print(res)
