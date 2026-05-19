"""
Configuration for the news monitor.
Theme-specific settings are delegated to theme.py; shared settings remain here.
"""
import os
from pathlib import Path

from theme import get_theme

_t = get_theme()

BASE_DIR = Path(__file__).parent

# ── Theme-specific (delegated) ──────────────────────────────────────────

KEYWORDS = _t.keywords
ALL_KEYWORDS = sorted(set(kw for group in KEYWORDS.values() for kw in group))
EXCLUDE_PATTERNS = _t.exclude_patterns
RSS_SOURCES = _t.rss_sources

TRANSLATION_PROMPT = _t.translation_prompt
LLM_FILTER_PROMPT = _t.llm_filter_prompt
USE_LLM_FILTER = True

BRIEFING_SUBJECT = _t.briefing_subject
BRIEFING_PROMPT = _t.briefing_prompt

DASHBOARD_PORT = int(os.environ.get("DASHBOARD_PORT", str(_t.dashboard_port)))
DASHBOARD_HOST = "0.0.0.0"

HAS_EVENT_GROUPING = _t.has_event_grouping
LOGGER_NAME = _t.logger_name
APP_NAME = _t.app_name
APP_NAME_CN = _t.app_name_cn
APP_SUBTITLE = _t.app_subtitle
DASHBOARD_TITLE = _t.dashboard_title
DASHBOARD_OTHER_THEME_NAME = _t.dashboard_other_theme_name
DASHBOARD_OTHER_THEME_URL = _t.dashboard_other_theme_url
DASHBOARD_OTHER_THEME_COLOR = _t.dashboard_other_theme_color
DASHBOARD_OTHER_THEME_COLOR_RGB = _t.dashboard_other_theme_color_rgb
STATS_TITLE = _t.stats_title
FALLBACK_BRIEFING_TITLE = _t.fallback_briefing_title

# Notifications
TELEGRAM_MSG_CJK = _t.telegram_msg_cjk
TELEGRAM_MSG_EN = _t.telegram_msg_en
EMAIL_HTML_PREFIX = _t.email_html_prefix
EMAIL_SUBJECT_PREFIX = _t.email_subject_prefix
NOTIFICATION_PREFIX = _t.notification_prefix

# Dashboard colors
COLOR_PRIMARY = _t.dashboard_color_primary
COLOR_PRIMARY_RGB = _t.dashboard_color_primary_rgb
HEADER_BG = _t.dashboard_header_bg
HEADER_BORDER = _t.dashboard_header_border
HEADER_BG_LIGHT = _t.dashboard_header_bg_light
EVENT_HEADER_BG = _t.dashboard_event_header_bg
EVENT_BORDER = _t.dashboard_event_border
SOURCE_TAG_DOMESTIC_BG = _t.dashboard_source_tag_domestic_bg
SOURCE_TAG_DOMESTIC_COLOR = _t.dashboard_source_tag_domestic_color

# ── Theme-scoped storage paths ──────────────────────────────────────────

DB_PATH = BASE_DIR / "data" / f"{_t.db_name}.db"
ARCHIVE_DIR = BASE_DIR / "snapshots" / _t.name
BRIEFING_DIR = BASE_DIR / "briefings" / _t.name

# ── Shared (unchanged across themes) ────────────────────────────────────

MIN_RELEVANCE_SCORE = 30
POLL_INTERVAL_MINUTES = 1440
TRANSLATE_TO_CHINESE = True

LLM_API_KEY = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("LLM_API_KEY", "")
LLM_MODEL = "claude-sonnet-4-6"

# Notification channels
TELEGRAM_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TG_CHAT_ID", "")
SMTP_SERVER = os.environ.get("SMTP_SERVER", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "")
EMAIL_TO = os.environ.get("EMAIL_TO", "")

# Collector API (for domestic news collector node)
COLLECTOR_API_KEY = os.environ.get("COLLECTOR_API_KEY", "")

# Cutoff date: only collect articles published on or after this date
COLLECT_START_DATE = "2026-04-01"
