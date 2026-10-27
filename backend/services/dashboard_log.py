"""Salida compartida del dashboard para terminal y consola visual del cron."""

from services.cron_logger import cron_logger


def dashboard_log(message: str, *args) -> None:
    text = message % args if args else message
    cron_logger.log(text)
