import collections
import threading
from datetime import datetime
import pytz

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
                print(log_entry)
            except UnicodeEncodeError:
                print(log_entry.encode('cp1252', errors='replace').decode('cp1252'))

    def get_logs(self, last_n: int = 50) -> list[str]:
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

cron_logger = CronLogger()
