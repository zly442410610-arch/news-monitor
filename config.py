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
THEME_NAME = _t.name
VERSION = "0.21.0"

CHANGELOG = [
    ("0.21.0", "2026-05-26",
     "• 术语库大幅扩充：参照 GB/T 14410、GJB 高超声速术语标准等，新增高超声速气动热力学、真实气体效应、热防护系统、风洞试验设备等领域术语约 1000 条\n"
     "• 固体超燃冲压发动机专题：新增 SFSJ/SRSJ/SDRS 等构型术语，涵盖燃面退移、硼燃烧、气固两相流等约 160 条\n"
     "• 相变冲压发动机专题：新增相变燃料/微波驱动相变/熔融喷射等约 90 条\n"
     "• 旋转爆震冲压发动机专题：新增喷注器/爆震波动力学/隔离段/起爆系统等约 200 条\n"
     "• 固体火箭冲压发动机部件补充：新增喉栓/转级/燃气发生器/补燃室等约 130 条\n"
     "• AAM 术语补充：新增雷达 ECM/有源相控阵/氮化镓收发模块等约 200 条\n"
     "• 关键词同步扩充至 594 个，覆盖新型推进技术领域\n"),
    ("0.19.0", "2026-05-25",
     "• 修复术语库回填导致括号内缩写被误翻的问题\n"
     "• 修复最近 24h 统计按钮 ISO 8601 T 分隔符导致的计数错误\n"
     "• 修复月度报告参考文献超链接点击区域过小的问题\n"
     "• 修复文章正文化学式换行异常、专利段落合并过度的问题\n"
     "• 文章详情页支持展示全文抓取时的配图\n"
     "• 回填 9 篇漏翻译文章正文（含俄文专利）\n"
     "• 超链接颜色优化：橙色调 #fb923c，醒目且不刺眼\n"
     "• 术语库扩展到 2784 条并回填现有文章\n"),
    ("0.17.0", "2026-05-25",
     "• 相关文章标题前增加论文/专利/新闻类型标签\n"
     "• 相关文章手机布局优化：纵向排列、标题左对齐、自动换行\n"
     "• 韩文/日文/俄文自动检测并翻译，翻译提示语不再限定英文\n"
     "• Google Patents 韩文编码修复：优先检测 HTML meta charset\n"
     "• 重新采集并翻译 2 篇韩文旋转爆震发动机专利\n"
     "• 左侧导航面板/筛选/搜索/收藏/事件分组管理\n"
     "• AI 问答（文章详情页悬浮按钮）\n"
     "• 月报自动预生成\n"),
    ("0.16.0", "2026-05-24",
     "• 新增相似文章推荐：文章详情页底部展示关键词重叠最多的 8 篇相关文章\n"),
    ("0.15.0", "2026-05-24",
     "• 新增关键词趋势页面 /trends，SVG 柱状图展示关键词每日文章数变化\n"
     "• 新增 AI 问答页面 /ask，基于已采集文章做 RAG 问答，引用来源可追溯\n"
     "• 新增重复文章智能合并：AAM 主题启用事件分组，文章详情页显示相关报道\n"
     "• 改进标题归一化，增加更多前缀清洗模式，提高去重准确率\n"),
    ("0.14.0", "2026-05-24",
     "• 补充 NEEDS_PROXY_DOMAINS 代理域名列表，Clash 翻墙可用\n"
     "• 恢复 8 个 GFW 被墙源（Breaking Defense、Atlantic Council 等），走 Clash 代理采集\n"
     "• 清理真正失效的源（Janes、TASS、Defence Connect、Defence Technology 等 11 个 404/403 源）\n"),
    ("0.13.0", "2026-05-24",
     "• 文章正文展示改进: 分段 <p> 渲染，移除 10000 字符截断\n"
     "• 新增缺失全文页面 /missing-content，支持单条和批量补抓\n"
     "• 新增关键词管理页面 /keywords，支持添加/删除关键词和分组\n"
     "• DB 关键词与 theme.py 默认关键词自动合并，无需重启\n"
     "• 新增 POST 路由模式支持表单提交\n"),
    ("0.12.0", "2026-05-24",
     "• 导航栏月度报告左对齐，与全部/论文等链接同级排列\n"
     "• 移除未读功能（无账户系统，共享已读状态无实际意义）\n"
     "• 统计栏精简为总计/最近24h\n"),
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
MONTHLY_REPORT_PROMPT = _t.monthly_report_prompt

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

SOURCE_SELECTORS_PATH = BASE_DIR / "data" / f"{_t.db_name}_selectors.json"

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
LLM_FALLBACK2_MODEL = os.environ.get("LLM_FALLBACK2_MODEL", "")
LLM_FALLBACK2_BASE_URL = os.environ.get("LLM_FALLBACK2_BASE_URL", "")
LLM_FALLBACK2_API_KEY = os.environ.get("LLM_FALLBACK2_API_KEY", "")
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

# Unpaywall API for open-access full text retrieval
UNPAYWALL_EMAIL = os.environ.get("UNPAYWALL_EMAIL", "zly442410610@gmail.com")

# Library proxy for CNKI full-text access
# Format: {CNKI_PROXY_BASE}/{CNKI_PROXY_TOKEN}/kcms/detail/...
#   湖北: https://ycfw.library.hb.cn:8000/https/vpn/1 (旧)
#   浙江: https://erm.zjlib.cn/goto (当前)
# Token from browser address bar, e.g. "2029748866772160513/e/xxxxx"
CNKI_PROXY_TOKEN = os.environ.get("CNKI_PROXY_TOKEN", "")
CNKI_PROXY_COOKIE = os.environ.get("CNKI_PROXY_COOKIE", "")  # Cookie like JSESSIONID (Zhejiang may not need it)
CNKI_PROXY_COOKIE_NAME = os.environ.get("CNKI_PROXY_COOKIE_NAME", "")  # e.g. JSESSIONID-UMS-ycfw.library.hb.cn
CNKI_PROXY_BASE = os.environ.get("CNKI_PROXY_BASE", "https://erm.zjlib.cn/goto")
# Load persisted proxy config from dashboard
_proxy_persist = Path(__file__).parent / ".cnki_proxy"
if _proxy_persist.exists():
    _lines = _proxy_persist.read_text().strip().split("\n")
    if len(_lines) >= 2:
        if not CNKI_PROXY_TOKEN:
            CNKI_PROXY_TOKEN = _lines[0].strip()
        if len(_lines) >= 3:
            CNKI_PROXY_COOKIE_NAME = _lines[1].strip()
            CNKI_PROXY_COOKIE = _lines[2].strip()
        else:
            CNKI_PROXY_COOKIE = _lines[1].strip()

# CNKI fetch rate limiting (random delay seconds per request)
# Library proxies block high-speed bulk downloads — keep 3-10s
CNKI_FETCH_DELAY_MIN = float(os.environ.get("CNKI_FETCH_DELAY_MIN", "3"))
CNKI_FETCH_DELAY_MAX = float(os.environ.get("CNKI_FETCH_DELAY_MAX", "10"))

# Cutoff date: only collect articles published on or after this date
COLLECT_START_DATE = os.environ.get("COLLECT_START_DATE", "2026-04-01")
