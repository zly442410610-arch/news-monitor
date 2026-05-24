"""
Configuration for the news monitor.
Theme-specific settings are delegated to theme.py; shared settings remain here.
"""
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(override=True)

from theme import get_theme

_t = get_theme()

BASE_DIR = Path(__file__).parent
VERSION = "0.11.0"

CHANGELOG = [
    ("0.11.0", "2026-05-24",
     "• 修复 Google Patents 乱码（UTF-8 编码检测，22 篇已采集文章批量回写修复）\n"
     "• 新增专利文本清洗函数 — 自动去除分类号、引用文献、法律状态等排版噪声\n"
     "• 优化文章详情排版（字号/行距/对比度提升）\n"
     "• 有翻译时隐藏英文原文，仅显示中文\n"),
    ("0.10.0", "2026-05-22",
     "• 新增关键词：凝胶推进剂、电控推进剂、相变推进剂、斜爆震\n"
     "• 接入 Zhipu AI glm-4-flash 为主力翻译/过滤引擎\n"
     "• 新增 kuaipao.ai gpt-5.4-mini 作为 LLM 备用通道\n"
     "• 新增 LLM 速率限制（并发数/RPM 可配置）\n"
     "• 新增 token 用量追踪（每次采集后报告）\n"
     "• 专利采集全程走 LLM 过滤，消除误报\n"
     "• 全文 LLM 扫描，清除 53 篇不相关文章\n"
     "• 清理遗留 NVIDIA/Anthropic 引用及死代码\n"
     "• 排除 iRNA/RNAi 等生物医药专利误报\n"
     "• 放宽 AAM LLM 过滤阈值，减少漏报"),
    ("0.9.2", "2026-05-21",
     "• 修复更新历史页面崩溃问题\n"
     "• 完善系统检查与稳定性优化"),
    ("0.9.1", "2026-05-21",
     "• 全面重构导航布局，搜索框独立一行，移除导出功能\n"
     "• 恢复翻译功能，接入 DeepSeek API\n"
     "• 修复跨来源文章去重逻辑\n"
     "• 新增作者单位自动回填\n"
     "• 修复日期格式一致性\n"
     "• 新增搜索框支持全文检索\n"
     "• 移除无法访问的 Google News 链接"),
    ("0.9.0", "2026-05-18",
     "• 接入多个学术数据源（CNKI、arXiv、Springer 等）\n"
     "• 新增论文/新闻/专利分类标签\n"
     "• 新增事件分组功能\n"
     "• 新增月度报告\n"
     "• 优化移动端显示"),
    ("0.8.0", "2026-05-10",
     "• 接入 RSSHub 国内新闻源\n"
     "• 新增 Telegram 消息推送\n"
     "• 新增采集历史页面\n"
     "• 优化关键词匹配算法"),
    ("0.7.0", "2026-05-01",
     "• 引入 LLM 翻译引擎\n"
     "• 新增文章全文翻译\n"
     "• 新增 LLM 智能过滤\n"
     "• 优化文章相关性评分"),
    ("0.6.0", "2026-04-20",
     "• 支持多主题面板（固体动力/空空导弹）\n"
     "• 搭建双面板独立数据存储\n"
     "• 新增角标快速切换主题"),
    ("0.5.0", "2026-04-10",
     "• 初始版本上线\n"
     "• 支持 RSS 新闻采集\n"
     "• 基础中文翻译\n"
     "• 简单 Web 面板"),
]

# ── Theme-specific (delegated) ──────────────────────────────────────────

KEYWORDS = _t.keywords
ALL_KEYWORDS = sorted(set(kw for group in KEYWORDS.values() for kw in group))
EXCLUDE_PATTERNS = _t.exclude_patterns
RSS_SOURCES = _t.rss_sources

TRANSLATION_PROMPT = _t.translation_prompt
LLM_FILTER_PROMPT = _t.llm_filter_prompt
USE_LLM_FILTER = os.environ.get("USE_LLM_FILTER", "true").lower() == "true"

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
POLL_INTERVAL_MINUTES = int(os.environ.get("POLL_INTERVAL_MINUTES", "120"))
TRANSLATE_TO_CHINESE = os.environ.get("TRANSLATE_TO_CHINESE", "true").lower() == "true"

LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "glm-4-flash")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/")
LLM_FALLBACK_MODEL = os.environ.get("LLM_FALLBACK_MODEL", "")
LLM_FALLBACK_BASE_URL = os.environ.get("LLM_FALLBACK_BASE_URL", "")
LLM_FALLBACK_API_KEY = os.environ.get("LLM_FALLBACK_API_KEY", "")
LLM_CONCURRENCY = int(os.environ.get("LLM_CONCURRENCY", "2"))
LLM_RPM = int(os.environ.get("LLM_RPM", "60"))

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
COLLECT_START_DATE = os.environ.get("COLLECT_START_DATE", "2026-04-01")
