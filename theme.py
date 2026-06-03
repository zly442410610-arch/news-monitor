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

    # Monthly research survey
    monthly_report_prompt: str = field(repr=False)

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
    search_sources: dict = field(repr=False, default_factory=dict)


_FILTER_NEWS = """You are a strict aerospace technology filter. Determine if the following article is TECHNICALLY relevant to ONE of these specific propulsion technologies:

1. **Solid rocket motors (固体火箭发动机)** — design, testing, materials (propellant grains, HTPB, composite propellants), manufacturing, static fire tests, solid motor innovations, solid rocket booster development
2. **Ramjet / scramjet engines (冲压发动机/超燃冲压发动机)** — including liquid-fueled ramjets (液体冲压), solid-fuel ramjets, dual-mode ramjet, integrated rocket-ramjet, scramjet propulsion, hypersonic air-breathing engines
3. **Detonation engines (爆震发动机)** — rotating detonation engine (RDE), pulse detonation engine (PDE), oblique detonation engine, continuous detonation engine, detonation wave propagation, detonation combustion chamber design, detonation-based propulsion systems
4. **Missile / hypersonic propulsion (导弹/高超推进)** — solid/liquid-fuel ramjet or rocket motor designs for missile and hypersonic vehicle propulsion systems, scramjet combustor technology, dual-mode ramjet development, thermal management and materials for hypersonic propulsion

RULES:
- Reply YES if the article substantially discusses the ENGINEERING or TECHNOLOGY of ONE of the above propulsion systems, including details of engine design, testing, materials, or combustion
- Reply NO if the article is merely a MILITARY COMMENTARY, OPINION PIECE, or GENERAL ANALYSIS piece that mentions propulsion terms only in passing (e.g., 讲武谈兵, 析, 观察 columns from 澎湃, 凤凰, 新浪等)
- Reply NO if the article is PRIMARILY about **drones / UAVs / loitering munitions / interceptors** — even if it mentions solid rocket motors as the drone's powerplant, unless the article substantially discusses motor/propulsion engineering details
- Reply NO for: articles that match a keyword (like 固体火箭 or 火箭发动机) incidentally because the body includes it in a general list, citation, or background paragraph — the keyword must be the CENTRAL topic
- Reply NO for: general launch mission reports, business/financial news, military contracts that don't discuss propulsion tech, satellite technology, space science unrelated to propulsion, defense budget news, missile procurement or deployment news without propulsion content
- Reply NO for: call for papers, journal announcements, submission guidelines, conference announcements, or any meta-content about publishing
- Reply NO for: articles that merely mention a keyword in passing without technical discussion
- Reply NO for: **liquid rocket engines (液体火箭发动机)** — pump-fed or pressure-fed liquid-propellant rockets, cryogenic engines (LOX/LH2, LOX/kerosene, LOX/methane), thrust chamber design, injectors, turbopumps, or any liquid rocket propulsion that is NOT a ramjet/scramjet
- Reply NO for: articles that are PRIMARILY about **air-to-air missiles (空空导弹)** — including AAM seekers, guidance systems, warheads, fuzes, fighter integration of AAMs, AAM testing/trials, or specific AAM models (AIM-120, PL-15, Meteor, IRIS-T, etc.), UNLESS the article substantially discusses propulsion technology relevant to items 1-4 above
- Reply NO for: **general hypersonic weapons program overviews** — articles that broadly review multiple hypersonic weapon programs, compare weapons, or discuss race/competition narratives without substantial propulsion engineering detail
- Reply NO for: **historical retrospectives** — articles about historical flight records (e.g., X-43A, X-51A records) that merely restate past achievements without discussing current propulsion engineering developments
- Reply NO for: **high-level survey/review articles** that summarize technology domains at a conceptual level without presenting specific propulsion system design, testing, or material details

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

PATENT-SPECIFIC RULES:
- For PATENT articles: Reply NO if AAM/missile/guidance terms appear ONLY in a generic list of potential applications (e.g., "used in ABS, fuel pumps, fans, HDDs, motors, MRI, wind turbines, satellites, and missiles"). A patent passing mention of "missile" or "guidance" as one of many unrelated applications does NOT make it relevant.
- Reply NO for patents about materials science, chemistry, metallurgy, magnets, batteries, ceramics, coatings, or manufacturing processes, even if the summary mentions "missile" — unless the patent is SUBSTANTIVELY about AAM technology.
- Reply NO for patents about general-purpose components (motors, sensors, bearings, valves, connectors, magnets) that list "missile" as one of many application examples but are not designed specifically for AAMs.

When in doubt, be strict and reply NO — it is better to miss an irrelevant article than to flood the database with false positives.

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
            "specific impulse", "比冲", "密度比冲", "特征速度", "推力系数",
            "高燃速", "低燃速", "燃速催化剂", "high burning rate propellant",
            "装填分数", "loading fraction&&propellant",
            "推进剂老化", "propellant aging",
            "含硼推进剂", "富燃料推进剂", "CL-20", "HNIW", "ADN", "BAMO",
            "多脉冲发动机", "双脉冲固体", "dual pulse motor",
            "推力可调固体", "可控固体发动机", "throttleable solid",
            "钝感弹药", "insensitive munition", "cook-off", "烤燃",
            "静止试验", "static firing", "热试车",
            "固体火箭发动机", "固体推进剂", "固体发动机", "固体火箭",
            "固体燃料", "固体助推器",
            "凝胶推进剂", "电控推进剂",
            "高氯酸铵", "奥克托今", "黑索今",
            "端羟基聚丁二烯",
            "侵蚀燃烧", "erosive burning",
            "复合固体推进剂",
            "摩擦感度", "冲击感度",
            "双基推进剂", "改性双基",
            "药柱", "装药设计", "推进剂配方",
            "推进剂装药", "推进剂燃速",
            # ── New chemistry / binder / plasticizer / curing terms ──
            "PBAN", "聚丁二烯丙烯酸", "PBAA",
            "聚氨酯推进剂", "polyurethane propellant",
            "硝酸酯增塑剂", "BTTN", "TMETN", "TEGDN", "DEGDN",
            "键合剂", "bonding agent&&propellant",
            "异氰酸酯固化", "IPDI", "TDI", "MDI", "HMDI",
            "交联密度", "crosslink density&&propellant",
            "弹道调节剂", "ballistic modifier",
            "plateau burning", "平台燃烧",
            "mesa burning", "麦撒燃烧",
            "燃速催化剂",
            "燃烧效率", "固体发动机老化", "储存寿命",
            "浇注", "vacuum casting&&propellant", "固化&&推进剂",
            "金属燃料", "硼粉", "boron powder", "镁粉", "beryllium",
        ],
        "ramjet": [
            "ramjet", "scramjet", "supersonic combustion",
            "integrated rocket ramjet", "dual combustion ramjet",
            "ducted rocket", "ramjet test", "scramjet test",
            "ramjet engine", "scramjet engine", "supersonic engine",
            "air-breathing engine", "airbreathing propulsion",
            "冲压发动机", "超燃冲压", "超燃冲压发动机",
            "冲压", "高超声速推进", "亚燃冲压",
            "固体冲压", "SFRJ", "整体式冲压", "integral rocket ramjet",
            "含硼推进剂冲压", "可变流量冲压", "VFDR",
            "固体燃料冲压", "凹腔稳焰", "支板喷射",
            "激波串", "隔离段",
            "乘波体", "助推滑翔",
            "高超声速飞行器", "高超声速风洞",
            "进气道不起动", "总压恢复系数",
            # ── New ramjet/scramjet expanded terms ──
            "双模态冲压", "DMR", "dual-mode ramjet",
            "模态转换", "mode transition",
            "超燃模态", "scramjet mode", "亚燃模态",
            "火焰稳定", "flameholding", "cavity flameholder",
            "燃料喷注", "fuel injection", "strut injector",
            "横向射流", "jet in crossflow",
            "当量比", "equivalence ratio",
            "热壅塞", "thermal choking", "thermal choke",
            "吸热型燃料", "endothermic fuel", "裂解燃料",
            "再生冷却", "regenerative cooling",
            "等离子体点火", "plasma ignition",
            "火焰吹熄", "flame blowout", "blowout limit",
            "燃烧不稳定性", "screech",
            "内转式进气道", "inward turning inlet",
            "起动马赫数", "starting Mach number",
            "变几何进气道", "variable geometry inlet",
            "附面层吸除", "boundary layer bleed",
            "收缩比", "contraction ratio",
            "冷流试验", "cold flow test",
            "直连式试验", "direct connect test",
            "自由射流试验", "free jet test",
            # ── Solid rocket ramjet component keywords ──
            "一次燃烧室", "燃气发生器", "gas generator",
            "燃气发生器推进剂", "gas generator propellant",
            "贫氧推进剂", "oxygen-deficient propellant",
            "富燃料推进剂", "fuel-rich propellant",
            "含硼富燃料推进剂", "boron-loaded fuel-rich propellant",
            "补燃室", "secondary combustion chamber",
            "二次燃烧", "secondary combustion",
            "补燃", "afterburning",
            "燃气流量调节", "flow control valve",
            "喉栓", "pintle", "throttling pintle",
            "转级", "stage transition",
            "助推转巡航", "boost-sustain transition",
            "燃气导管", "gas duct",
            "空燃比", "air/fuel ratio",
            "掺混", "mixing section",
            "可调喷管", "variable nozzle",
            "突扩燃烧室", "dump combustor",
            "硼点火", "boron ignition",
            "硼燃烧", "boron combustion",
            "凝相产物", "condensed combustion product",
            "两相流损失", "two-phase flow loss",
            "喷管积渣", "slag deposition",
            "引射冲压", "ejector ramjet",
            "空气加力火箭", "air-augmented rocket",
            "弹射冲压", "eject ramjet",
            # ── Solid-fuel scramjet keywords (固体超燃冲压) ──
            "固体超燃冲压", "固体燃料超燃冲压", "solid-fuel scramjet",
            "固体火箭超燃冲压", "solid rocket scramjet",
            "固体粉末超燃冲压", "powdered fuel scramjet",
            "燃面退移", "regression rate", "fuel regression rate",
            "固体燃料药柱", "solid fuel grain",
            "富燃燃气喷射", "fuel-rich gas injection",
            "硼颗粒燃烧", "硼颗粒点火", "boron combustion",
            "气固两相流", "gas-solid two-phase flow",
            "颗粒弥散", "particle dispersion",
            "冲压补燃室", "secondary combustion chamber",
            "硼团聚", "boron agglomeration",
            "氧化硼包覆", "boron oxide coating",
            "King硼燃烧模型",
            # ── Phase change ramjet keywords (相变冲压) ──
            "相变冲压", "phase change ramjet",
            "固液相变燃料", "solid-liquid phase change fuel",
            "相变燃料", "phase change fuel",
            "微波驱动相变", "microwave-driven phase change",
            "石蜡基燃料", "paraffin fuel",
            "熔融燃料喷射", "molten fuel injection",
            "燃料雾化", "fuel atomization",
            "相变材料", "phase change material",
            "熔化潜热", "latent heat of fusion",
            "相变温度", "phase change temperature",
            # ── Special ramjet types (膏体/粉末/凝胶/水冲压) ──
            "膏体冲压发动机", "膏体冲压", "paste ramjet",
            "粉末冲压发动机", "粉末冲压", "powdered fuel ramjet",
            "凝胶冲压发动机", "凝胶冲压", "gel ramjet",
            "水冲压发动机", "水冲压", "water ramjet", "铝水冲压", "aluminum-water ramjet",
        ],
        "hypersonic_propulsion": [
            "hypersonic propulsion", "hypersonic scramjet",
            "scramjet propulsion", "高超声速推进", "高超声速发动机",
            # ── New expanded hypersonic terms ──
            "hypersonic vehicle", "高超声速飞行器",
            "X-43A", "X-51A", "WaveRider",
            "HAWC", "HIFiRE", "SCIFiRE",
            "高超-X", "Hyper-X",
            "高超声速技术验证",
            "气动热力学", "aerothermodynamics",
            "高超声速流动", "hypersonic flow",
            "气动加热", "aerodynamic heating",
            "真实气体效应", "real gas effect",
            "化学非平衡", "chemical non-equilibrium",
            "激波层", "shock layer",
            "驻点加热", "stagnation heating",
            "催化加热", "catalytic heating",
            "粘性干扰", "viscous interaction",
        ],
        "propulsion_tech": [
            "rocket engine", "rocket motor", "rocket engine test",
            "engine test", "hot fire test", "static fire",
            "thrust chamber", "nozzle test", "propulsion system",
            "rocket propellant", "missile propulsion",
            "air-launched rocket", "rocket test",
            "phase change propellant",
            "火箭发动机", "发动机试验", "推进系统",
            "导弹推进", "火箭试车", "发动机试车", "高超声速",
            "相变推进剂",
            "喷管烧蚀", "绝热层烧蚀", "碳/碳复合材料喉衬",
            "潜入喷管", "柔性喷管", "throat insert",
            "点火瞬态", "ignition transient solid",
            "TBCC", "RBCC", "TRRE", "预冷发动机",
            "壳体缠绕", "扩张段", "收敛段",
            "凝相产物", "两相流损失",
            "核热推进", "核火箭",
            "点火药", "pyrogen igniter",
            "拉瓦尔喷管",
            "热防护系统", "热障涂层", "环境障涂层",
            "超高温陶瓷", "C/SiC", "C/C",
            "烧蚀热防护", "ablative thermal protection",
            "防热瓦", "thermal protection tile", "TPS material",
            "碳/酚醛", "carbon phenolic", "PICA",
            "陶瓷基复材", "CMC", "SiC/SiC", "UHTC",
            "热防护材料", "thermal barrier coating",
            # AND-keywords (require both terms across text)
            "3D打印&&火箭", "3D打印&&发动机",
            "增材制造&&喷管", "增材制造&&火箭",
            "碳纤维&&壳体", "碳纤维&&发动机",
            "复合材料&&喷管", "复合材料&&壳体",
            "数值模拟&&固体火箭",
            # ── New expanded propulsion tech terms ──
            "钨合金", "tungsten alloy", "钼合金", "难熔金属",
            "铌合金", "C/SiC", "SiC/SiC",
            "高温合金", "superalloy", "单晶叶片",
            "镍基高温合金", "Ni-based superalloy",
            "增材制造&&推进", "additive manufacturing&&propulsion",
            "电子束熔融", "SLM", "WAAM",
            "疲劳寿命", "fatigue life", "蠕变", "creep",
            "热机械疲劳", "thermomechanical fatigue",
            "涡轮基组合循环", "turbine based combined cycle",
            "火箭基组合循环", "rocket based combined cycle",
            "宽域飞行器", "waverider",
            "等离子体点火", "激光点火",
            "数值模拟", "CFD", "有限元",
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
            # Transition
            "爆燃转爆震", "deflagration to detonation",
            # ── New expanded detonation physics terms ──
            "CJ爆震", "CJ detonation", "Chapman-Jouguet",
            "ZND模型", "ZND detonation model",
            "冯诺伊曼尖峰", "von Neumann spike",
            "压力增益燃烧", "pressure gain combustion",
            "等容燃烧", "constant volume combustion",
            "爆震胞格", "detonation cell", "cellular structure",
            "三波点", "triple point",
            "马赫杆", "Mach stem",
            "横波", "transverse wave",
            "感应区", "induction zone", "感应长度",
            "过驱爆震", "overdriven detonation",
            "旋转爆震火箭", "RDRE",
            "旋转爆震冲压", "rotating detonation ramjet",
            "爆震极限", "detonation limit",
            "淬熄", "quenching diameter",
            "爆震波速", "detonation velocity",
            # ── Rotating detonation ramjet keywords (旋转爆震冲压) ──
            "旋转爆震冲压发动机", "RDR",
            "旋转爆震燃烧室", "RDC",
            "环形燃烧室", "annular combustion chamber",
            "中心安装环式喷注器", "sting-mount injector",
            "分层喷射", "stratified injection",
            "预爆管", "pre-detonator",
            "爆震波传播", "detonation wave propagation",
            "爆震频率", "detonation frequency",
            "喷孔-环缝喷注器", "orifice-slit injector",
            "撞击式喷注器", "impinging injector",
            "自持爆震", "self-sustaining detonation",
            "旋转爆震隔离段", "RDE isolator",
            "非预混爆震", "non-premixed detonation",
            "单波模式", "双波模式", "多波模式",
            "同向传播", "对撞爆震波",
            "液体燃料旋转爆震", "liquid fuel RDE",
            "煤油旋转爆震", "kerosene RDE",
            "旋转爆震比冲", "specific impulse RDE",
            "压力增益燃烧", "pressure gain combustion",
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
        "iRNA", "RNAi",
        # ── Patent office procedural notices ─────────────────────
        "hearing diary", "听证日程", "听证日",
        # ── Liquid rocket engine (NOT ramjet) exclusion ──────────
        "液体火箭",           # matches 液体火箭发动机 but NOT 液体燃料冲压
        "液氧", "液氢",       # LOX/LH2 — unique to liquid rockets
        "氢氧发动机",
        "推力室",             # thrust chamber — liquid rocket only
        "涡轮泵", "turbopump",
        "喷注器",
        "燃气发生器", "gas generator",
        "cryogenic rocket",
        "liquid rocket engine",
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
        "联合早报 - 中国": "https://plink.anyfeeder.com/zaobao/realtime/china",
        "联合早报 - 国际": "https://plink.anyfeeder.com/zaobao/realtime/world",
        "观察者网": "http://localhost:1200/guancha",
        "人民军事": "http://localhost:1200/people/military",
        "Solidot": "http://localhost:1200/solidot/www",
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
        "National Defense Mag": "https://www.nationaldefensemagazine.org/rss.xml",
        "The Defense Post": "https://www.thedefensepost.com/feed/",
        "Asia Pacific Defence Reporter": "https://asiapacificdefencereporter.com/feed/",
        "SpaceWatch Global": "https://spacewatch.global/feed/",
        "AIAA J. Spacecraft & Rockets": "https://arc.aiaa.org/action/showFeed?type=etoc&feed=rss&jc=jsr",
        "Chinese J. Aeronautics": "https://rss.sciencedirect.com/publication/science/10009361",
        # ── 2026-05-19: RSSHub可用源 ────────────────────────────────
        "参考消息": "http://localhost:1200/cankaoxiaoxi",
        "中国新闻网": "http://localhost:1200/chinanews",
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
        "AeroTime": "https://www.aerotime.aero/feed/",
        "Aerospace America": "https://aerospaceamerica.aiaa.org/feed/",
        "Defence Security Asia": "https://www.defencesecurityasia.com/feed/",
        "Defense Daily": "https://www.defensedaily.com/feed/",
        "Warrior Maven": "https://warriormaven.com/rss/WARMAV/full",
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
        "Next Big Future": "http://feeds.feedburner.com/blogspot/advancednano",
        # ── 2026-05-24: 恢复被墙源 (走 Clash 代理) ────────────────────
        "Breaking Defense": "https://breakingdefense.com/feed/",
        "Atlantic Council": "https://www.atlanticcouncil.org/feed/",
        "Business Insider": "https://www.businessinsider.com/rss",
        "EurAsian Times": "https://www.eurasiantimes.com/feed/",
        "The Diplomat": "https://thediplomat.com/feed/",
        "War on the Rocks": "https://warontherocks.com/feed/",
        "19FortyFive": "https://www.19fortyfive.com/feed/",
        "L3Harris Newsroom": "https://www.l3harris.com/newsroom/feed",
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

    monthly_report_prompt="""You are a senior solid rocket propulsion researcher writing a professional monthly technical research survey in Chinese (中文). The report must read like a high-quality review article in a peer-reviewed journal — authoritative, data-driven, technically precise.

CORE REQUIREMENTS:
- Write a flowing, integrated analysis. Do NOT split sections into "领域现状" + "本月补充". Combine domain knowledge with this month's news naturally — e.g., "双脉冲发动机方面，PL-15通过10-30秒级间延迟将不可逃逸区扩展约50%。本月报道指出..." — the domain overview and current developments should blend seamlessly.
- Every claim about this month's developments MUST cite the article number [N]. Domain knowledge from your training does not need citations.
- BE SPECIFIC: name programs, models, parameters, companies, countries. Use concrete data: thrust, Isp, chamber pressure, diameter, mass, temperature, TRL. Avoid vague phrases like "取得显著进展" or "受到广泛关注".
- Focus on HARDWARE, PROGRAMS, MATERIALS, PROCESSES. Do NOT explain basic physics. Assume the reader is a propulsion professional.
- Show deep domain knowledge: know who is developing what worldwide, know the performance of fielded systems, understand current technology frontiers and limitations.
- Write naturally. Each section should be a coherent narrative, not a bullet list or template. Use organizational patterns that make sense for the content — comparison, chronology, problem-solution, etc.
- Total length: 3000-5000 Chinese characters.

## Suggested Structure (adapt as needed — not every section must appear, combine or split based on content):

# {year}年{month}月{topic_zh}技术研究进展综述

## 摘要
~300字高度概括本月核心动态和当前技术格局。包含至少5个具体型号和数据点。

## 1. 引言
概述当前{topic_zh}的全球发展态势和本月值得关注的动态。

## 2. 固体火箭发动机总体技术
综合分析大型固体助推器（P120C、GEM-63XL、SRB-A3等）、战术导弹发动机（MK58/60等）、上面级发动机的当前发展水平，结合本月相关报道。涵盖推力等级、直径/装药量、燃烧室压力、比冲等关键技术参数，以及推力调节、低成本制造等创新方向。

## 3. 推进剂与含能材料技术
综合分析HTPB/NEPE/HEDM等推进剂路线的最新发展水平，含CL-20/ADN/HMX等氧化剂的应用进展，低特征信号和清洁推进剂方向，装药构型设计等工艺问题。结合本月相关报道。

## 4. 结构材料与热防护技术
综合分析壳体材料（高强钢、钛合金、CFRP）、喷管材料（C/C、C/SiC、钨渗铜 >3000°C）、热防护层（EPDM绝热层、耐烧蚀涂层）的最新发展水平。结合本月相关报道。

## 5. 推力矢量控制与智能控制技术
综合分析柔性喷管TVC、机电伺服、流体TVC、双脉冲控制、数字孪生健康监测、AI推力调节等方向的最新进展。结合本月相关报道。

## 6. 制造工艺与数字化技术
综合分析增材制造、自动铺放缠绕、数字化产线、敏捷制造等工艺方向，以及成本控制和大国制造能力对比。结合本月相关报道。

## 7. 应用格局与项目动态
综合分析大型航天发射（SLS/Vega-C/H3/商业航天）、战略与战术导弹应用、全球主要研制机构（诺格、L3Harris、Avio、MBDA、航天科工等）的最新项目动态、合同与产业整合趋势。

## 8. 技术挑战与发展趋势
综合以上各领域，指出当前面临的关键瓶颈、未来3-5年的核心技术方向，以及基于本月信息反映出的新动向。

## 参考文献
[1] 标题, 来源, 日期
[2] 标题, 来源, 日期
...

Articles to review:""",

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
    has_event_grouping=True,
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
            "HOBS", "high off-boresight", "大离轴", "离轴发射",
            "AIM-9X Block II", "AIM-120D3", "CAMM", "A-Darter",
            "PL-XX", "VL MICA",
            "A射B导", "协同制导", "接力制导",
            "后向发射", "rearward launch",
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
            # AND-keywords
            "3D打印&&导弹",
            "增材制造&&导弹",
            "复合材料&&弹体",
            "碳纤维&&导弹",
            "MEMS&&导引头",
            "MEMS&&惯导",
            "大过载导弹", "high angle of attack missile",
            "missile agility",
            "大攻角", "high AoA", "过失速", "post-stall",
            "抗高过载", "高过载生存",
            "减速器",
            "气动弹性", "aeroelastic", "颤振", "flutter",
            "脱靶量", "miss distance",
            "末端机动", "end-game maneuver",
            "越肩发射", "全向攻击",
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
            "捷联导引头", "strapdown seeker", "半捷联导引头",
            "双色红外", "dual-color IR",
            "碲镉汞", "MCT", "InSb", "锑化铟",
            "焦平面阵列", "focal plane array", "FPA",
            "偏振探测", "polarization imaging",
            "非制冷红外", "uncooled IR",
            "InGaAs",
            "雪崩光电二极管",
            "红外焦平面",
            "截获概率", "target acquisition seeker",
            "角闪烁", "glint",
            "单脉冲导引头", "passive tracking",
            "多模寻的",
        ],
        "missile_fuze_warhead": [
            "引信", "fuze", "fuse&&missile", "proximity fuze",
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
            "激光定距", "激光测距引信",
            "自适应起爆", "adaptive initiation",
            "多普勒近炸", "Doppler proximity fuze",
            "电容近炸", "target detection fuze",
            "MEMS引信",
            "无线电高度表", "radio altimeter fuze",
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
            "MEMS IMU", "微惯导", "微机电惯性",
            "频率捷变", "frequency agility", "波形捷变",
            "滑模制导", "变结构制导",
            "多弹协同", "末端导引",
            "增广比例导引", "augmented proportional navigation",
            "剩余飞行时间", "time-to-go",
            "导航比", "制导误差",
            "捷联惯导", "strapdown INS",
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
            "复合挂架",
            "弹射挂架", "ejector rack",
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
            "launch vehicle", "可重复使用火箭", "reusable rocket",
            "hypersonic weapon", "hypersonic missile",
            "高超音速武器", "高超音速导弹",
            "next-gen weapon",
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
            "杀伤概率", "SSPK", "单发杀伤概率",
            "不可逃逸区", "no escape zone", "NEZ",
            "蒙特卡洛仿真", "Monte Carlo simulation",
            "靶试", "靶场试验",
            "挂飞试验",
            "遥测数据",
            "武器分离", "弹射分离",
            "发射包线", "launch envelope",
            "攻击区", "missile engagement zone",
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
            "距离拖引", "速度拖引",
            "角度欺骗", "angle deception",
        ],
        "hypersonic_weapons": [
            "hypersonic weapon", "hypersonic missile",
            "高超音速武器", "高超音速导弹", "高超声速武器",
            "hypersonic race", "hypersonic program",
            "hypersonic boost-glide", "boost glide", "助推滑翔",
            "hypersonic glide", "HGV", "高超音速滑翔",
            "hypersonic cruise missile", "高超音速巡航导弹",
            "HACM",
            "LRHW", "远程高超音速武器",
            "ARRW", "AGM-183A",
            "C-HGB", "通用高超音速滑翔体",
            "Dark Eagle", "暗鹰",
            "hypersonic strike", "高超音速打击",
            "next-gen weapon",
            "hypersonic interceptor", "高超音速拦截",
            "Glide Breaker",
            "临近空间", "near space",
            "high-speed strike weapon",
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
        "iRNA", "RNAi",
    ],
    rss_sources={
        "Defense News": "https://www.defensenews.com/arc/outboundfeeds/rss/category/industry/",
        "Air Force Technology": "https://www.airforce-technology.com/feed/",
        "UK Defence Journal": "https://ukdefencejournal.org.uk/feed/",
        "European Defence Review": "https://www.edrmagazine.eu/feed",
        "Air & Space Forces Mag": "https://www.airandspaceforces.com/feed/",
        "Naval News": "https://www.navalnews.com/feed/",
        "UK MOD Defence": "https://www.gov.uk/government/feed?organisations[]=ministry-of-defence",
        "The War Zone": "https://www.twz.com/feed",
        "Space News": "https://spacenews.com/feed/",
        "Missile Threat (CSIS)": "https://missilethreat.csis.org/feed/",
        "Military Times": "https://www.militarytimes.com/arc/outboundfeeds/rss/",
        "Navy Recognition": "https://www.navyrecognition.com/feed",
        "FlightGlobal": "https://www.flightglobal.com/rss",
        "C4ISRNet": "https://www.c4isrnet.com/arc/outboundfeeds/rss/",
        "The Aviationist": "https://theaviationist.com/feed/",
        "Defence Blog": "https://defence-blog.com/feed/",
        "War is Boring": "https://warisboring.com/feed/",
        "Army Technology": "https://www.army-technology.com/feed/",
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
        "Aviation Week": "https://aviationweek.com/rss.xml",
        "观察者网": "http://localhost:1200/guancha",
        "arXiv - AAM": "https://export.arxiv.org/api/query?search_query=all:%22air-to-air+missile%22+OR+all:%22missile+seeker%22+OR+all:%22air+combat+missile%22&sortBy=submittedDate&sortOrder=descending&max_results=20",
        "arXiv - missile": "https://export.arxiv.org/api/query?search_query=all:%22missile+propulsion%22+OR+all:%22ramjet+missile%22+OR+all:%22missile+guidance%22&sortBy=submittedDate&sortOrder=descending&max_results=20",
        "arXiv - guidance": "https://export.arxiv.org/api/query?search_query=all:%22missile+guidance%22+OR+all:%22thrust+vectoring%22+OR+all:%22missile+control%22&sortBy=submittedDate&sortOrder=descending&max_results=15",
        "AIAA J. Guidance & Control": "https://arc.aiaa.org/action/showFeed?type=etoc&feed=rss&jc=jgcd",
        "AIAA J. Propulsion & Power": "https://arc.aiaa.org/action/showFeed?type=etoc&feed=rss&jc=jpp",
        "Lockheed Martin": "https://news.lockheedmartin.com/news-releases?pagetemplate=rss",
        "CNKI - 航空兵器": "https://rss.cnki.net/rss/rss.aspx?journal=HKBQ&Virtual=grid20&DBCode=CJFD",
        "CNKI - 弹箭与制导学报": "https://rss.cnki.net/rss/rss.aspx?journal=DJZD&Virtual=grid20&DBCode=CJFD",
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
        "Springer - Missile Seeker": "https://link.springer.com/search.rss?facet-content-type=Article&query=missile+seeker",
        "Springer - Air Combat": "https://link.springer.com/search.rss?facet-content-type=Article&query=air+combat",
        "Springer - Solid Propellant": "https://link.springer.com/search.rss?facet-content-type=Article&query=solid+rocket+propellant",
        "Combustion Sci & Tech": "https://www.tandfonline.com/action/showFeed?type=etoc&feed=rss&jc=gcst20",
        "Propulsion & Power Research": "https://rss.sciencedirect.com/publication/science/2212540X",
        "Chinese J. Aeronautics": "https://rss.sciencedirect.com/publication/science/10009361",
        "央视新闻 (RSSHub)": "http://localhost:1200/cctv/world",
        "National Defense Mag": "https://www.nationaldefensemagazine.org/rss.xml",
        "The Defense Post": "https://www.thedefensepost.com/feed/",
        "Asia Pacific Defence Reporter": "https://asiapacificdefencereporter.com/feed/",
        "USNI News": "https://news.usni.org/feed",
        "DefenceTalk": "https://www.defencetalk.com/feed/",
        "Overt Defense": "https://www.overtdefense.com/feed/",
        "Defence Aviation": "https://www.defenceaviation.com/feed/",
        "CSIS Missile Threat": "https://missilethreat.csis.org/feed/",
        "Google News - AAM": "https://news.google.com/rss/search?q=%22air-to-air+missile%22&hl=en-US&gl=US&ceid=US:en",
        "Google News - Missile Defense": "https://news.google.com/rss/search?q=missile+defense+technology&hl=en-US&gl=US&ceid=US:en",
        "Google News - China Military": "https://news.google.com/rss/search?q=China+military+aerospace+technology&hl=en-US&gl=US&ceid=US:en",
        "Google News - Air Combat": "https://news.google.com/rss/search?q=air+combat+missile&hl=en-US&gl=US&ceid=US:en",
        "Google News - BVR": "https://news.google.com/rss/search?q=%22beyond+visual+range%22+missile&hl=en-US&gl=US&ceid=US:en",
        "Google News - Air Superiority": "https://news.google.com/rss/search?q=air+superiority+fighter&hl=en-US&gl=US&ceid=US:en",
        "Google News - AAM Chinese": "https://news.google.com/rss/search?q=%E7%A9%BA%E7%A9%BA%E5%AF%BC%E5%BC%B9&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "Google News - Missile Seeker": "https://news.google.com/rss/search?q=missile+seeker+guidance&hl=en-US&gl=US&ceid=US:en",
        "Google News - Fighter Weapon": "https://news.google.com/rss/search?q=fighter+weapon+system&hl=en-US&gl=US&ceid=US:en",
        "Google News - Hypersonic": "https://news.google.com/rss/search?q=hypersonic+military+technology&hl=en-US&gl=US&ceid=US:en",
        "AIAA J. Spacecraft & Rockets": "https://arc.aiaa.org/action/showFeed?type=etoc&feed=rss&jc=jsr",
        "Defense Daily": "https://www.defensedaily.com/feed/",
        "AeroTime": "https://www.aerotime.aero/feed/",
        "Warrior Maven": "https://warriormaven.com/rss/WARMAV/full",
        "Breaking Defense": "https://breakingdefense.com/feed/",
        "Atlantic Council": "https://www.atlanticcouncil.org/feed/",
        "EurAsian Times": "https://www.eurasiantimes.com/feed/",
        "The Diplomat": "https://thediplomat.com/feed/",
        "War on the Rocks": "https://warontherocks.com/feed/",
        "19FortyFive": "https://www.19fortyfive.com/feed/",
        "L3Harris Newsroom": "https://www.l3harris.com/newsroom/feed",
        # ── Chinese news sources (shared with news theme) ────────────────
        "联合早报 - 中国": "https://plink.anyfeeder.com/zaobao/realtime/china",
        "联合早报 - 国际": "https://plink.anyfeeder.com/zaobao/realtime/world",
        "人民军事": "http://localhost:1200/people/military",
        "Solidot": "http://localhost:1200/solidot/www",
        "BBC中文": "https://www.bbc.com/zhongwen/simp/index.xml",
        "环球网军事 (RSSHub)": "http://localhost:1200/huanqiu/news/world",
        "参考消息": "http://localhost:1200/cankaoxiaoxi",
        "中国新闻网": "http://localhost:1200/chinanews",
        "澎湃新闻": "http://localhost:1200/thepaper/featured",
        "中国军网": "http://localhost:1200/china/news/military",
        "凤凰网新闻": "http://localhost:1200/ifeng/news",
        "中华网新闻": "http://localhost:1200/china/news",
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

    monthly_report_prompt="""You are a senior air-to-air missile (AAM) technology researcher writing a professional monthly technical research survey in Chinese (中文). The report must read like a high-quality review article in a peer-reviewed journal — authoritative, data-driven, technically precise.

CORE REQUIREMENTS:
- Write a flowing, integrated analysis. Do NOT split sections into "领域现状" + "本月补充". Combine domain knowledge with this month's news naturally — e.g., "主动雷达导引头方面，AIM-120D的HTCC天线可在Ku波段实现40km以上探测距离。本月报道指出..." — domain overview and current developments should blend seamlessly.
- Every claim about this month's developments MUST cite the article number [N]. Domain knowledge from your training does not need citations.
- BE SPECIFIC: name missile designations (AIM-120D, PL-15, Meteor, AIM-260, etc.), technical parameters (range, speed, seeker type, warhead mass, g-limit, diameter), programs, countries, companies.
- Focus on HARDWARE, PROGRAMS, SENSORS, PROPULSION, MATERIALS. Do NOT explain basic concepts. Assume the reader is a defense technology professional.
- Show deep domain knowledge: know the global AAM landscape (US/EU/CN/RU/emerging programs), fielded system performance, current technology frontiers.
- Write naturally. Each section should be a coherent narrative, not a bullet list or template.
- Total length: 3000-5000 Chinese characters.

## Suggested Structure (adapt as needed — combine or split based on content):

# {year}年{month}月{topic_zh}技术研究进展综述

## 摘要
~300字高度概括本月核心动态和技术格局。包含至少5个具体型号和数据点。

## 1. 引言
概述当前{topic_zh}的全球发展态势和本月值得关注的动态。

## 2. 导弹总体设计技术
综合分析远程化（AIM-260/PL-17/Meteor射程150-300km）、小型化内埋化（F-35/J-20弹舱约束弹长<4m弹径<200mm）、隐身设计（RCS减缩、菱形弹体、吸波材料）、模块化等方向的当前发展水平，结合本月相关报道。

## 3. 导引头与目标探测技术
综合分析AESA雷达导引头（GaN器件、X/Ku波段）、红外成像（双色MWIR/SWIR阵列1280×1024+）、多模复合导引、LPI波形设计的当前发展水平，各国路线对比（雷神/MBDA/中国），结合本月相关报道。

## 4. 动力推进系统
综合分析双脉冲固体火箭（PL-15核心优势、10-30s级间延迟、不可逃逸区扩展~50%）、冲压发动机（Meteor VFDR、含硼富燃料推进剂、M3-4巡航）、固体火箭（MK58/60比冲230-260s）、TVC（AIM-9X喷流偏转±20°、瞬时转弯>100°/s）、低特征信号推进剂的当前发展水平，结合本月相关报道。

## 5. 制导与控制技术
综合分析中段制导（INS+GNSS+数据链修正、A射B导）、末段制导（APN/OGL/自适应滑模）、协同交战（Link-16/MADL多机协同、接力制导）、AI辅助制导（强化学习航路规划、SAR自动目标识别）的当前发展水平，结合本月相关报道。

## 6. 引信与战斗部技术
综合分析主动激光/无线电引信、连续杆/破片/定向战斗部（AIM-120D的WDU-41B 22.7kg HG-70A）、定向能量聚焦效率提升200-300%的当前发展水平，结合本月相关报道。

## 7. 电子对抗与生存能力
综合分析弹载电子对抗（DRFM欺骗干扰、拖曳诱饵GEN-X/ALE系列）、RWR/MAWS数字信道化接收机、LPI数据链（MADL/TTNT）、协同对抗（多机ESM无源定位/互相照射）、红外对抗（DIRCM/双色鉴别）的当前发展水平，结合本月相关报道。

## 8. 应用格局与项目动态
综合分析全球AAM项目：美国（AIM-260 JATM、AIM-9X Block II+、NGAD武器）、欧洲（Meteor、IRIS-T Block II、EUROPAAM）、中国（PL-15E出口型、PL-10E、PL-XX极远程）、俄罗斯（R-77M、R-37M）、新兴国家（Astra Mk2、A-Darter）的最新测试、列装、合同和产业动态。

## 9. 技术挑战与发展趋势
综合指出当前面临的关键瓶颈（射程/机动性/隐身/成本的多维约束）、未来3-5年的核心技术方向，以及基于本月信息的新动向。

## 参考文献
[1] 标题, 来源, 日期
[2] 标题, 来源, 日期
...

Articles to review:""",


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
