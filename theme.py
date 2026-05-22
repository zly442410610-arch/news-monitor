"""
Monitor theme definitions.
Defines theme-specific configuration values for each monitor instance.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MonitorTheme:
    # Identity
    name: str
    app_name: str
    app_name_cn: str
    app_subtitle: str
    logger_name: str
    db_name: str
    has_event_grouping: bool
    stats_title: str
    fallback_briefing_title: str

    # Keywords & filtering
    keywords: dict = field(repr=False)
    exclude_patterns: list = field(repr=False)
    rss_sources: dict = field(repr=False)

    # Prompts
    llm_filter_prompt: str = field(repr=False)
    translation_prompt: str = field(repr=False)

    # Briefing
    briefing_subject: str = field(repr=False)
    briefing_prompt: str = field(repr=False)

    # Dashboard
    dashboard_port: int = 8080
    dashboard_title: str = ""
    dashboard_other_theme_name: str = ""
    dashboard_other_theme_url: str = ""

    # Dashboard colors
    dashboard_color_primary: str = "#38bdf8"
    dashboard_color_primary_rgb: str = "56,189,248"
    dashboard_other_theme_color: str = "#38bdf8"
    dashboard_other_theme_color_rgb: str = "56,189,248"
    dashboard_header_bg: str = "linear-gradient(135deg,#1e2a3a,#1a2332)"
    dashboard_header_border: str = "#2a4a6a"
    dashboard_header_bg_light: str = "#243447"
    dashboard_event_header_bg: str = "linear-gradient(135deg,#1e2e40,#1a2332)"
    dashboard_event_border: str = "#3a5a7a"
    dashboard_source_tag_domestic_bg: str = "#1e3a5f"
    dashboard_source_tag_domestic_color: str = "#60a5fa"

    # Notifications
    telegram_msg_cjk: str = ""
    telegram_msg_en: str = ""
    email_html_prefix: str = ""
    email_subject_prefix: str = ""
    notification_prefix: str = ""


_FILTER_NEWS = """You are a strict aerospace technology filter. Determine if the following article is TECHNICALLY relevant to ONE of these specific propulsion technologies:

1. **Solid rocket motors (固体火箭发动机)** — design, testing, materials (propellant grains, HTPB, composite propellants), manufacturing, static fire tests, solid motor innovations, solid rocket booster development
2. **Ramjet / scramjet engines (冲压发动机/超燃冲压发动机)** — design, testing, supersonic combustion, dual-mode ramjet, integrated rocket-ramjet, scramjet propulsion, hypersonic air-breathing engines
3. **Detonation engines (爆震发动机)** — rotating detonation engine (RDE), pulse detonation engine (PDE), oblique detonation engine, continuous detonation engine, detonation wave propagation, detonation combustion chamber design, detonation-based propulsion systems
4. **Missile / hypersonic propulsion (导弹/高超推进)** — missile propulsion systems, hypersonic weapon propulsion, rocket motor or ramjet/scramjet applications in missiles, propulsion for hypersonic vehicles

RULES:
- Reply YES if the article substantially discusses the ENGINEERING or TECHNOLOGY of the above propulsion systems, including missile/hypersonic propulsion
- Reply NO for: general launch mission reports, business/financial news, military contracts that don't discuss propulsion tech, satellite technology, space science unrelated to propulsion, defense budget news, missile procurement or deployment news without propulsion content
- Reply NO for: call for papers, journal announcements, submission guidelines, conference announcements, or any meta-content about publishing
- Reply NO for: articles that merely mention a keyword in passing without technical discussion

Article title: {title}
Article summary: {summary}

Reply with ONLY "YES" or "NO"."""

_FILTER_AAM = """You are a defense technology filter. Determine if the following article is relevant to air-to-air missile (AAM) technology:

1. **Air-to-air missile systems** — development, testing, production, deployment, or operational use of specific AAM models (AIM-120, AIM-9, AIM-260, IRIS-T, Meteor, PL-15, PL-10, R-77, etc.)
2. **AAM propulsion** — solid rocket motors, dual-pulse motors, ramjet motors for AAMs, thrust vectoring, nozzle technology
3. **AAM seekers & guidance** — active radar seekers, AESA seekers, imaging infrared (IIR) seekers, lock-on after launch (LOAL), datalink, mid-course guidance, missile control laws, guidance algorithms
4. **AAM testing, trials & operations** — live fire tests, captive carry tests, missile intercept tests, operational evaluation, weapon separation tests, AAM deployment
5. **Fighter AAM integration** — fighter aircraft weapon systems, AAM carriage/integration (including on F-35, F-22, Su-57, J-20, Eurofighter, Rafale, etc.), fire control radar for AAM employment, air combat exercises involving AAM usage

RULES:
- Reply YES if the article discusses any aspect of AAM systems: ENGINEERING, TECHNOLOGY, TESTING, DEPLOYMENT, PROCUREMENT, or WEAPON INTEGRATION
- Reply YES for: seeker technology, missile guidance algorithms, missile control systems, missile warheads and fuzes — these are applicable to AAMs even if not explicitly AAM-branded
- Reply YES for: fighter aircraft articles that mention AAM capability, armament, testing, or combat use
- Reply YES for: Chinese academic articles (CNKI) about missile guidance, seekers, radar guidance, infrared guidance
- Reply YES for: defense news articles that mention specific AAM models, AAM contracts, AAM programs, or AAM technology development
- Reply NO only for: articles that are purely about autonomous driving, automotive technology, commercial aviation, or airport operations with zero military relevance

When in doubt, reply YES — it is better to keep a potentially relevant article than to miss one.

Article title: {title}
Article summary: {summary}

Reply with ONLY "YES" or "NO"."""

_TRANSLATE_NEWS = """You are a professional aerospace translator. Translate the following news article title and summary from {source_lang} to Chinese (中文).

Requirements:
- Keep technical terms accurate (e.g., solid rocket motor → 固体火箭发动机, ramjet → 冲压发动机)
- Maintain factual accuracy, do not add or omit information
- If the text is already in Chinese, return it unchanged
- Respond with XML format: <translated_title>...</translated_title> followed by <translated_summary>...</translated_summary>
- No other text outside the XML tags

Original title: {title}
Original summary: {summary}"""

_TRANSLATE_AAM = """You are a professional aerospace and defense translator. Translate the following news article title and summary from {source_lang} to Chinese (中文).

Requirements:
- Keep technical terms accurate (e.g., AMRAAM → 先进中距空空导弹, IRIS-T → 红外成像制导格斗导弹)
- Maintain factual accuracy, do not add or omit information
- If the text is already in Chinese, return it unchanged
- Respond with XML format: <translated_title>...</translated_title> followed by <translated_summary>...</translated_summary>
- No other text outside the XML tags

Original title: {title}
Original summary: {summary}"""


# ── Theme instances ─────────────────────────────────────────────────────

NEWS = MonitorTheme(
    name="news",
    app_name="Solid Propulsion Monitor",
    app_name_cn="固体动力信息采集系统",
    app_subtitle="固体火箭发动机 · 冲压发动机 / 超燃冲压发动机 · 爆震发动机",
    logger_name="news-monitor",
    db_name="news",
    has_event_grouping=True,
    stats_title="固体动力信息采集系统",
    fallback_briefing_title="# 固体动力信息周报",

    keywords={
        "solid_rocket": [
            "solid rocket motor", "solid rocket booster", "solid propellant",
            "composite propellant", "extruded propellant", "HTPB propellant",
            "solid motor test", "solid rocket", "solid booster", "solid motor",
            "propellant grain", "solid fuel rocket", "solid rocket test",
            "GEM 63", "GEM 63XL", "P80", "P120", "Castor 30", "Castor 120", "SRB",
            "gel propellant", "electrically controlled propellant",
            "固体火箭发动机", "固体推进剂", "固体发动机", "固体火箭",
            "固体燃料", "固体助推器",
            "凝胶推进剂", "电控推进剂",
        ],
        "ramjet": [
            "ramjet", "scramjet", "supersonic combustion",
            "integrated rocket ramjet", "dual combustion ramjet",
            "ducted rocket", "ramjet test", "scramjet test",
            "ramjet engine", "scramjet engine", "supersonic engine",
            "air-breathing engine", "airbreathing propulsion",
            "冲压发动机", "超燃冲压", "超燃冲压发动机",
            "冲压", "高超声速推进", "亚燃冲压",
        ],
        "hypersonic_propulsion": [
            "hypersonic propulsion", "hypersonic scramjet",
            "scramjet propulsion", "高超声速推进", "高超声速发动机",
        ],
        "propulsion_tech": [
            "rocket engine", "rocket motor", "rocket engine test",
            "engine test", "hot fire test", "static fire",
            "thrust chamber", "nozzle test", "propulsion system",
            "rocket propellant", "missile propulsion",
            "cruise missile", "ballistic missile", "hypersonic",
            "air-launched rocket", "rocket test", "launch vehicle",
            "phase change propellant",
            "火箭发动机", "发动机试验", "推进系统",
            "导弹推进", "火箭试车", "发动机试车", "高超声速",
            "相变推进剂",
        ],
        "patents": [
            "patent", "patent application", "USPTO",
            "method of propelling", "propulsion system",
            "solid rocket propellant", "ramjet engine",
            "combustion chamber", "thrust vectoring",
            "nozzle design", "rocket nozzle",
            "solid fuel grain", "propellant grain",
        ],
        "detonation": [
            # English — full terms
            "rotating detonation engine", "pulse detonation engine",
            "oblique detonation engine", "continuous detonation engine",
            "rotating detonation", "pulse detonation",
            "oblique detonation", "continuous detonation",
            # English — core concepts
            "detonation wave", "detonation combustion",
            "detonation chamber", "detonation engine",
            "detonation propulsion", "detonation rocket engine",
            # English — abbreviations (contextual in aerospace literature)
            "RDE", "PDE",
            # Chinese — full terms
            "旋转爆震发动机", "脉冲爆震发动机",
            "斜爆震发动机", "连续爆震发动机",
            # Chinese — core concepts
            "旋转爆震", "脉冲爆震", "斜爆震", "连续爆震",
            "爆震波", "爆震燃烧", "爆震室",
            "爆震发动机", "爆震推进",
            # Chinese — general
            "爆震",
        ],
    },
    exclude_patterns=[
        "征稿启事", "call for papers", "call for paper",
        "会议通知", "会议征文", "征文通知",
        "期刊简介", "期刊介绍", "稿约",
        "submission guidelines", "author guidelines",
        "special issue", "专刊征稿",
        "weekly review", "weekly recap", "本周回顾",
        "investor", "quarterly results", "earnings call",
        "subscription", "subscribe", "newsletter",
        "advertise", "advertisement",
        "stock market", "share price", "dividend",
    ],
    rss_sources={
        "Defense News": "https://www.defensenews.com/arc/outboundfeeds/rss/category/industry/",
        "Air Force Technology": "https://www.airforce-technology.com/feed/",
        "UK Defence Journal": "https://ukdefencejournal.org.uk/feed/",
        "European Defence Review": "https://www.edrmagazine.eu/feed",
        "Air & Space Forces Mag": "https://www.airandspaceforces.com/feed/",
        "Naval News": "https://www.navalnews.com/feed/",
        "UK MOD Defence": "https://www.gov.uk/government/feed?organisations[]=ministry-of-defence",
        "Spaceflight Now": "https://spaceflightnow.com/feed/",
        "NASA Breaking News": "https://www.nasa.gov/rss/dyn/breaking_news.rss",
        "Ars Technica": "http://feeds.arstechnica.com/arstechnica/index",
        "IEEE Spectrum": "https://spectrum.ieee.org/feeds/feed.rss",
        "Phys.org - Space": "https://phys.org/rss-feed/space-news/",
        "Science Daily - Space": "https://www.sciencedaily.com/rss/space_time.xml",
        "Space Intel Report": "https://www.spaceintelreport.com/feed/",
        "SpaceRef": "https://spaceref.com/feed/",
        "European Spaceflight": "https://europeanspaceflight.com/feed/",
        "JAXA (English)": "https://global.jaxa.jp/rss/press.rdf",
        "Universe Today": "https://www.universetoday.com/rss.xml",
        "Space.com": "https://www.space.com/news/rss.xml",
        "The War Zone": "https://www.twz.com/feed",
        "Interesting Engineering": "https://interestingengineering.com/feed",
        "The Aviationist": "https://theaviationist.com/feed/",
        "Popular Mechanics": "https://www.popularmechanics.com/rss/all.xml",
        "Military Times": "https://www.militarytimes.com/arc/outboundfeeds/rss/",
        "Aviation Week": "https://aviationweek.com/rss.xml",
        "New Scientist": "https://www.newscientist.com/feed/home",
        "SOF News": "https://sof.news/feed/",
        "少数派": "http://localhost:1200/sspai/index",
        "知乎日报": "http://localhost:1200/zhihu/daily",
        "知乎热搜": "http://localhost:1200/zhihu/hot",
        "36氪新闻": "http://localhost:1200/36kr/news",
        "联合早报 - 中国": "https://plink.anyfeeder.com/zaobao/realtime/china",
        "联合早报 - 国际": "https://plink.anyfeeder.com/zaobao/realtime/world",
        "观察者网": "http://localhost:1200/guancha",
        "人民军事": "http://localhost:1200/people/military",
        "Solidot": "http://localhost:1200/solidot/www",
        "果壳科学": "http://localhost:1200/guokr/scientific",
        # ── Patent sources (FPO 源已移除: 数据停留在 2015 年, 已失效) ────
        "CNKI - 推进技术": "https://rss.cnki.net/rss/rss.aspx?journal=TJJS&Virtual=grid20&DBCode=CJFD",
        "CNKI - 固体火箭技术": "https://rss.cnki.net/rss/rss.aspx?journal=GTHJ&Virtual=grid20&DBCode=CJFD",
        "CNKI - 宇航学报": "https://rss.cnki.net/rss/rss.aspx?journal=YHXB&Virtual=grid20&DBCode=CJFD",
        "CNKI - 航空动力学报": "https://rss.cnki.net/rss/rss.aspx?journal=HKDI&Virtual=grid20&DBCode=CJFD",
        "CNKI - 火箭推进": "https://rss.cnki.net/rss/rss.aspx?journal=HJTU&Virtual=grid20&DBCode=CJFD",
        "CNKI - 航空学报": "https://rss.cnki.net/rss/rss.aspx?journal=HKXB&Virtual=grid20&DBCode=CJFD",
        "CNKI - 导弹与航天运载技术": "https://rss.cnki.net/rss/rss.aspx?journal=DDYH&Virtual=grid20&DBCode=CJFD",
        "CNKI - 飞航导弹": "https://rss.cnki.net/rss/rss.aspx?journal=FHDD&Virtual=grid20&DBCode=CJFD",
        "CNKI - 战术导弹技术": "https://rss.cnki.net/rss/rss.aspx?journal=ZSDD&Virtual=grid20&DBCode=CJFD",
        "AIAA J. Propulsion & Power": "https://arc.aiaa.org/action/showFeed?type=etoc&feed=rss&jc=jpp",
        "AIAA Journal": "https://arc.aiaa.org/action/showFeed?type=etoc&feed=rss&jc=aiaa",
        "Acta Astronautica": "https://rss.sciencedirect.com/publication/science/00945765",
        "Aerospace Sci & Tech": "https://rss.sciencedirect.com/publication/science/12709638",
        "Combustion and Flame": "https://rss.sciencedirect.com/publication/science/00102180",
        "Progress in Aerospace Sciences": "https://rss.sciencedirect.com/publication/science/03760421",
        "Nature Aerospace": "https://www.nature.com/subjects/aerospace-engineering.rss",
        "arXiv - Solid Rocket": "https://export.arxiv.org/api/query?search_query=all:%22solid+rocket+motor%22+OR+all:%22solid+propellant%22&sortBy=submittedDate&sortOrder=descending&max_results=15",
        "arXiv - Ramjet": "https://export.arxiv.org/api/query?search_query=all:%22ramjet%22+OR+all:%22scramjet%22+OR+all:%22supersonic+combustion%22&sortBy=submittedDate&sortOrder=descending&max_results=15",
        "Propulsion & Power Research": "https://rss.sciencedirect.com/publication/science/2212540X",
        "Springer - Solid Rocket Motor": "https://link.springer.com/search.rss?facet-content-type=Article&query=solid+rocket+motor",
        "Springer - Ramjet/Scramjet": "https://link.springer.com/search.rss?facet-content-type=Article&query=ramjet+scramjet",
        "Springer - Missile Propulsion": "https://link.springer.com/search.rss?facet-content-type=Article&query=missile+propulsion",
        "Springer - Hypersonic": "https://link.springer.com/search.rss?facet-content-type=Article&query=hypersonic+propulsion",
        "Combustion Sci & Tech": "https://www.tandfonline.com/action/showFeed?type=etoc&feed=rss&jc=gcst20",
        "ESA Space Engineering": "https://www.esa.int/rssfeed/Our_Activities/Space_Engineering_Technology",
        "Lockheed Martin": "https://news.lockheedmartin.com/news-releases?pagetemplate=rss",
        "BBC中文": "https://www.bbc.com/zhongwen/simp/index.xml",
        "央视新闻 (RSSHub)": "http://localhost:1200/cctv/world",
        "环球网军事 (RSSHub)": "http://localhost:1200/huanqiu/news/world",
        # ── 2026-05-18: 扩展源 ──────────────────────────────────────
        "Shephard Media": "https://www.shephardmedia.com/feed/",
        "Janes": "https://www.janes.com/feed",
        "Breaking Defense": "https://breakingdefense.com/feed/",
        "National Defense Mag": "https://www.nationaldefensemagazine.org/rss.xml",
        "The Defense Post": "https://www.thedefensepost.com/feed/",
        "Defence Connect": "https://www.defenceconnect.com.au/feed/",
        "Asia Pacific Defence Reporter": "https://asiapacificdefencereporter.com/feed/",
        "TASS Defense": "https://tass.com/rss/v2/defense.xml",
        "SpaceWatch Global": "https://spacewatch.global/feed/",
        "AIAA J. Spacecraft & Rockets": "https://arc.aiaa.org/action/showFeed?type=etoc&feed=rss&jc=jsr",
        "Chinese J. Aeronautics": "https://rss.sciencedirect.com/publication/science/10009361",
        "Defence Technology": "https://rss.sciencedirect.com/publication/science/20963452",
        # ── 2026-05-19: RSSHub可用源 ────────────────────────────────
        "参考消息": "http://localhost:1200/cankaoxiaoxi",
        "中国新闻网": "http://localhost:1200/chinanews",
        "知乎想法日报": "http://localhost:1200/zhihu/pin/daily",
        "知乎每周精选": "http://localhost:1200/zhihu/weekly",
        "Hacker News": "https://hnrss.org/frontpage",
        "HN Show": "https://hnrss.org/show",
        # ── 2026-05-19: 更多扩展源 ────────────────────────────────
        "澎湃新闻": "http://localhost:1200/thepaper/featured",
        "Military Embedded Systems": "https://militaryembedded.com/rss",
        "Defence Industry EU": "https://defence-industry.eu/feed/",
        "Springer - Solid Propellant": "https://link.springer.com/search.rss?facet-content-type=Article&query=solid+rocket+propellant",
        "Springer - Missile Seeker": "https://link.springer.com/search.rss?facet-content-type=Article&query=missile+seeker",
        "Springer - Air Combat": "https://link.springer.com/search.rss?facet-content-type=Article&query=air+combat",
        # ── 2026-05-20: RSSHub本地源 ────────────────────────────
        "中国军网": "http://localhost:1200/china/news/military",
        "凤凰网新闻": "http://localhost:1200/ifeng/news",
        "中华网新闻": "http://localhost:1200/china/news",
        # ── 2026-05-20: 新增国外源 (代理已启用) ────────────────────
        "BBC Technology": "https://feeds.bbci.co.uk/news/technology/rss.xml",
        "BBC Science & Environment": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
        "USNI News": "https://news.usni.org/feed",
        "DefenceTalk": "https://www.defencetalk.com/feed/",
        "Overt Defense": "https://www.overtdefense.com/feed/",
        "Defence Blog": "https://defence-blog.com/feed/",
        "Defence Aviation": "https://www.defenceaviation.com/feed/",
        "CSIS Missile Threat": "https://missilethreat.csis.org/feed/",
        "Google News - Solid Rocket": "https://news.google.com/rss/search?q=%22solid+rocket+motor%22&hl=en-US&gl=US&ceid=US:en",
        "Google News - Ramjet/Scramjet": "https://news.google.com/rss/search?q=ramjet+scramjet+hypersonic&hl=en-US&gl=US&ceid=US:en",
        "Google News - Aerospace": "https://news.google.com/rss/search?q=aerospace+propulsion&hl=en-US&gl=US&ceid=US:en",
        "Google News - Hypersonic": "https://news.google.com/rss/search?q=hypersonic+military+technology&hl=en-US&gl=US&ceid=US:en",
        "Google News - China Military": "https://news.google.com/rss/search?q=China+military+aerospace+technology&hl=en-US&gl=US&ceid=US:en",
        "TandF - Int J Energetic Materials": "https://www.tandfonline.com/action/showFeed?type=etoc&feed=rss&jc=uegm20",
        # ── 2026-05-20: Google News 原始源直连 (可抓全文) ──────────────
        "19FortyFive": "https://www.19fortyfive.com/feed/",
        "AeroTime": "https://www.aerotime.aero/feed/",
        "Aerospace America": "https://aerospaceamerica.aiaa.org/feed/",
        "Aerospace Mfg & Design": "https://www.aerospacemanufacturinganddesign.com/rss/",
        "Atlantic Council": "https://www.atlanticcouncil.org/feed/",
        "Business Insider": "https://www.businessinsider.com/rss",
        "Defence Security Asia": "https://www.defencesecurityasia.com/feed/",
        "Defense Daily": "https://www.defensedaily.com/feed/",
        "EurAsian Times": "https://www.eurasiantimes.com/feed/",
        "Orbital Today": "https://orbitaltoday.com/feed/",
        "Sandboxx": "https://www.sandboxx.us/feed/",
        "The Diplomat": "https://thediplomat.com/feed/",
        "War on the Rocks": "https://warontherocks.com/feed/",
        "Warrior Maven": "https://warriormaven.com/rss/WARMAV/full",
        "Zona Militar": "https://www.zona-militar.com/feed/",
        # ── 2026-05-21: 补充源 ──────────────────────────────────────
        "Missile Threat (CSIS)": "https://missilethreat.csis.org/feed/",
        "FlightGlobal": "https://www.flightglobal.com/rss",
        "Army Technology": "https://www.army-technology.com/feed/",
        "Defense Scoop": "https://defensescoop.com/feed/",
        "European Security Defence": "https://euro-sd.com/feed/",
        "Navy Recognition": "https://www.navyrecognition.com/feed",
        "Defence24": "https://defence24.com/feed",
        "Asian Military Review": "https://www.asianmilitaryreview.com/feed/",
        "E&T (Engineering & Tech)": "https://eandt.theiet.org/rss",
        "新浪军事": "http://localhost:1200/sina/military",
        "Next Big Future": "http://feeds.feedburner.com/blogspot/advancednano",
        "L3Harris Newsroom": "https://www.l3harris.com/newsroom/feed",
        "RTX News": "https://www.rtx.com/news/rss",
    },

    llm_filter_prompt=_FILTER_NEWS,
    translation_prompt=_TRANSLATE_NEWS,
    briefing_subject="航天动力技术周报 - {date_range}",
    briefing_prompt="""You are a technical aerospace analyst. Produce a weekly briefing in Chinese (中文) covering news articles about solid rocket motor technology and ramjet/scramjet engine technology.

Format the briefing with these sections:
1. **本周概述 (Weekly Overview)**: 1-2 paragraph summary of the week's major technical developments
2. **关键动态 (Key Developments)**: Bullet points of the most important stories with technical analysis
3. **详细摘要 (Detailed Summaries)**: For each article, provide:
   - 标题 (Chinese)
   - 来源 | 日期
   - 技术要点 (2-3 sentences focusing on the propulsion technology aspects)
   - 原文链接
4. **趋势观察 (Trends & Analysis)**: Notable technical patterns, emerging propulsion technologies

Articles:""",

    dashboard_port=8080,
    dashboard_title="固体动力信息采集系统",
    dashboard_other_theme_name="空空导弹",
    dashboard_other_theme_url="http://47.103.207.227:8081",
    dashboard_other_theme_color="#fb923c",
    dashboard_other_theme_color_rgb="251,146,60",

    telegram_msg_cjk="🚀 固体动力推送",
    telegram_msg_en="🚀 Solid Propulsion Alert",
    email_html_prefix="🚀 Solid Propulsion",
    email_subject_prefix="🚀 [固体动力]",
    notification_prefix="🚀",
)

AAM = MonitorTheme(
    name="aam",
    app_name="Air-to-Air Missile Monitor",
    app_name_cn="空空导弹信息采集系统",
    app_subtitle="总体 · 导引头 · 引战 · 舵机",
    logger_name="aam-monitor",
    db_name="aam",
    has_event_grouping=False,
    stats_title="空空导弹信息采集系统",
    fallback_briefing_title="# 空空导弹信息周报",

    keywords={
        "aam_types": [
            "AIM-120", "AMRAAM", "AIM-9", "Sidewinder",
            "AIM-260", "JATM", "AIM-7", "Sparrow",
            "AIM-54", "Phoenix missile", "AIM-174",
            "ASRAAM", "IRIS-T", "Meteor missile",
            "Python-5", "Derby missile",
            "PL-10", "PL-12", "PL-15", "PL-17", "PL-21",
            "霹雳导弹", "霹雳-10", "霹雳-12", "霹雳-15", "霹雳-17",
            "R-73", "R-77", "R-37", "RVV-SD", "KS-172",
            "air-to-air missile", "beyond-visual-range",
            "BVR missile", "air combat missile",
            "air-to-air", "air to air missile",
            "air dominance missile",
            "超视距空空导弹", "中远程空空导弹",
            "主动雷达制导空空导弹",
        ],
        "missile_overall": [
            "空空导弹总体", "导弹气动布局", "missile airframe",
            "导弹结构设计", "missile aerodynamics",
            "导弹外形设计", "aerodynamic configuration",
            "导弹弹体", "missile airframe design",
            " aerodynamic shape", "missile configuration",
            "气动外形", "气动特性", "空气动力学导弹",
            "structural design missile",
            "fin stabilization", "tail control",
            "canard configuration", "无翼式布局", "正常式布局",
            "鸭式布局", "rotary missile",
            "missile cross-section", "missile material",
            "复合材料弹体", "missile structure composite",
            "高机动导弹", "high-G missile",
            "大过载导弹", "high angle of attack missile",
            "missile agility",
        ],
        "missile_seeker": [
            "导引头", "seeker", "seeker head",
            "active radar seeker", "AESA seeker",
            "imaging infrared seeker", "IIR seeker",
            "被动雷达导引头", "passive radar seeker",
            "多模导引头", "multi-mode seeker",
            "dual-mode seeker", "双模导引头",
            "红外成像导引头", "infrared imaging seeker",
            "雷达导引头", "radar seeker", "红外导引头",
            "毫米波导引头", "millimeter wave seeker",
            "激光导引头", "laser seeker",
            "seeker antenna", "导引头天线",
            "seeker optics", "导引头光学系统",
            "seeker signal processing",
            "导引头信号处理",
            "target detection seeker",
            "导引头探测距离",
            "anti-radiation seeker",
            "seeker stabilization",
            "seeker gimbal", "稳定平台",
            "导引头小型化",
        ],
        "missile_fuze_warhead": [
            "引信", "fuze", "fuse", "proximity fuze",
            "激光引信", "laser proximity fuze",
            "无线电引信", "radio fuze",
            "红外引信", "infrared fuze",
            "引战系统", "fuze warhead system",
            "战斗部", "warhead", "定向战斗部",
            "aimable warhead", "directional warhead",
            "破片战斗部", "fragmentation warhead",
            "连续杆战斗部", "continuous rod warhead",
            "杀伤战斗部", "blast fragmentation",
            "聚焦战斗部", "focused warhead",
            "战斗部杀伤威力", "warhead lethality",
            "引战配合", "fuze warhead matching",
            "安全执行机构", "safety arm device",
            "保险机构", "missile safe arm",
            "引信抗干扰",
        ],
        "missile_actuator": [
            "舵机", "actuator", "servo actuator",
            "电动舵机", "electromechanical actuator",
            "液压舵机", "hydraulic actuator",
            "气动舵机", "pneumatic actuator",
            "电磁舵机", "EMA actuator",
            "missile fin control",
            "舵机控制系统", "actuator control system",
            "推力矢量", "thrust vectoring",
            "thrust vector control", "TVC",
            "喷气舵", "jet vane", "燃气舵",
            "气动舵面", "control surface",
            "尾舵", "tail fin control",
            "网格舵", "grid fin",
            "直接力控制", "reaction control",
            "侧向喷流", "lateral jet control",
            "姿控发动机", "attitude control motor",
            "missile maneuverability",
            "high-G maneuver",
        ],
        "missile_guidance": [
            "制导系统", "guidance system",
            "制导律", "guidance law",
            "proportional navigation", "比例导引",
            "mid-course guidance", "中制导",
            "terminal guidance", "末制导",
            "command guidance", "指令制导",
            "inertial guidance", "惯性制导",
            "inertial navigation", "INS guidance",
            "satellite guidance", "卫星制导",
            "GNSS missile", "GPS missile",
            "数据链制导", "datalink guidance",
            "track-via-missile", "TVM guidance",
            "制导控制一体化", "integrated guidance control",
            "autopilot missile", "导弹自动驾驶仪",
            "飞行控制", "flight control system",
            "制导精度", "guidance accuracy",
            "命中精度", "circular error probable",
            "制导算法", "guidance algorithm",
            "航迹规划", "trajectory planning",
            "中末制导交接班",
            "复合制导", "integrated guidance",
        ],
        "missile_datalink": [
            "数据链", "datalink", "missile datalink",
            "双向数据链", "two-way datalink",
            "机载数据链", "airborne datalink",
            "弹载数据链", "missile datalink communication",
            "missile communication",
            "武器数据链", "weapon datalink",
            "协同交战", "cooperative engagement",
            "网络化作战", "networked warfare",
            "双站通信", "missile networking",
            "中继制导", "mid-course update",
            "target update missile",
            "lock-on after launch", "LOAL",
            "lock-on before launch", "LOBL",
            "射后更新", "post-launch update",
        ],
        "missile_launch": [
            "导弹发射", "missile launch",
            "发射系统", "launch system",
            "垂直发射", "vertical launch",
            "导轨发射", "rail launch",
            "弹射发射", "ejection launch",
            "热发射", "hot launch",
            "冷发射", "cold launch",
            "内埋弹舱", "internal weapon bay",
            "外挂发射", "external carriage",
            "导轨发射架", "launch rail",
            "发射装置", "launcher",
            "universal launcher",
            "弹射装置", "catapult launcher",
            "导弹挂架", "missile pylon",
            "共架发射",
        ],
        "aam_tech_general": [
            "空空导弹", "中距空空导弹", "近距空空导弹",
            "超视距空战", "格斗导弹",
            "空对空导弹", "空战导弹",
            "AAM", "air-to-air",
            "air combat missile",
            "超视距空空导弹", "中远程空空导弹",
            "近距格斗导弹",
            "第四代空空导弹", "第五代空空导弹",
            "next generation air dominance",
            "NGAD missile",
            "dual-role missile",
            "多用途空空导弹",
            "小型化导弹", "miniaturized missile",
            "先进空空导弹", "advanced AAM",
            "空空导弹技术", "AAM technology",
            "air superiority weapon",
            "新型空空导弹",
        ],
        "missile_equipment": [
            "火控雷达", "fire control radar",
            "AESA radar", "有源相控阵雷达",
            "火力控制", "fire control system",
            "导弹瞄准", "missile targeting",
            "头盔瞄准具", "helmet mounted sight",
            "HMD/S", "瞄准系统",
            "光电瞄准", "electro-optical targeting",
            "红外搜索跟踪", "IRST",
            "infrared search track",
            "分布式孔径系统", "DAS",
            "电子支援", "electronic support",
            "导弹逼近告警", "missile approach warning",
            "MAW", "导弹告警系统",
            "敌我识别", "IFF",
            "武器管理系统", "weapon management",
            "武器投放", "weapon delivery",
            "火力控制计算机", "fire control computer",
            "机载武器系统",
        ],
        "missile_test": [
            "missile test", "missile launch",
            "missile interception", "captive carry",
            "live fire test", "missile trial",
            "flight test missile",
            "operational test", "combat evaluation",
            "导弹试验", "实弹测试", "打靶试验",
            "导弹实弹射击", "飞行试验",
            "作战试验", "定型试验",
            "拦截试验", "intercept test",
            "weapon integration", "missile integration",
            "fighter weapon",
            "air superiority",
            "air combat exercise",
            "模拟仿真", "missile simulation",
            "半实物仿真", "hardware-in-loop",
            "missile evaluation",
        ],
        "missile_ecm": [
            "电子对抗", "electronic warfare",
            "电子干扰", "electronic jamming",
            "红外干扰", "infrared countermeasure",
            "红外诱饵", "flare decoy",
            "拖曳诱饵", "towed decoy",
            "有源干扰", "active jamming",
            "被动干扰", "passive countermeasure",
            "自卫干扰", "self-protection jammer",
            "诱饵弹", "decoy flare",
            "干扰丝", "chaff",
            "定向红外对抗", "DIRCM",
            "导弹逼近告警", "missile warning",
            "紫外告警", "UV warning",
            "激光告警", "laser warning",
            "导弹对抗", "missile countermeasure",
            "电子攻击", "electronic attack",
            "红外对抗", "红外抑制",
            "射频对抗", "RF countermeasure",
        ],
        "aam_countermeasure": [
            "导弹防御", "missile defense",
            "反导", "anti-missile",
            "自卫对抗", "self-defense",
            "软杀伤", "soft kill",
            "硬杀伤", "hard kill",
            "主动防护", "active protection",
            "高功率微波", "high power microwave",
            "激光拦截", "laser interception",
            "密集阵", "close-in weapon",
        ],
    },
    exclude_patterns=[
        "car-following", "car following", "car following behavior",
        "autonomous driving", "self-driving", "autonomous vehicle",
        "autonomous navigation",
        "lane change", "traffic flow", "pedestrian detection",
        "V2V communication", "vehicle-to-vehicle",
        "investor", "quarterly results", "earnings call",
        "subscription", "subscribe", "newsletter",
        "advertise", "advertisement",
        "stock market", "share price", "dividend",
    ],
    rss_sources={
        "Defense News": "https://www.defensenews.com/arc/outboundfeeds/rss/category/industry/",
        "Air Force Technology": "https://www.airforce-technology.com/feed/",
        "UK Defence Journal": "https://ukdefencejournal.org.uk/feed/",
        "European Defence Review": "https://www.edrmagazine.eu/feed",
        "Air & Space Forces Mag": "https://www.airandspaceforces.com/feed/",
        "Naval News": "https://www.navalnews.com/feed/",
        "UK MOD Defence": "https://www.gov.uk/government/feed?organisations[]=ministry-of-defence",
        "The War Zone": "https://www.thedrive.com/the-war-zone/rss",
        "Interesting Engineering": "https://interestingengineering.com/feed",
        "European Spaceflight": "https://europeanspaceflight.com/feed/",
        "Ars Technica": "http://feeds.arstechnica.com/arstechnica/index",
        "Space News": "https://spacenews.com/feed/",
        "Breaking Defense": "https://breakingdefense.com/feed/",
        "Janes": "https://www.janes.com/feed",
        "Missile Threat (CSIS)": "https://missilethreat.csis.org/feed/",
        "联合早报 - 中国": "https://plink.anyfeeder.com/zaobao/realtime/china",
        "联合早报 - 国际": "https://plink.anyfeeder.com/zaobao/realtime/world",
        "Military Times": "https://www.militarytimes.com/arc/outboundfeeds/rss/",
        "Navy Recognition": "https://www.navyrecognition.com/feed",
        "FlightGlobal": "https://www.flightglobal.com/rss",
        "C4ISRNet": "https://www.c4isrnet.com/arc/outboundfeeds/rss/",
        "The Aviationist": "https://theaviationist.com/feed/",
        "Defence Blog": "https://defence-blog.com/feed/",
        "War is Boring": "https://warisboring.com/feed/",
        "Army Technology": "https://www.army-technology.com/feed/",
        "E&T (Engineering & Tech)": "https://eandt.theiet.org/rss",
        "Defence Industry EU": "https://defence-industry.eu/feed/",
        "Defense Scoop": "https://defensescoop.com/feed/",
        "European Security Defence": "https://euro-sd.com/feed/",
        "Defence24": "https://defence24.com/feed",
        "Asian Military Review": "https://www.asianmilitaryreview.com/feed/",
        "Military Embedded": "https://militaryembedded.com/rss",
        "Armada International": "https://www.armadainternational.com/feed/",
        "DefenceWeb": "https://www.defenceweb.co.za/feed/",
        "Joint Forces News": "https://www.joint-forces.com/feed",
        "Naval Technology": "https://www.naval-technology.com/feed/",
        "Space.com": "https://www.space.com/news/rss.xml",
        "Aviation Week": "https://aviationweek.com/rss.xml",
        "观察者网": "http://localhost:1200/guancha",
        "人民军事": "http://localhost:1200/people/military",
        "arXiv - AAM": "https://export.arxiv.org/api/query?search_query=all:%22air-to-air+missile%22+OR+all:%22missile+seeker%22+OR+all:%22air+combat+missile%22&sortBy=submittedDate&sortOrder=descending&max_results=20",
        "arXiv - missile": "https://export.arxiv.org/api/query?search_query=all:%22missile+propulsion%22+OR+all:%22ramjet+missile%22+OR+all:%22missile+guidance%22&sortBy=submittedDate&sortOrder=descending&max_results=20",
        "arXiv - guidance": "https://export.arxiv.org/api/query?search_query=all:%22missile+guidance%22+OR+all:%22thrust+vectoring%22+OR+all:%22missile+control%22&sortBy=submittedDate&sortOrder=descending&max_results=15",
        "AIAA J. Guidance & Control": "https://arc.aiaa.org/action/showFeed?type=etoc&feed=rss&jc=jgcd",
        "AIAA J. Propulsion & Power": "https://arc.aiaa.org/action/showFeed?type=etoc&feed=rss&jc=jpp",
        "Lockheed Martin": "https://news.lockheedmartin.com/news-releases?pagetemplate=rss",
        "CNKI - 航空兵器": "https://rss.cnki.net/rss/rss.aspx?journal=HKBQ&Virtual=grid20&DBCode=CJFD",
        "CNKI - 弹箭与制导学报": "https://rss.cnki.net/rss/rss.aspx?journal=DJZD&Virtual=grid20&DBCode=CJFD",
        # ── 2026-05-19: 新加中文期刊源 ──────────────────────────────
        "CNKI - 推进技术": "https://rss.cnki.net/rss/rss.aspx?journal=TJJS&Virtual=grid20&DBCode=CJFD",
        "CNKI - 固体火箭技术": "https://rss.cnki.net/rss/rss.aspx?journal=GTHJ&Virtual=grid20&DBCode=CJFD",
        "CNKI - 航空学报": "https://rss.cnki.net/rss/rss.aspx?journal=HKXB&Virtual=grid20&DBCode=CJFD",
        "CNKI - 航空动力学报": "https://rss.cnki.net/rss/rss.aspx?journal=HKDI&Virtual=grid20&DBCode=CJFD",
        "CNKI - 飞航导弹": "https://rss.cnki.net/rss/rss.aspx?journal=FHDD&Virtual=grid20&DBCode=CJFD",
        "CNKI - 宇航学报": "https://rss.cnki.net/rss/rss.aspx?journal=YHXB&Virtual=grid20&DBCode=CJFD",
        "CNKI - 导弹与航天运载技术": "https://rss.cnki.net/rss/rss.aspx?journal=DDYH&Virtual=grid20&DBCode=CJFD",
        "CNKI - 战术导弹技术": "https://rss.cnki.net/rss/rss.aspx?journal=ZSDD&Virtual=grid20&DBCode=CJFD",
        "CNKI - 火箭推进": "https://rss.cnki.net/rss/rss.aspx?journal=HJTU&Virtual=grid20&DBCode=CJFD",
        "Springer - Missile Propulsion": "https://link.springer.com/search.rss?facet-content-type=Article&query=missile+propulsion",
        "Springer - Hypersonic": "https://link.springer.com/search.rss?facet-content-type=Article&query=hypersonic+propulsion",
        "Combustion Sci & Tech": "https://www.tandfonline.com/action/showFeed?type=etoc&feed=rss&jc=gcst20",
        "Propulsion & Power Research": "https://rss.sciencedirect.com/publication/science/2212540X",
        "ESA Space Engineering": "https://www.esa.int/rssfeed/Our_Activities/Space_Engineering_Technology",
        "BBC中文": "https://www.bbc.com/zhongwen/simp/index.xml",
        "央视新闻 (RSSHub)": "http://localhost:1200/cctv/world",
        # ── 2026-05-18: 扩展源 ──────────────────────────────────────
        "Shephard Media": "https://www.shephardmedia.com/feed/",
        "National Defense Mag": "https://www.nationaldefensemagazine.org/rss.xml",
        "The Defense Post": "https://www.thedefensepost.com/feed/",
        "Defence Connect": "https://www.defenceconnect.com.au/feed/",
        "Asia Pacific Defence Reporter": "https://asiapacificdefencereporter.com/feed/",
        "TASS Defense": "https://tass.com/rss/v2/defense.xml",
        "SpaceWatch Global": "https://spacewatch.global/feed/",
        "Chinese J. Aeronautics": "https://rss.sciencedirect.com/publication/science/10009361",
        "Defence Technology": "https://rss.sciencedirect.com/publication/science/20963452",
        # ── 2026-05-19: RSSHub可用源 ────────────────────────────────
        "参考消息": "http://localhost:1200/cankaoxiaoxi",
        "中国新闻网": "http://localhost:1200/chinanews",
        "知乎想法日报": "http://localhost:1200/zhihu/pin/daily",
        "知乎每周精选": "http://localhost:1200/zhihu/weekly",
        "Hacker News": "https://hnrss.org/frontpage",
        # ── 2026-05-19: 更多扩展源 ────────────────────────────────
        "澎湃新闻": "http://localhost:1200/thepaper/featured",
        "Springer - Missile Seeker": "https://link.springer.com/search.rss?facet-content-type=Article&query=missile+seeker",
        "Springer - Air Combat": "https://link.springer.com/search.rss?facet-content-type=Article&query=air+combat",
        "Springer - Solid Propellant": "https://link.springer.com/search.rss?facet-content-type=Article&query=solid+rocket+propellant",
        # ── 2026-05-20: RSSHub本地源 ────────────────────────────
        "中国军网": "http://localhost:1200/china/news/military",
        "凤凰网新闻": "http://localhost:1200/ifeng/news",
        # ── 2026-05-20: 新增国外源 (代理已启用) ────────────────────
        "BBC Technology": "https://feeds.bbci.co.uk/news/technology/rss.xml",
        "USNI News": "https://news.usni.org/feed",
        "DefenceTalk": "https://www.defencetalk.com/feed/",
        "Overt Defense": "https://www.overtdefense.com/feed/",
        "Defence Blog": "https://defence-blog.com/feed/",
        "Defence Aviation": "https://www.defenceaviation.com/feed/",
        "CSIS Missile Threat": "https://missilethreat.csis.org/feed/",
        "Google News - AAM": "https://news.google.com/rss/search?q=%22air-to-air+missile%22&hl=en-US&gl=US&ceid=US:en",
        "Google News - Missile Defense": "https://news.google.com/rss/search?q=missile+defense+technology&hl=en-US&gl=US&ceid=US:en",
        "Google News - China Military": "https://news.google.com/rss/search?q=China+military+aerospace+technology&hl=en-US&gl=US&ceid=US:en",
        "AIAA J. Spacecraft & Rockets": "https://arc.aiaa.org/action/showFeed?type=etoc&feed=rss&jc=jsr",
        # ── 2026-05-21: 从 NEWS 补充 ─────────────────────────────────
        "Popular Mechanics": "https://www.popularmechanics.com/rss/all.xml",
        "New Scientist": "https://www.newscientist.com/feed/home",
        "The Diplomat": "https://thediplomat.com/feed/",
        "EurAsian Times": "https://www.eurasiantimes.com/feed/",
        "War on the Rocks": "https://warontherocks.com/feed/",
        "Atlantic Council": "https://www.atlanticcouncil.org/feed/",
        "Business Insider": "https://www.businessinsider.com/rss",
        "Defense Daily": "https://www.defensedaily.com/feed/",
        "SOF News": "https://sof.news/feed/",
        "19FortyFive": "https://www.19fortyfive.com/feed/",
        "AeroTime": "https://www.aerotime.aero/feed/",
        "Orbital Today": "https://orbitaltoday.com/feed/",
        "Sandboxx": "https://www.sandboxx.us/feed/",
        "Warrior Maven": "https://warriormaven.com/rss/WARMAV/full",
        "Zona Militar": "https://www.zona-militar.com/feed/",
        "环球网军事 (RSSHub)": "http://localhost:1200/huanqiu/news/world",
        "新浪军事": "http://localhost:1200/sina/military",
        "知乎日报": "http://localhost:1200/zhihu/daily",
        "Next Big Future": "http://feeds.feedburner.com/blogspot/advancednano",
        "L3Harris Newsroom": "https://www.l3harris.com/newsroom/feed",
        "RTX News": "https://www.rtx.com/news/rss",
    },

    llm_filter_prompt=_FILTER_AAM,
    translation_prompt=_TRANSLATE_AAM,
    briefing_subject="空空导弹技术周报 - {date_range}",
    briefing_prompt="""You are a technical defense analyst. Produce a weekly briefing in Chinese (中文) covering news articles about air-to-air missile (AAM) technology.

Format the briefing with these sections:
1. **本周概述 (Weekly Overview)**: 1-2 paragraph summary of the week's major developments in AAM technology
2. **关键动态 (Key Developments)**: Bullet points of the most important stories with technical analysis
3. **详细摘要 (Detailed Summaries)**: For each article, provide:
   - 标题 (Chinese)
   - 来源 | 日期
   - 技术要点 (2-3 sentences focusing on the AAM technology aspects)
   - 原文链接
4. **趋势观察 (Trends & Analysis)**: Notable technical patterns, emerging AAM technologies

Articles:""",

    dashboard_port=8081,
    dashboard_title="空空导弹信息采集系统",
    dashboard_other_theme_name="固体动力",
    dashboard_other_theme_url="http://47.103.207.227:8080",
    dashboard_other_theme_color="#38bdf8",
    dashboard_other_theme_color_rgb="56,189,248",

    dashboard_color_primary="#fb923c",
    dashboard_color_primary_rgb="251,146,60",
    dashboard_header_bg="linear-gradient(135deg,#2d1a1e,#1a1510)",
    dashboard_header_border="#5c4a2e",
    dashboard_header_bg_light="#2d1a1e",
    dashboard_event_header_bg="linear-gradient(135deg,#2a1a1e,#1a1510)",
    dashboard_event_border="#4a3a2e",
    dashboard_source_tag_domestic_bg="#2d1a1e",
    dashboard_source_tag_domestic_color="#fb923c",

    telegram_msg_cjk="🎯 空空导弹推送",
    telegram_msg_en="🎯 AAM News Alert",
    email_html_prefix="🎯 AAM News",
    email_subject_prefix="🎯 [空空导弹]",
    notification_prefix="🎯",
)


_THEME_CACHE: Optional[MonitorTheme] = None
_THEME_MAP = {"news": NEWS, "aam": AAM}


def get_theme() -> MonitorTheme:
    """Get the active theme based on MONITOR_THEME env var (default: 'news')."""
    global _THEME_CACHE
    if _THEME_CACHE is None:
        name = os.environ.get("MONITOR_THEME", "news").lower()
        _THEME_CACHE = _THEME_MAP.get(name, NEWS)
    return _THEME_CACHE
