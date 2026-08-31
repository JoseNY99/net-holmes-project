"""
Scraper de Instagram usando instagrapi.
Requiere autenticación (cuentas carnada)
"""
from base_scraper import ChillModeScraper
# from instagrapi import Client

def run_instagram_scraper():
    scraper = ChillModeScraper("Instagram")
    
    # cl = Client()
    # cl.login("cuenta_carnada", "password123")
    
    hashtags = ["#replicasexactas", "#zapatillasimportadas"]
    
    for tag in hashtags:
        # medias = cl.hashtag_medias_top(tag, amount=10)
        # Placeholder simulado:
        medias = [{"user": "fake_store_123", "url": "https://instagram.com/p/123", "text": "Replica AAA 100% real", "price": 15000}]
        
        for m in medias:
            if not scraper.add_report(
                pais="ARGENTINA", 
                producto="Zapatillas", 
                marca="Nike", 
                titular=m["user"], 
                url=m["url"], 
                desc=m["text"], 
                precio=m.get("price")
            ):
                break # límite alcanzado
            
            scraper.human_pause()
            
    scraper.send_to_ingest()

if __name__ == "__main__":
    run_instagram_scraper()
