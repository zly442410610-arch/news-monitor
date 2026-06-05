"""Shared state for the unified dashboard."""
import logging
from pathlib import Path

from theme import NEWS, AAM, DW

THEMES = {"news": NEWS, "aam": AAM, "dw": DW}

log = logging.getLogger("monitor.dashboard")

BASE_DIR = Path(__file__).resolve().parent.parent
