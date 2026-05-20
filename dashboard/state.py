"""Shared state for the unified dashboard."""
import logging
import threading
from pathlib import Path

from theme import NEWS, AAM

THEMES = {"news": NEWS, "aam": AAM}

# Track background poll status per theme
_poll_status: dict[str, dict] = {}
_poll_lock = threading.Lock()

log = logging.getLogger("monitor.dashboard")

BASE_DIR = Path(__file__).resolve().parent.parent
