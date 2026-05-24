"""Unified dashboard package for aerospace news monitoring."""
import logging
import http.server
import signal
import threading
import urllib.request

from .handler import DashboardHandler
from .state import BASE_DIR, log
import config


class ThreadPoolHTTPServer(http.server.ThreadingHTTPServer):
    """Multi-threaded HTTPServer — one slow request won't block others."""
    allow_reuse_address = True


def _prewarm_monthly_reports(port: int):
    """Pre-generate monthly reports so users don't wait for LLM on first visit."""
    import time
    from .state import THEMES
    from .handler import init_db_for_theme
    from monitor import get_available_months

    time.sleep(2)  # give server a moment
    for theme_name in THEMES:
        try:
            conn = init_db_for_theme(theme_name)
            months = get_available_months(conn)
            conn.close()
            if not months:
                continue
            month = months[0]
            prefix = "/aam" if theme_name == "aam" else ""
            url = f"http://localhost:{port}{prefix}/monthly-report?month={month}"
            log.info(f"预生成月报: {theme_name} {month}")
            resp = urllib.request.urlopen(url, timeout=300)
            resp.read()  # wait for completion
            log.info(f"月报预生成完成: {theme_name} {month} ({resp.status})")
        except Exception as e:
            log.warning(f"月报预生成失败 {theme_name}: {e}")


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

    # Pre-generate monthly reports in background
    threading.Thread(target=_prewarm_monthly_reports, args=(port,), daemon=True).start()

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
