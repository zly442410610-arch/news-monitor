"""Unified dashboard package for aerospace news monitoring."""
import logging
import http.server
import signal
import threading
from socketserver import ThreadingMixIn

from .handler import DashboardHandler
from .state import BASE_DIR, log
import config


class ThreadPoolHTTPServer(ThreadingMixIn, http.server.HTTPServer):
    """HTTPServer with a bounded thread pool to prevent resource exhaustion."""
    allow_reuse_address = True
    daemon_threads = True
    max_workers = 16

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._active_requests = threading.BoundedSemaphore(self.max_workers)

    def process_request(self, request, client_address):
        with self._active_requests:
            super().process_request(request, client_address)


def run():
    port = config.DASHBOARD_PORT
    server = ThreadPoolHTTPServer(("0.0.0.0", port), DashboardHandler)

    # Graceful shutdown on SIGTERM/SIGINT
    shutdown_event = threading.Event()
    def _shutdown(signum, frame):
        log.info(f"Received signal {signum}, shutting down...")
        shutdown_event.set()
        server.shutdown()
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    log.info(f"统一监测 Dashboard 运行在 http://0.0.0.0:{port}")
    log.info("  航天动力: / (default)")
    log.info("  空空导弹: /aam")
    try:
        server.serve_forever()
    except (KeyboardInterrupt, OSError):
        pass
    finally:
        server.server_close()
        log.info("Dashboard stopped")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    run()
