# telemetry.py - System telemetry collection
import logging
import threading
import psutil
import state
from config import settings

logger = logging.getLogger(__name__)


class TelemetryManager:
    def __init__(self):
        self._observers = []
        self._stop_event = threading.Event()
        self._thread = None

        # Prime CPU measurement (first call always returns 0)
        try:
            psutil.cpu_percent(interval=None)
        except Exception:
            pass

    def subscribe(self, callback):
        self._observers.append(callback)

    def notify(self):
        for callback in self._observers:
            try:
                callback()
            except Exception as e:
                logger.error(f"[Telemetry] Observer callback failed: {e}")

    def update_metrics(self):
        """Collect system metrics. Handles errors gracefully."""
        try:
            cpu = psutil.cpu_percent(interval=None)
            memory = psutil.virtual_memory().percent
            storage = psutil.disk_usage("/").percent
            state.update_telemetry(cpu, memory, storage)
            self.notify()
        except Exception as e:
            logger.error(f"[Telemetry] Failed to collect metrics: {e}")

    def start(self):
        """Start background telemetry collection."""
        if self._thread is not None:
            logger.warning("[Telemetry] Already running")
            return

        interval = settings.telemetry_interval

        def loop():
            logger.info(f"[Telemetry] Started (interval={interval}s)")
            while not self._stop_event.is_set():
                self.update_metrics()
                self._stop_event.wait(interval)
            logger.info("[Telemetry] Stopped")

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop telemetry collection gracefully."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
