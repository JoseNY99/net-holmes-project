def matches_configured_product(text: str, brand_name: str, configured_products: str = None) -> bool:
    """
    Verifica que el texto de la publicación contenga la marca y, si existen, 
    los productos específicos configurados en la base de datos.
    """
    if not text:
        return False
        
    text_lower = text.lower()
    brand_lower = brand_name.lower()
    
    # 1. Exigencia absoluta: La marca DEBE estar mencionada
    if brand_lower not in text_lower:
        return False
        
    # 2. Si la marca no tiene productos específicos configurados en tu dashboard, pasa directo
    if not configured_products:
        return True
        
    # 3. Si configuraste productos (ej: "zapatillas, camperas, gorras"), exige al menos uno
    productos = [p.strip().lower() for p in configured_products.split(",") if p.strip()]
    
    if not productos:
        return True
        
    return any(prod in text_lower for prod in productos)