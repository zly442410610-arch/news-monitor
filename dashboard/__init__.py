"""Unified dashboard package for aerospace news monitoring."""
import logging
import http.server
import signal
import socket
import threading
import urllib.request

from .handler import DashboardHandler
from .state import BASE_DIR, log
import config


class ThreadPoolHTTPServer(http.server.ThreadingHTTPServer):
    """Multi-threaded HTTPServer — one slow request won't block others."""
    allow_reuse_address = True
    request_queue_size = 128  # default is 5, too small under burst

    def server_bind(self):
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return super().server_bind()


def _prewarm_monthly_reports(port: int):
    """Pre-generate monthly reports in parallel so users don't wait for LLM on first visit."""
    import time
    from .state import THEMES
    from .handler import init_db_for_theme
    from monitor import get_available_months
    import config

    if not config.LLM_API_KEY:
        return  # skip prewarm if LLM is not configured

    time.sleep(2)  # give server a moment

    def _warm_one(theme_name: str):
        try:
            conn = init_db_for_theme(theme_name)
            months = get_available_months(conn)
            conn.close()
            if not months:
                return
            month = months[0]
            prefix = {"news": "", "aam": "/aam", "dw": "/dw"}.get(theme_name, "")
            url = f"http://localhost:{port}{prefix}/monthly-report?month={month}"
            log.info(f"预生成月报: {theme_name} {month}")
            resp = urllib.request.urlopen(url, timeout=60)
            resp.read()
            log.info(f"月报预生成完成: {theme_name} {month} ({resp.status})")
        except Exception as e:
            log.warning(f"月报预生成失败 {theme_name}: {e}")

    threads = [threading.Thread(target=_warm_one, args=(t,), daemon=True)
               for t in THEMES]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)


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
    log.info("  防务观察: /dw")

    # Pre-generate monthly reports in background (disabled — self-request LLM deadlock risk)
    # threading.Thread(target=_prewarm_monthly_reports, args=(port,), daemon=True).start()
    log.info("月报预生成已跳过（按需生成）")

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
