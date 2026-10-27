"""Extracción de contactos publicados; nunca completa números parciales."""

import re
from urllib.parse import unquote

from services.dashboard_scope import COUNTRIES

BR_DDD = set("11 12 13 14 15 16 17 18 19 21 22 24 27 28 31 32 33 34 35 37 38 41 42 43 44 45 46 47 48 49 51 53 54 55 61 62 63 64 65 66 67 68 69 71 73 74 75 77 79 81 82 83 84 85 86 87 88 89 91 92 93 94 95 96 97 98 99".split())


def normalize_phone(value: str, country: str, mobile_hint: bool = False) -> str | None:
    raw = unquote(str(value)).strip()
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("00"):
        digits = digits[2:]
        raw = "+" + digits
    dial = COUNTRIES[country]["dial"]
    international = raw.startswith("+") or (digits.startswith(dial) and len(digits) >= 12)
    if international:
        if not digits.startswith(dial):
            return None
        digits = digits[len(dial):]
    if country == "Argentina":
        mobile = international and digits.startswith("9") and len(digits) == 11
        if mobile:
            digits = digits[1:]
        if digits.startswith("0"):
            digits = digits[1:]
        # Formato nacional: 0 + área (2 a 4) + 15 + abonado.
        if len(digits) == 12:
            match = re.fullmatch(r"([1-3]\d{1,3})15(\d{6,8})", digits)
            if not match or len(match[1] + match[2]) != 10:
                return None
            digits, mobile = match[1] + match[2], True
        # En publicaciones argentinas suele omitirse +54 9 e incluso el 15.
        # Si ya hay diez dígitos válidos, se guarda en el único formato móvil
        # internacional que usa el dashboard.
        if not international and len(digits) == 10:
            mobile = True
        if not re.fullmatch(r"[1-3]\d{9}", digits):
            return None
        if not mobile:
            return None
        return "+549" + digits
    if country == "Brasil":
        if digits.startswith("0") and len(digits) in (11, 12):
            digits = digits[1:]
        if digits[:2] not in BR_DDD:
            return None
        if not re.fullmatch(r"\d{2}9\d{8}", digits):
            return None
    if country == "México":
        if international and len(digits) == 11 and digits.startswith("1"):
            digits = digits[1:]
        if not international:
            for prefix in ("044", "045", "01"):
                if digits.startswith(prefix) and len(digits) == 10 + len(prefix):
                    digits = digits[len(prefix):]
                    break
        if not re.fullmatch(r"[2-9]\d{9}", digits):
            return None
    return "+" + dial + digits


def extract_phone(text: str, country: str) -> str | None:
    text = unquote(text or "")
    # Enlaces explícitos tienen prioridad y admiten dígitos sin separadores.
    explicit = re.findall(r"(?:tel:|wa\.me/|api\.whatsapp\.com/send\?phone=|whatsapp:\S*?phone=)(\+?[\d(). -]{8,24})", text, re.I)
    for value in explicit:
        phone = normalize_phone(value.rstrip(" .-"), country, mobile_hint=True)
        if phone:
            return phone
    for match in re.finditer(r"(?<![\w/])(?:\+|00)?\d(?:[\d(). -]{6,23}\d)(?!\d)", text):
        value = match[0]
        context = text[max(0, match.start() - 45):match.start()].casefold()
        # No interpretar IDs de publicaciones, precios o documentos como teléfonos.
        labelled = bool(re.search(r"whats(?:app)?|tel[eé]fono|telefone|\bcel(?:ular)?\.?|contacto|contato|\btel\b|phone", context))
        international = value.startswith(("+", "00"))
        if not labelled and not international:
            continue
        mobile_hint = bool(re.search(r"whats(?:app)?|cel(?:ular)?\.?", context))
        phone = normalize_phone(value, country, mobile_hint=mobile_hint)
        if phone:
            return phone
    return None
