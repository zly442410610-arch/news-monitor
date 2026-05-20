"""Unified dashboard package for aerospace news monitoring."""
import logging
import http.server

from .handler import DashboardHandler
from .state import BASE_DIR, log


def run():
    server = http.server.HTTPServer(("0.0.0.0", 8080), DashboardHandler)
    log.info("统一监测 Dashboard 运行在 http://0.0.0.0:8080")
    log.info("  航天动力: / (default)")
    log.info("  空空导弹: /aam")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Dashboard stopped")
        server.server_close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    run()
