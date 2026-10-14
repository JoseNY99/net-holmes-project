"""
Cliente LLM Unificado Agnóstico — Cerebras / DeepSeek.

Consume directamente la REST API compatible con Chat Completions vía `httpx`,
eliminando dependencias de librerías externas como `openai`.
Lee LLM_PROVIDER del .env o de la base de datos para decidir qué proveedor usar.

Cerebras: Ultra-rápido (~200ms), ideal para honeypot en tiempo real.
DeepSeek (por defecto): Inteligente, económico, excelente para simulación y extracción.
"""

import re
import json
import httpx
from datetime import datetime
from typing import Optional, Dict, Any
from config import settings
from services.cron_logger import cron_logger

# ─── Configuración de Proveedores ───────────────────────────────────────────

LLM_CONFIGS = {
    "cerebras": {
        "base_url": "https://api.cerebras.ai/v1",
        "model": "llama-3.3-70b",
        "api_key_attr": "CEREBRAS_API_KEY",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "api_key_attr": "DEEPSEEK_API_KEY",
    },
}

# ─── Prompt de Extracción Estructurado ──────────────────────────────────────

EXTRACTION_SYSTEM_PROMPT = """Eres un analista de inteligencia OSINT especializado en extraer datos de identidad y financieros de conversaciones de chat en español argentino.

Tu trabajo es analizar mensajes de texto y extraer TODAS las entidades que encuentres. Responde ÚNICAMENTE con un objeto JSON válido.

Entidades a buscar:
- "dni_cedula": Documento Nacional de Identidad (7-8 dígitos, a veces con puntos: 35.123.456)
- "cuit_cuil_ruc": CUIT/CUIL argentino (formato: 20-35123456-7 o variantes sin guiones)
- "cvu_cbu": CBU (22 dígitos numéricos) o CVU (22 dígitos empezando en 000)
- "alias_bancario": Alias de MercadoPago/banco (formato: palabra.palabra.palabra o similar)
- "email": Correo electrónico
- "telefono_privado": Número de teléfono (cualquier formato argentino)
- "direccion_exacta": Dirección física mencionada (calle, número, piso, localidad)
- "precio_final_cotizado": Precio mencionado (en ARS o USD)
- "banco": Nombre del banco o billetera virtual (MercadoPago, Brubank, Ualá, etc.)
- "nombre_real": Nombre real de la persona si lo revela

Reglas:
1. Si NO encuentras una entidad, NO la incluyas en el JSON (omítela).
2. Si el mensaje no contiene datos relevantes, responde con un JSON vacío: {}
3. Limpia los valores: sin espacios extra, sin caracteres especiales innecesarios.
4. Responde SOLO con el JSON, sin texto adicional, sin markdown, sin backticks."""

EXTRACTION_USER_TEMPLATE = """Analiza el siguiente mensaje de chat y extrae todas las entidades de identidad/financieras que encuentres:

Mensaje: "{message_text}"

JSON:"""

# ─── Prompt de Clasificación de Publicaciones OSINT / Brand Protection ──────

BRAND_PROTECTION_OSINT_SYSTEM_PROMPT = """Actúa como un Analista Senior de Brand Protection y OSINT. Tu tarea es analizar los datos extraídos de una publicación de redes sociales y determinar estrictamente dos cosas: 
1. Si el producto ofrecido es una FALSIFICACIÓN/RÉPLICA (descartando productos originales nuevos o usados).
2. Si el vendedor o la publicación está orientada a ARGENTINA.

DATOS DE LA PUBLICACIÓN:
- Plataforma: {plataforma}
- Título/Descripción: {descripcion}
- Comentarios extraídos: {comentarios}
- Ubicación/Metadatos: {ubicacion}
- Precio detectado: {precio}

REGLAS DE EVALUACIÓN (FALSIFICACIÓN):
- ES FAKE: Si menciona términos como "réplica", "G5", "AAA", "1.1", "importadas" (junto a precios irracionalmente bajos para la marca), "espejo", "clon".
- NO ES FAKE (RECHAZAR): Si dice explícitamente "100% original", "usado" o "tienda oficial". También rechaza "pre-loved", "segunda mano", "vendo mis zapatillas" y distribuidores autorizados.
- La regla NO ES FAKE tiene prioridad si también aparecen indicadores de falsificación.

REGLAS DE EVALUACIÓN (GEOGRAFÍA E IDIOMA):
- ES ARGENTINA: Si menciona provincias argentinas, si el precio está en "ARS" o "pesos", o si usa jerga/logística local como "talle", "lucas" o "Andreani".
- NO ES ARGENTINA (RECHAZAR): Si los comentarios están en árabe, inglés, ruso o portugués. También rechaza menciones de homónimos/lugares extranjeros como Bogotá o Santa Fe de Estados Unidos, así como envíos internacionales genéricos.
- La regla NO ES ARGENTINA tiene prioridad si también aparecen indicadores locales.

FORMATO DE SALIDA (ESTRICTAMENTE JSON):
Debes responder ÚNICAMENTE con un objeto JSON válido, sin markdown, sin texto adicional y sin claves extra. Los dos primeros valores deben ser booleanos JSON y "motivo" una cadena:
{
  "es_falsificacion": false,
  "es_argentina": false,
  "motivo": "Breve explicación de por qué se aprobó o rechazó"
}"""

BRAND_PROTECTION_USER_TEMPLATE = """DATOS DE LA PUBLICACIÓN:
- Plataforma: {plataforma}
- Título/Descripción: {descripcion}
- Comentarios extraídos: {comentarios}
- Ubicación/Metadatos: {ubicacion}
- Precio detectado: {precio}"""



def _get_llm_config_and_key():
    """Retorna (base_url, model, api_key, provider_name) según configuración en DB o entorno."""
    from services.api_key_service import get_active_api_key

    def _clean_key(prov: str, k: str) -> str:
        if not k:
            return ""
        k = k.strip()
        if prov == "deepseek" and not k.startswith("sk-") and len(k) >= 20:
            return f"sk-{k}"
        return k

    # 1. Verificar si DeepSeek está configurado en Base de Datos o en entorno
    deepseek_db_key = get_active_api_key("deepseek")
    deepseek_env_key = getattr(settings, "DEEPSEEK_API_KEY", None)
    deepseek_key = _clean_key("deepseek", deepseek_db_key or deepseek_env_key or "")

    preferred = (getattr(settings, "LLM_PROVIDER", None) or "deepseek").lower().strip()

    # Si hay clave de DeepSeek activa en DB o es el preferido:
    if deepseek_key and (preferred == "deepseek" or deepseek_db_key or not get_active_api_key("cerebras")):
        config = LLM_CONFIGS["deepseek"]
        cron_logger.log(f"[LLM] 🧠 Consumiendo API de DEEPSEEK ({config['model']}) para Honeypot y Extracción.")
        return config["base_url"], config["model"], deepseek_key, "deepseek"

    # 2. Comprobar Cerebras
    cerebras_key = get_active_api_key("cerebras") or getattr(settings, "CEREBRAS_API_KEY", None)
    if cerebras_key and cerebras_key.strip():
        config = LLM_CONFIGS["cerebras"]
        cron_logger.log(f"[LLM] 🧠 Consumiendo API de CEREBRAS ({config['model']}).")
        return config["base_url"], config["model"], cerebras_key.strip(), "cerebras"

    # 3. Fallback a DeepSeek si hay alguna clave disponible
    if deepseek_key:
        config = LLM_CONFIGS["deepseek"]
        cron_logger.log(f"[LLM] 🧠 Consumiendo API de DEEPSEEK ({config['model']}) como fallback.")
        return config["base_url"], config["model"], deepseek_key, "deepseek"

    cron_logger.log("[LLM] ℹ️ Sin API Key de DeepSeek/Cerebras activa en DB. Se usarán respuestas de contingencia contextual.")
    return None, None, None, None


async def call_llm_chat_completion(
    messages: list,
    temperature: float = 0.7,
    max_tokens: int = 200,
) -> tuple[str, str | None]:
    """
    Realiza la llamada HTTP a DeepSeek o Cerebras usando httpx nativo sin requerir la librería openai.
    Returns:
        tuple (reply_text: str, error_detail: str | None)
    """
    base_url, model, api_key, provider = _get_llm_config_and_key()
    if not api_key:
        return "", "No hay API Key de DeepSeek/Cerebras activa en la Base de Datos."

    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    try:
        cron_logger.log(f"[LLM] 🧠 Enviando petición HTTP a {provider.upper()} ({model})...")
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices", [])
                if choices and "message" in choices[0]:
                    reply = choices[0]["message"].get("content", "").strip()
                    return reply, None
                return "", f"Respuesta inesperada de {provider}: no se encontró contenido"
            else:
                try:
                    err_json = resp.json()
                    err_detail = err_json.get("error", {}).get("message") or resp.text
                except Exception:
                    err_detail = resp.text
                return "", f"Error HTTP {resp.status_code} ({provider}): {err_detail}"
    except httpx.TimeoutException:
        return "", f"Timeout (30s) al conectar con {provider}."
    except Exception as e:
        return "", f"Falla de red con {provider}: {str(e)}"


# ─── Cliente Unificado ──────────────────────────────────────────────────────

async def extract_entities_llm(message_text: str) -> dict:
    """
    Envía un mensaje al LLM configurado y retorna las entidades extraídas.
    
    Returns:
        dict con las entidades encontradas, o {} si no encontró nada.
    """
    messages = [
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": EXTRACTION_USER_TEMPLATE.format(message_text=message_text)},
    ]

    content, err = await call_llm_chat_completion(messages, temperature=0.1, max_tokens=500)
    if not content:
        if err:
            cron_logger.log(f"[LLM Extracción] ⚠️ {err}")
        return {}

    # Limpiar posible markdown wrapping
    if content.startswith("```json"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    try:
        entities = json.loads(content)
        if not isinstance(entities, dict):
            cron_logger.log(f"[LLM] ⚠️ Respuesta no es un dict: {content[:100]}")
            return {}

        entities = {k: v for k, v in entities.items() if v is not None and v != ""}
        if entities:
            cron_logger.log(f"[LLM] 🎯 Entidades extraídas: {entities}")
        return entities
    except json.JSONDecodeError as e:
        cron_logger.log(f"[LLM] ⚠️ Error parseando JSON del LLM: {e}")
        return {}
    except Exception as e:
        cron_logger.log(f"[LLM] ❌ Error inesperado en extracción LLM: {e}")
        return {}


def _is_adversarial_or_strange(text: str) -> bool:
    """Detecta patrones de inyección, problemas matemáticos o caracteres extraños para no delatarse."""
    if not text:
        return False
    t = text.lower().strip()
    
    # 1. Problemas matemáticos obvios ("cuanto es 2+2", "50 * 3", "calcula", "solve")
    if re.search(r'\b(cuanto\s+es|calcula|resolv[eé]|calculame)\b\s*\d+', t):
        return True
    if re.search(r'^\s*\d+\s*[\+\-\*\/]\s*\d+\s*=?\s*$', t):
        return True
        
    # 2. Inyecciones de Prompt / Jailbreaks / Pedidos de Código y Tareas
    injection_triggers = [
        "ignore previous", "olvida las instrucciones", "system prompt", "act as",
        "actúa como", "dame tu prompt", "eres un bot", "eres una ia", "quien te programo",
        "eval(", "console.log", "import sys", "print(", "<script", "exec(",
        "escribe un codigo", "escribime un codigo", "genera un codigo", "write code",
        "haceme un script", "hace un script", "haceme un poema", "escribi un poema",
        "haceme la tarea", "resumi este texto", "creame una receta", "escribe una historia"
    ]
    if any(trigger in t for trigger in injection_triggers):
        return True
        
    # 3. Acoso, Degenerados y Comentarios Sexuales Explícitos
    sexual_harassment_triggers = [
        "mandame foto", "manda foto", "tu foto", "pasame tu foto", "estas buena",
        "estas bueno", "linda", "lindo", "mi amor", "bebe", "pajero", "pajera",
        "pack", "desnuda", "desnudo", "cojer", "garchar", "telo", "sexo",
        "videollamada hot", "llamada hot", "hacer el amor", "te pago mas si", "en bolas"
    ]
    if any(trigger in t for trigger in sexual_harassment_triggers):
        return True

    # 4. Caracteres extremadamente extraños / no estándar (excluyendo acentos y emojis comunes)
    non_ascii_or_latin = len(re.findall(r'[\u0400-\u04FF\u4E00-\u9FFF\u0600-\u06FF\u0590-\u05FF\u0370-\u03FF]', t))
    if non_ascii_or_latin > 3:
        return True

    return False


def _generate_contingency_reply(conversation_history: list, target_info: dict) -> str:
    """Genera respuestas inteligentes de contingencia según la hora del sistema y el contexto cuando el LLM no está activo."""
    hour = datetime.now().hour
    if 6 <= hour < 13:
        saludo = "Buenos días"
    elif 13 <= hour < 20:
        saludo = "Buenas tardes"
    else:
        saludo = "Buenas noches"

    last_text = ""
    if conversation_history:
        last_text = (conversation_history[-1].get("text", "") or "").lower().strip()

    if any(k in last_text for k in ["alias", "cbu", "cvu", "mercadopago", "cuenta", "banco", "transfer"]):
        return "¡Buenísimo! ¿A nombre de quién está la cuenta o alias para verificar la transferencia?"
    elif any(k in last_text for k in ["precio", "sale", "cuesta", "cuanto", "total", "$", "pesos", "dolar"]):
        return "Dale impecable, me sirve el precio. ¿Qué Alias o CVU de MercadoPago me pasás para hacerte el pago?"
    elif any(k in last_text for k in ["zona", "donde", "local", "showroom", "retirar", "envio", "envíos", "moto"]):
        return "¿Por qué zona están para pasar a retirar en persona o cómo hacen con los envíos?"
    elif any(k in last_text for k in ["talle", "stock", "color", "modelo", "disponible", "quedan"]):
        return "¿Te queda stock disponible? ¿Cómo hacemos para coordinar el pago y la entrega?"
    elif len(conversation_history) <= 1:
        return f"¡Hola! {saludo}, vi tu publicación. ¿Sigue disponible? ¿Cuánto sale y cómo hacemos para coordinar?"
    else:
        return "Dale joya, ¿cómo hacemos para coordinar el pago y retiro?"


SELLER_SIMULATION_SYSTEM_PROMPT = """Eres un vendedor informal argentino que comercializa calzado, zapatillas, indumentaria y réplicas de marcas reconocidas por WhatsApp, Marketplace e Instagram.

Estás hablando con un cliente interesado en comprar tus productos:

🎯 TUS OBJETIVOS COMO VENDEDOR SIMULADO:
1. Actúa como un vendedor real y amigable con lenguaje coloquial argentino ("Hola genio/a!", "Sí rey/reina, nos queda stock en talle 40 y 41", "Te sale $65.000 de promo").
2. Si te preguntan el PRECIO: Da un precio entre $45.000 y $85.000 ARS y ofrece descuento por transferencia.
3. Si te preguntan MEDIO DE PAGO / CÓMO PAGAR: Pasa de inmediato datos de cobro realistas para que el peritaje OSINT los detecte:
   - Alias: "calzados.directo.mp" o "zapas.outlet.arg"
   - CBU/CVU: "0000003100012345678901"
   - Titular: "Juan Carlos Pérez"
   - CUIT/CUIL: "20-38123456-8"
4. Si te preguntan DÓNDE ESTÁN O RETIRO: Di que tienen showroom/depósito en la zona comercial de Flores (cerca de Nazca y Av. Avellaneda) o en Once, o que hacen envíos por motomensajería a todo el país.
5. Mantén respuestas ágiles de 1 a 2 oraciones. NUNCA digas que eres una IA o simulación."""


async def generate_honeypot_response(conversation_history: list, target_info: dict) -> tuple[str, str | None]:
    """
    Genera una respuesta honeypot contextual (rol Comprador/Analista) usando DeepSeek/LLM.
    Returns:
        tuple (reply_text: str, error_detail: str | None)
    """
    if conversation_history:
        last_msg = conversation_history[-1].get("text", "")
        if _is_adversarial_or_strange(last_msg):
            cron_logger.log(f"[Honeypot LLM] 🛡️ Mensaje adversarial/tarea/acoso detectado ('{last_msg[:40]}'). El bot se queda en silencio.")
            return "", None

    from services.bot_persona_service import get_bot_persona_config
    persona_cfg = get_bot_persona_config()
    custom_prompt = (persona_cfg.get("system_prompt") or "").strip()

    marca_info = target_info.get('marca') or 'el producto publicado'
    if custom_prompt:
        system_prompt = f"{custom_prompt}\n\n[CONTEXTO ACTUAL DE LA CONVERSACIÓN]: Estás negociando por: {marca_info}."
    else:
        system_prompt = f"""Eres un comprador interesado en adquirir {marca_info}. Estás chateando por WhatsApp con el vendedor de forma casual y directa.
Respuestas CORTAS de 1 o 2 oraciones como máximo. Pide con naturalidad el Alias o CBU/CVU para transferir, y pregunta de qué zona son para retirar."""

    messages = [{"role": "system", "content": system_prompt}]
    for msg in conversation_history[-10:]:  # Últimos 10 mensajes para contexto
        txt = (msg.get("text") or "").strip()
        if not txt:
            continue
        role = "assistant" if msg.get("sender") == "bot" else "user"
        messages.append({"role": role, "content": txt})

    if len(messages) == 1 or messages[-1]["role"] != "user":
        last_txt = conversation_history[-1].get("text", "").strip() if conversation_history else "Hola"
        messages.append({"role": "user", "content": last_txt or "Hola"})

    reply, err = await call_llm_chat_completion(messages, temperature=0.7, max_tokens=150)
    if err:
        cron_logger.log(f"[Honeypot LLM] ❌ Error en LLM ({err}). Usando contingencia contextual.")
        return _generate_contingency_reply(conversation_history, target_info), err

    # Sanitizar: quitar comillas envolventes si las tiene
    if reply.startswith('"') and reply.endswith('"'):
        reply = reply[1:-1]

    # Si el modelo determinó SILENCIO o el vendedor fue hostil/extraño, no enviar nada
    if reply.upper().strip() in ("SILENCIO", "SILENCIO.", "[SILENCIO]"):
        cron_logger.log(f"[Honeypot LLM] 🤫 Comportamiento no comercial detectado. El bot permanece en silencio.")
        return "", None

    cron_logger.log(f"[Honeypot LLM] 🤖 Respuesta generada: {reply[:80]}...")
    return reply, None


async def generate_seller_simulation_response(conversation_history: list, target_info: dict) -> tuple[str, str | None]:
    """
    Genera la respuesta del VENDEDOR SIMULADO (infractor) usando DeepSeek.
    El bot asume el papel de vendedor informal ofreciendo réplicas y pasando datos bancarios.
    Returns:
        tuple (reply_text: str, error_detail: str | None)
    """
    messages = [{"role": "system", "content": SELLER_SIMULATION_SYSTEM_PROMPT}]
    for msg in conversation_history[-10:]:
        txt = (msg.get("text") or "").strip()
        if not txt:
            continue
        role = "assistant" if msg.get("sender") in ("infractor", "seller") else "user"
        messages.append({"role": role, "content": txt})

    if len(messages) == 1 or messages[-1]["role"] != "user":
        last_txt = conversation_history[-1].get("text", "").strip() if conversation_history else "¿Cuánto sale?"
        messages.append({"role": "user", "content": last_txt or "¿Cuánto sale?"})

    reply, err = await call_llm_chat_completion(messages, temperature=0.8, max_tokens=200)
    if err:
        cron_logger.log(f"[Vendedor Simulacro DeepSeek] ❌ Error en API DeepSeek: {err}")
        fallback = "¡Hola! Sí, nos quedan los últimos pares en promo a $65.000. Te paso el alias calzados.directo.mp si querés asegurar el tuyo."
        return fallback, f"Error DeepSeek: {err}"

    if reply.startswith('"') and reply.endswith('"'):
        reply = reply[1:-1]

    cron_logger.log(f"[Vendedor Simulacro DeepSeek] 🎭 Respuesta generada: {reply[:80]}...")
    return reply, None


# ─── Evaluación OSINT y Brand Protection de Publicaciones ───────────────────

def _evaluate_publication_heuristics(
    plataforma: str,
    descripcion: str,
    comentarios: str,
    ubicacion: str,
    precio: str
) -> dict:
    """
    Evaluación heurística determinística aplicando estrictamente las mismas reglas
    cuando el LLM no está disponible o falla el parseo JSON.
    """
    texto_combinado = f"{descripcion} {comentarios} {precio}".lower()
    geo_combinado = f"{ubicacion} {texto_combinado} {precio}".lower()

    # 1. Reglas Falsificación
    # NO ES FAKE (Rechazar)
    re_no_fake = re.compile(
        r"\b(?:100%\s*original|usad[oa]s?|pre-loved|segunda\s+mano|vendo\s+mis\s+zapatillas|"
        r"tienda\s+oficial|distribuidor\s+autorizado|aut[eé]ntic[oa]s?)\b",
        re.IGNORECASE
    )
    # ES FAKE
    re_fake = re.compile(
        r"\b(?:r[eé]plicas?|g5|aaa|triple\s*a|1[.:/]1|1\.1|importadas?|espejo|clon(?:es)?|mirror|super\s*fake)\b",
        re.IGNORECASE
    )

    if re_no_fake.search(texto_combinado):
        es_fake = False
        motivo_fake = "Rechazado: Menciona producto original, usado o canal oficial autorizado."
    elif re_fake.search(texto_combinado):
        es_fake = True
        motivo_fake = "Detectado término explícito de réplica o falsificación."
    else:
        es_fake = False
        motivo_fake = "Rechazado: No presenta indicadores claros de réplica o falsificación."

    # 2. Reglas Geografía e Idioma
    tiene_caracteres_no_latinos = bool(re.search(r'[\u0600-\u06FF\u0400-\u04FF\u4E00-\u9FFF]', geo_combinado))
    re_idioma_extranjero = re.compile(
        r"\b(?:shipping|free\s*shipping|worldwide|tamanho|frete|cart[aã]o|promo[cç][aã]o|pre[cç]o|"
        r"order\s*now|wholesale|authentic\s*shoes|worldwide\s*shipping|international\s*shipping|"
        r"shoes|buy\s*now|available\s*now|size|sale)\b",
        re.IGNORECASE
    )
    re_paises_homonimos = re.compile(
        r"\b(?:nuevo\s*m[eé]xico|new\s*mexico|santa\s*fe,?\s*(?:nm|new\s*mexico)|bogot[aá]|colombia|m[eé]xico|"
        r"chile|per[uú]|españa|spain|estados\s*unidos|united\s*states|usa|eeuu|brasil|brazil|uruguay|paraguay)\b",
        re.IGNORECASE
    )

    re_argentina = re.compile(
        r"\b(?:caba|rosario|c[oó]rdoba|mendoza|tucum[aá]n|buenos\s*aires|la\s*plata|santa\s*fe|"
        r"mar\s*del\s*plata|salta|neuqu[eé]n|chaco|corrientes|entre\s*r[ií]os|misiones|"
        r"catamarca|chubut|formosa|jujuy|la\s*pampa|la\s*rioja|san\s*juan|san\s*luis|"
        r"santa\s*cruz|santiago\s*del\s*estero|tierra\s*del\s*fuego|"
        r"ars|pesos?|lucas?|talles?|che|andreani|correo\s*argentino|mercadopago|cbu|cvu)\b",
        re.IGNORECASE
    )

    if tiene_caracteres_no_latinos:
        es_arg = False
        motivo_geo = "Rechazado: Contenido en idioma extranjero no latino (árabe, ruso, etc.)."
    elif re_idioma_extranjero.search(geo_combinado):
        es_arg = False
        motivo_geo = "Rechazado: Idioma extranjero o envíos internacionales genéricos detectados."
    elif re_paises_homonimos.search(geo_combinado):
        es_arg = False
        motivo_geo = "Rechazado: Menciona países extranjeros o ciudades homónimas no orientadas a Argentina."
    elif re_argentina.search(geo_combinado) or "argentina" in geo_combinado or "+54" in geo_combinado:
        es_arg = True
        motivo_geo = "Orientado a Argentina por ubicación, moneda o jerga/logística local."
    else:
        es_arg = False
        motivo_geo = "Rechazado: Sin indicadores suficientes de ubicación o logística argentina."

    # Resumen de motivo de 1 línea
    if es_fake and es_arg:
        motivo = "Aprobado: Producto réplica/falsificación orientado al mercado argentino."
    elif not es_fake and not es_arg:
        motivo = f"{motivo_fake} {motivo_geo}"
    elif not es_fake:
        motivo = motivo_fake
    else:
        motivo = motivo_geo

    return {
        "es_falsificacion": es_fake,
        "es_argentina": es_arg,
        "motivo": motivo
    }


async def analyze_publication_brand_protection(
    plataforma: str = "",
    descripcion: str = "",
    comentarios: str | list = "",
    ubicacion: str = "",
    precio: str | float = ""
) -> dict:
    """
    Analiza datos extraídos de una publicación de redes sociales y determina estrictamente:
    1. Si es FALSIFICACIÓN/RÉPLICA (descartando originales nuevos o usados).
    2. Si está orientada a ARGENTINA.
    
    Retorna estrictamente:
    {
      "es_falsificacion": bool,
      "es_argentina": bool,
      "motivo": str
    }
    """
    if isinstance(comentarios, (list, tuple)):
        comentarios_str = " | ".join(str(c) for c in comentarios if c)
    else:
        comentarios_str = str(comentarios or "")

    user_content = BRAND_PROTECTION_USER_TEMPLATE.format(
        plataforma=plataforma or "No informada",
        descripcion=descripcion or "Sin descripción",
        comentarios=comentarios_str or "Sin comentarios",
        ubicacion=ubicacion or "No informada",
        precio=str(precio) if precio not in (None, "") else "No detectado"
    )

    messages = [
        {"role": "system", "content": BRAND_PROTECTION_OSINT_SYSTEM_PROMPT},
        {"role": "user", "content": user_content}
    ]

    content, err = await call_llm_chat_completion(messages, temperature=0.1, max_tokens=250)
    if content:
        clean = content.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        if clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        clean = clean.strip()

        try:
            parsed = json.loads(clean)
            if isinstance(parsed, dict) and "es_falsificacion" in parsed and "es_argentina" in parsed:
                result = {
                    "es_falsificacion": bool(parsed.get("es_falsificacion")),
                    "es_argentina": bool(parsed.get("es_argentina")),
                    "motivo": str(parsed.get("motivo", "")).strip()
                }
                cron_logger.log(f"[BrandProtection OSINT] 🎯 Análisis completado por LLM: {result}")
                return result
        except Exception as e:
            cron_logger.log(f"[BrandProtection OSINT] ⚠️ Error parseando JSON de LLM: {e} | Raw: {clean[:100]}")

    # Fallback heurístico si no hay API key o falló la respuesta
    cron_logger.log("[BrandProtection OSINT] ℹ️ Ejecutando evaluación heurística de respaldo.")
    return _evaluate_publication_heuristics(
        plataforma=plataforma,
        descripcion=descripcion,
        comentarios=comentarios_str,
        ubicacion=ubicacion,
        precio=str(precio or "")
    )
