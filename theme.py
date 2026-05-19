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
    dashboard_header_bg: str = "linear-gradient(135deg,#1e293b,#0f172a)"
    dashboard_header_border: str = "#1e3a5f"
    dashboard_header_bg_light: str = "#1e293b"
    dashboard_event_header_bg: str = "linear-gradient(135deg,#1a2a3a,#0f172a)"
    dashboard_event_border: str = "#2a4a6a"
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
3. **Missile / hypersonic propulsion (导弹/高超推进)** — missile propulsion systems, hypersonic weapon propulsion, rocket motor or ramjet/scramjet applications in missiles, propulsion for hypersonic vehicles

RULES:
- Reply YES if the article substantially discusses the ENGINEERING or TECHNOLOGY of the above propulsion systems, including missile/hypersonic propulsion
- Reply NO for: general launch mission reports, business/financial news, military contracts that don't discuss propulsion tech, satellite technology, space science unrelated to propulsion, defense budget news, missile procurement or deployment news without propulsion content
- Reply NO for: call for papers, journal announcements, submission guidelines, conference announcements, or any meta-content about publishing
- Reply NO for: articles that merely mention a keyword in passing without technical discussion

Article title: {title}
Article summary: {summary}

Reply with ONLY "YES" or "NO"."""

_FILTER_AAM = """You are a defense technology filter. Determine if the following article is TECHNICALLY relevant to air-to-air missile (AAM) technology:

1. **Air-to-air missile systems** — development, testing, production, or deployment of specific AAM models (AIM-120, AIM-9, AIM-260, IRIS-T, Meteor, PL-15, PL-10, R-77, etc.)
2. **AAM propulsion** — solid rocket motors, dual-pulse motors, ramjet motors for AAMs, thrust vectoring, nozzle technology
3. **AAM seekers & guidance** — active radar seekers, AESA seekers, imaging infrared (IIR) seekers, lock-on after launch (LOAL), datalink, mid-course guidance, missile control laws, guidance algorithms
4. **AAM testing & trials** — live fire tests, captive carry tests, missile intercept tests, operational evaluation, weapon separation tests
5. **Fighter AAM integration** — fighter aircraft weapon systems, AAM carriage/integration (including on F-35, F-22, Su-57, J-20, Eurofighter, Rafale, etc.), fire control radar for AAM employment, air combat exercises involving AAM usage

RULES:
- Reply YES if the article discusses ENGINEERING, TECHNOLOGY, TESTING, or WEAPON INTEGRATION of AAM systems or their subsystems (seekers, guidance, warheads, fuzes, propulsion, datalinks)
- Reply YES for: seeker technology, missile guidance algorithms, missile control systems, missile warheads and fuzes — these are applicable to AAMs even if not explicitly AAM-branded
- Reply YES for: fighter aircraft articles that specifically discuss AAM armament, AAM testing, or AAM combat capability
- Reply YES for: Chinese academic articles (CNKI) about missile guidance, seekers, radar guidance, infrared guidance — these are typically AAM-related
- Reply NO for: general military budget news, troop deployments, geopolitical analysis without technical content
- Reply NO for: non-AAM missile systems (cruise missiles, ballistic missiles, SAMs) unless they directly relate to AAM technology
- Reply NO for: autonomous driving, self-driving vehicles, or any automotive technology
- Reply NO for: general aviation, commercial airline operations, airport news
- Individual keyword mentions without technical substance → NO

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
    app_name="Aerospace News Monitor",
    app_name_cn="航天动力技术监测",
    app_subtitle="固体火箭发动机 · 冲压发动机 / 超燃冲压发动机",
    logger_name="news-monitor",
    db_name="news",
    has_event_grouping=True,
    stats_title="航天新闻监测",
    fallback_briefing_title="# 航天新闻周报",

    keywords={
        "solid_rocket": [
            "solid rocket motor", "solid rocket booster", "solid propellant",
            "composite propellant", "extruded propellant", "HTPB propellant",
            "solid motor test", "solid rocket", "solid booster", "solid motor",
            "propellant grain", "solid fuel rocket", "solid rocket test",
            "GEM 63", "GEM 63XL", "P80", "P120", "Castor 30", "Castor 120", "SRB",
            "固体火箭发动机", "固体推进剂", "固体发动机", "固体火箭",
            "固体燃料", "固体助推器",
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
            "火箭发动机", "发动机试验", "推进系统",
            "导弹推进", "火箭试车", "发动机试车", "高超声速",
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
        "FPO Patents - Power Plants": "https://www.freepatentsonline.com/rssfeed/rsspat060.xml",
        "FPO Patents - Aeronautics": "https://www.freepatentsonline.com/rssfeed/rsspat244.xml",
        "FPO Patents - Ammunition": "https://www.freepatentsonline.com/rssfeed/rsspat102.xml",
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
        "BBC中文 (RSSHub)": "https://rsshub.rssforever.com/bbc/chinese",
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
        "Hacker News": "https://rsshub.rssforever.com/hackernews",
        # ── 2026-05-19: 更多扩展源 ────────────────────────────────
        "澎湃新闻": "http://localhost:1200/thepaper/featured",
        "Military Embedded Systems": "https://militaryembedded.com/rss",
        "Defence Industry EU": "https://defence-industry.eu/feed/",
        "Springer - Solid Propellant": "https://link.springer.com/search.rss?facet-content-type=Article&query=solid+rocket+propellant",
        "Springer - Missile Seeker": "https://link.springer.com/search.rss?facet-content-type=Article&query=missile+seeker",
        "Springer - Air Combat": "https://link.springer.com/search.rss?facet-content-type=Article&query=air+combat",
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
    dashboard_title="航天动力监测",
    dashboard_other_theme_name="空空导弹",
    dashboard_other_theme_url="http://47.103.207.227:8081",
    dashboard_other_theme_color="#fb923c",
    dashboard_other_theme_color_rgb="251,146,60",

    telegram_msg_cjk="🚀 航天新闻推送",
    telegram_msg_en="🚀 Aerospace News Alert",
    email_html_prefix="🚀 Aerospace News",
    email_subject_prefix="🚀 [航天新闻]",
    notification_prefix="🚀",
)

AAM = MonitorTheme(
    name="aam",
    app_name="Air-to-Air Missile Monitor",
    app_name_cn="空空导弹技术监测",
    app_subtitle="AIM-120 · PL-15 · Meteor · IRIS-T · 霹雳系列",
    logger_name="aam-monitor",
    db_name="aam",
    has_event_grouping=False,
    stats_title="空空导弹监测",
    fallback_briefing_title="# 空空导弹新闻周报",

    keywords={
        "aam_types": [
            "AIM-120", "AMRAAM", "AIM-9", "Sidewinder",
            "AIM-260", "JATM", "AIM-7", "Sparrow",
            "AIM-54", "Phoenix", "AIM-174",
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
        "missile_tech": [
            "双脉冲发动机", "dual-pulse rocket",
            "thrust vectoring", "推力矢量",
            "active radar seeker", "AESA seeker",
            "imaging infrared seeker", "IIR seeker",
            "lock-on after launch", "LOAL",
            "missile datalink", "导弹数据链",
            "ramjet missile", "冲压发动机导弹",
            "固体火箭发动机导弹",
            "nozzleless booster",
            "missile propulsion",
            "solid rocket motor",
            "missile seeker", "radar seeker", "红外导引头",
            "雷达导引头", "成像导引头",
            "missile guidance", "制导系统",
            "mid-course guidance", "terminal guidance",
            "missile warhead", "定向战斗部",
            "proximity fuze", "激光近炸引信",
            "missile countermeasure",
            "electronic warfare missile",
            "红外对抗", "导弹告警",
        ],
        "air_to_air": [
            "空空导弹", "中距空空导弹", "近距空空导弹",
            "超视距空战", "格斗导弹", "红外制导",
            "雷达制导", "主动雷达制导",
            "霹雳", "PL系列", "SD-10",
            "AAM", "air-to-air",
            "空对空导弹",
            "空战", "空中优势",
            "战斗机武器", "机载导弹",
            "机载武器系统",
            "火力控制", "火控雷达",
            "射后不理", "发射后不管",
        ],
        "test_trials": [
            "missile test", "missile launch",
            "missile interception", "captive carry",
            "live fire test", "missile trial",
            "导弹试验", "实弹测试", "打靶试验",
            "wingman missile", "协同交战",
            "weapon integration", "missile integration",
            "flight test missile",
            "operational test", "combat evaluation",
            "fighter weapon",
            "air superiority",
            "air combat exercise",
            "导弹实弹射击",
        ],
        "combat_aircraft": [
            "fighter jet", "fighter aircraft",
            "stealth fighter", "五代机", "歼击机",
            "歼-20", "歼-16", "歼-10",
            "F-35", "F-22", "F-15", "F-16", "F/A-18",
            "Su-57", "Su-35", "Su-30",
            "Eurofighter", "Typhoon", "Rafale",
            "Gripen", "战斗机",
            "air combat", "空战能力",
            "超音速巡航",
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
        "BBC中文 (RSSHub)": "https://rsshub.rssforever.com/bbc/chinese",
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
        "Hacker News": "https://rsshub.rssforever.com/hackernews",
        # ── 2026-05-19: 更多扩展源 ────────────────────────────────
        "澎湃新闻": "http://localhost:1200/thepaper/featured",
        "Springer - Missile Seeker": "https://link.springer.com/search.rss?facet-content-type=Article&query=missile+seeker",
        "Springer - Air Combat": "https://link.springer.com/search.rss?facet-content-type=Article&query=air+combat",
        "Springer - Solid Propellant": "https://link.springer.com/search.rss?facet-content-type=Article&query=solid+rocket+propellant",
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
    dashboard_title="空空导弹监测",
    dashboard_other_theme_name="航天动力",
    dashboard_other_theme_url="http://47.103.207.227:8080",
    dashboard_other_theme_color="#38bdf8",
    dashboard_other_theme_color_rgb="56,189,248",

    dashboard_color_primary="#fb923c",
    dashboard_color_primary_rgb="251,146,60",
    dashboard_header_bg="linear-gradient(135deg,#2d1a0e,#1a0f0a)",
    dashboard_header_border="#5c3a1e",
    dashboard_header_bg_light="#2d1a0e",
    dashboard_event_header_bg="linear-gradient(135deg,#2a1a0e,#1a0f0a)",
    dashboard_event_border="#4a2a0e",
    dashboard_source_tag_domestic_bg="#2d1a0e",
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
