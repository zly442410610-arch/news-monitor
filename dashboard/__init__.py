"""Unified dashboard package for aerospace news monitoring."""
import logging
import http.server
import signal
import threading

from .handler import DashboardHandler
from .state import BASE_DIR, log
import config


class ThreadPoolHTTPServer(http.server.ThreadingHTTPServer):
    """Multi-threaded HTTPServer — one slow request won't block others."""
    allow_reuse_address = True


def run():
    port = config.DASHBOARD_PORT
    server = ThreadPoolHTTPServer(("0.0.0.0", port), DashboardHandler)

    # Graceful shutdown via a background thread (avoids signal handler deadlock)
    shutdown_event = threading.Event()

    def _shutdown(signum, frame):
        log.info(f"Received signal {signum}, shutting down...")
        shutdown_event.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    def _wait_shutdown():
        shutdown_event.wait()
        server.shutdown()

    threading.Thread(target=_wait_shutdown, daemon=True).start()

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
