import collections
import threading
from datetime import datetime
import pytz
from pathlib import Path

LOG_FILE = Path(__file__).resolve().parent.parent / "cron_execution.log"

class CronLogger:
    def __init__(self):
        self.logs = collections.deque(maxlen=500)
        self.lock = threading.Lock()
        self.progress = {}
        self.tz = pytz.timezone('America/Argentina/Buenos_Aires')

    def log(self, message: str):
        with self.lock:
            now = datetime.now(self.tz).strftime('%H:%M:%S')
            log_entry = f"[{now}] {message}"
            self.logs.append(log_entry)
            try:
                print(log_entry, flush=True)
            except Exception:
                try:
                    print(log_entry.encode('ascii', 'replace').decode('ascii'), flush=True)
                except Exception:
                    pass
            try:
                with open(LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(log_entry + "\n")
            except Exception:
                pass

    def get_logs(self, last_n: int = 60) -> list[str]:
        # Leer desde archivo compartido para sincronizar todos los workers de Uvicorn
        try:
            if LOG_FILE.exists():
                with open(LOG_FILE, "r", encoding="utf-8") as f:
                    lines = [line.strip() for line in f if line.strip()]
                    if lines:
                        return lines[-last_n:]
        except Exception:
            pass
        with self.lock:
            return list(self.logs)[-last_n:]

    def get_progress(self) -> dict:
        with self.lock:
            return dict(self.progress)

    def set_status(self, status: str):
        with self.lock:
            self.progress["status"] = status

    def get_status(self) -> dict:
        with self.lock:
            return {"status": self.progress.get("status", "idle")}

    def set_progress(self, **kwargs):
        with self.lock:
            self.progress.update(kwargs)

    def reset(self):
        with self.lock:
            self.logs.clear()
            self.progress.clear()
            try:
                if LOG_FILE.exists():
                    LOG_FILE.write_text("", encoding="utf-8")
            except Exception:
                pass

cron_logger = CronLogger()
