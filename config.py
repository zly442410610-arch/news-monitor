"""
Configuration for the aerospace news monitor.
Focus: solid rocket motor technology & ramjet/scramjet engine technology.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent

# --- Search Keywords ---
# Only keywords directly related to the two core technologies:
# 1) Solid rocket motors  2) Ramjet/scramjet engines
# Broad/general terms are intentionally excluded — they cause false positives.
KEYWORDS = {
    "solid_rocket": [
        # Core solid rocket motor technology terms
        "solid rocket motor",
        "solid rocket booster",
        "solid propellant",
        "composite propellant",
        "extruded propellant",
        "HTPB propellant",
        "solid motor test",
        "solid rocket",
        "solid booster",
        "solid motor",
        "propellant grain",
        "solid fuel rocket",
        "solid rocket test",
        # Specific solid rocket motor programs
        "GEM 63",
        "GEM 63XL",
        "P80",
        "P120",
        "Castor 30",
        "Castor 120",
        "SRB",
        "固体火箭发动机",
        "固体推进剂",
        "固体发动机",
        "固体火箭",
        "固体燃料",
        "固体助推器",
    ],
    "ramjet": [
        # Core ramjet/scramjet technology terms
        "ramjet",
        "scramjet",
        "supersonic combustion",
        "integrated rocket ramjet",
        "dual combustion ramjet",
        "ducted rocket",
        "ramjet test",
        "scramjet test",
        "ramjet engine",
        "scramjet engine",
        "supersonic engine",
        "air-breathing engine",
        "airbreathing propulsion",
        "冲压发动机",
        "超燃冲压",
        "超燃冲压发动机",
        "冲压",
        "高超声速推进",
        "亚燃冲压",
    ],
    "hypersonic_propulsion": [
        # Hypersonic — only when combined with propulsion context
        "hypersonic propulsion",
        "hypersonic scramjet",
        "scramjet propulsion",
        "高超声速推进",
        "高超声速发动机",
    ],
    "propulsion_tech": [
        # Additional propulsion technology terms — these cast a wider net
        # but will be strictly filtered by LLM
        "rocket engine",           # catches engine dev/test articles
        "rocket motor",            # general rocket motor term
        "rocket engine test",
        "engine test",             # catches "engine test milestone" etc.
        "hot fire test",
        "static fire",
        "thrust chamber",
        "nozzle test",
        "propulsion system",
        "rocket propellant",
        "missile propulsion",
        "cruise missile",
        "ballistic missile",
        "hypersonic",              # broader than "hypersonic propulsion"
        "air-launched rocket",     # air-launched vehicle tests
        "rocket test",             # broader than specific rocket test terms
        "launch vehicle",          # catches SRB/motor articles in launch context
        "火箭发动机",
        "发动机试验",
        "推进系统",
        "导弹推进",
        "火箭试车",
        "发动机试车",
        "高超声速",
    ],
}

# Combine all keywords into a flat list for first-pass matching
ALL_KEYWORDS = []
for group in KEYWORDS.values():
    ALL_KEYWORDS.extend(group)
ALL_KEYWORDS = sorted(set(ALL_KEYWORDS))

# Minimum relevance score for an article to be kept (0-100)
# Helps filter out tangential matches (e.g., "cruise missile" in passing)
MIN_RELEVANCE_SCORE = 15

# --- Negative patterns: articles matching these are rejected ---
# These catch non-technical content like call-for-papers, event announcements, etc.
# Patterns are checked case-insensitively against title + summary.
EXCLUDE_PATTERNS = [
    "征稿启事", "call for papers", "call for paper",
    "会议通知", "会议征文", "征文通知",
    "期刊简介", "期刊介绍", "稿约",
    "submission guidelines", "author guidelines",
    "special issue", "专刊征稿",
    # Broad/general content types that are not technical
    "weekly review", "weekly recap", "本周回顾",
]

# --- RSS News Sources ---
# Selected for technical/defense content relevance.
# Sources dominated by launch schedules or general business news are excluded.
RSS_SOURCES = {
    "Defense News": "https://www.defensenews.com/arc/outboundfeeds/rss/category/industry/",
    "Spaceflight Now": "https://spaceflightnow.com/feed/",
    "NASA Breaking News": "https://www.nasa.gov/rss/dyn/breaking_news.rss",
    "Air Force Technology": "https://www.airforce-technology.com/feed/",
    "UK Defence Journal": "https://ukdefencejournal.org.uk/feed/",
    "European Defence Review": "https://www.edrmagazine.eu/feed",
    "IEEE Spectrum": "https://spectrum.ieee.org/feeds/feed.rss",
    "Air & Space Forces Mag": "https://www.airandspaceforces.com/feed/",
    "Phys.org - Space": "https://phys.org/rss-feed/space-news/",
    "Science Daily - Space": "https://www.sciencedaily.com/rss/space_time.xml",
    "Space Intel Report": "https://www.spaceintelreport.com/feed/",
    "SpaceRef": "https://spaceref.com/feed/",
    "Naval News": "https://www.navalnews.com/feed/",
    "UK MOD Defence": "https://www.gov.uk/government/feed?organisations[]=ministry-of-defence",
    # --- Technical/propulsion-focused sources ---
    "European Spaceflight": "https://europeanspaceflight.com/feed/",
    "Ars Technica": "http://feeds.arstechnica.com/arstechnica/index",
    "JAXA (English)": "https://global.jaxa.jp/rss/press.rdf",
    "Universe Today": "https://www.universetoday.com/rss.xml",
    "Space.com": "https://www.space.com/news/rss.xml",
    "The War Zone": "https://www.thedrive.com/the-war-zone/rss",
    "Interesting Engineering": "https://interestingengineering.com/feed",
    # --- Chinese news sources ---
    "联合早报 - 中国": "https://plink.anyfeeder.com/zaobao/realtime/china",
    "联合早报 - 国际": "https://plink.anyfeeder.com/zaobao/realtime/world",
    # --- Newly added defense sources ---
    "Military Times": "https://www.militarytimes.com/arc/outboundfeeds/rss/",
    "Navy Recognition": "https://www.navyrecognition.com/feed",
    "FlightGlobal": "https://www.flightglobal.com/rss",
    "C4ISRNet": "https://www.c4isrnet.com/arc/outboundfeeds/rss/",
    # --- Extra defense/technology sources ---
    "The Aviationist": "https://theaviationist.com/feed/",
    "Popular Mechanics": "https://www.popularmechanics.com/rss/all.xml",
    "Defence Blog": "https://defence-blog.com/feed/",
    "War is Boring": "https://warisboring.com/feed/",
    "Army Technology": "https://www.army-technology.com/feed/",
    "E&T (Engineering & Tech)": "https://eandt.theiet.org/rss",
    "Defence Industry EU": "https://defence-industry.eu/feed/",
    # --- Chinese news sources (via RSS Hub mirror inside China) ---
    # Note: Toutiao/WeChat/Baijiahao don't have reliable RSS feeds.
    # Using RSS Hub mirror for Chinese tech/trending sources instead.
    "少数派": "https://rsshub.rssforever.com/sspai/index",
    "知乎日报": "https://rsshub.rssforever.com/zhihu/daily",
    "知乎热搜": "https://rsshub.rssforever.com/zhihu/hot",
    "36氪快讯": "https://rsshub.rssforever.com/36kr/newsflashes",
    "Solidot": "https://rsshub.rssforever.com/solidot/www",
    "果壳科学": "https://rsshub.rssforever.com/guokr/scientific",
    # --- Patent RSS feeds (FreePatentsOnline, by USPC class) ---
    # Class 60: Power Plants (rocket engines, jet propulsion, gas turbines)
    "FPO Patents - Power Plants": "https://www.freepatentsonline.com/rssfeed/rsspat060.xml",
    # Class 244: Aeronautics & Astronautics (spacecraft, missiles, aircraft)
    "FPO Patents - Aeronautics": "https://www.freepatentsonline.com/rssfeed/rsspat244.xml",
    # Class 102: Ammunition & Explosives (rockets, missile tech, propellants)
    "FPO Patents - Ammunition": "https://www.freepatentsonline.com/rssfeed/rsspat102.xml",
    # --- Academic paper sources ---
    # arXiv keyword search (via Atom API)
    "arXiv - 固体火箭": "https://export.arxiv.org/api/query?search_query=all:%22solid+rocket+motor%22+OR+all:%22solid+propellant%22+OR+all:%22solid+rocket+booster%22&sortBy=submittedDate&sortOrder=descending&max_results=15",
    "arXiv - 冲压发动机": "https://export.arxiv.org/api/query?search_query=all:%22scramjet%22+OR+all:%22ramjet%22+OR+all:%22scramjet+engine%22+OR+all:%22ramjet+engine%22&sortBy=submittedDate&sortOrder=descending&max_results=15",
    "arXiv - 高超声速推进": "https://export.arxiv.org/api/query?search_query=all:%22hypersonic+propulsion%22+OR+all:%22supersonic+combustion%22+OR+all:%22scramjet+propulsion%22&sortBy=submittedDate&sortOrder=descending&max_results=15",
    # CNKI 中文学术期刊 (知网)
    "CNKI - 推进技术": "http://rss.cnki.net/rss/rss.aspx?journal=TJJS&Virtual=grid20&DBCode=CJFD",
    "CNKI - 固体火箭技术": "http://rss.cnki.net/rss/rss.aspx?journal=GTHJ&Virtual=grid20&DBCode=CJFD",
    "CNKI - 宇航学报": "http://rss.cnki.net/rss/rss.aspx?journal=YHXB&Virtual=grid20&DBCode=CJFD",
    "CNKI - 航空动力学报": "http://rss.cnki.net/rss/rss.aspx?journal=HKDI&Virtual=grid20&DBCode=CJFD",
    "CNKI - 火箭推进": "http://rss.cnki.net/rss/rss.aspx?journal=HJTU&Virtual=grid20&DBCode=CJFD",
}

# --- Notification ---
# Telegram Bot (recommended)
TELEGRAM_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TG_CHAT_ID", "")

# Email (optional, requires SMTP server)
SMTP_SERVER = os.environ.get("SMTP_SERVER", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "")
EMAIL_TO = os.environ.get("EMAIL_TO", "")

# --- Storage ---
DB_PATH = BASE_DIR / "data" / "news.db"
ARCHIVE_DIR = BASE_DIR / "snapshots"
BRIEFING_DIR = BASE_DIR / "briefings"

# --- Scheduling ---
POLL_INTERVAL_MINUTES = 1440  # every 24 hours (cron handles exact 9am timing)

# --- LLM Filtering & Translation ---
LLM_API_KEY = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("LLM_API_KEY", "")
LLM_MODEL = "claude-sonnet-4-6"

# --- Translation ---
TRANSLATE_TO_CHINESE = True

TRANSLATION_PROMPT = """You are a professional aerospace translator. Translate the following news article title and summary from {source_lang} to Chinese (中文).

Requirements:
- Keep technical terms accurate (e.g., solid rocket motor → 固体火箭发动机, ramjet → 冲压发动机)
- Maintain factual accuracy, do not add or omit information
- Format: return ONLY the translation, no explanations
- If the text is already in Chinese, return it unchanged

Title: {title}
Summary: {summary}

Translated Title:
Translated Summary:"""

# --- LLM Filter ---
USE_LLM_FILTER = True  # enables strict semantic filtering

LLM_FILTER_PROMPT = """You are a strict aerospace technology filter. Determine if the following article is TECHNICALLY relevant to ONE of these specific propulsion technologies:

1. **Solid rocket motors (固体火箭发动机)** — design, testing, materials (propellant grains, HTPB, composite propellants), manufacturing, static fire tests, solid motor innovations, solid rocket booster development
2. **Ramjet / scramjet engines (冲压发动机/超燃冲压发动机)** — design, testing, supersonic combustion, dual-mode ramjet, integrated rocket-ramjet, scramjet propulsion, hypersonic air-breathing engines
3. **Missile / hypersonic propulsion (导弹/高超推进)** — missile propulsion systems, hypersonic weapon propulsion, rocket motor or ramjet/scramjet applications in missiles, propulsion for hypersonic vehicles

RULES:
- Reply YES if the article substantially discusses the ENGINEERING or TECHNOLOGY of the above propulsion systems, including missile/hypersonic propulsion
- Reply NO for: general launch mission reports, business/financial news, military contracts that don't discuss propulsion tech, satellite technology, space science unrelated to propulsion, defense budget news, missile procurement or deployment news without propulsion content
- Reply NO for: call for papers, journal announcements, submission guidelines, conference announcements, or any meta-content about publishing
- Reply NO for: articles that merely mention a keyword in passing without technical discussion
- Individual keyword mentions without technical substance → NO

Article title: {title}
Article summary: {summary}

Reply with ONLY "YES" or "NO"."""

# --- Weekly Briefing ---
BRIEFING_SUBJECT = "航天动力技术周报 - {date_range}"
BRIEFING_PROMPT = """You are a technical aerospace analyst. Produce a weekly briefing in Chinese (中文) covering news articles about solid rocket motor technology and ramjet/scramjet engine technology.

Format the briefing with these sections:
1. **本周概述 (Weekly Overview)**: 1-2 paragraph summary of the week's major technical developments
2. **关键动态 (Key Developments)**: Bullet points of the most important stories with technical analysis
3. **详细摘要 (Detailed Summaries)**: For each article, provide:
   - 标题 (Chinese)
   - 来源 | 日期
   - 技术要点 (2-3 sentences focusing on the propulsion technology aspects)
   - 原文链接
4. **趋势观察 (Trends & Analysis)**: Notable technical patterns, emerging propulsion technologies

Articles:"""

# --- Web Dashboard ---
DASHBOARD_PORT = int(os.environ.get("DASHBOARD_PORT", "8080"))
DASHBOARD_HOST = "0.0.0.0"

# --- Collector API (for domestic news collector node) ---
COLLECTOR_API_KEY = os.environ.get("COLLECTOR_API_KEY", "")
