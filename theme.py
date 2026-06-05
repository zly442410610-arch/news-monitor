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

_FILTER_AAM = """You are a defense technology filter. Determine if the following article is relevant to air-to-air missile (AAM) technology, air combat operations/tactics, fighter aircraft / UAVs, or hypersonic weapon technology:

1. **Air-to-air missile systems** — development, testing, production, deployment, or operational use of specific AAM models (AIM-120, AIM-9, AIM-260, IRIS-T, Meteor, PL-15, PL-10, R-77, etc.)
2. **AAM propulsion** — solid rocket motors, dual-pulse motors, ramjet motors for AAMs, thrust vectoring, nozzle technology
3. **AAM seekers & guidance** — active radar seekers, AESA seekers, imaging infrared (IIR) seekers, lock-on after launch (LOAL), datalink, mid-course guidance, missile control laws, guidance algorithms
4. **AAM testing, trials & operations** — live fire tests, captive carry tests, missile intercept tests, operational evaluation, weapon separation tests, AAM deployment
5. **Fighter AAM integration** — fighter aircraft weapon systems, AAM carriage/integration, fire control radar for AAM employment, air combat exercises involving AAM usage
6. **Hypersonic weapon technology** — hypersonic missile and weapon programs (ARRW, HACM, LRHW, Dark Eagle, C-HGB, Glide Breaker, etc.), hypersonic boost-glide vehicles, hypersonic cruise missiles, hypersonic propulsion, scramjet/ramjet for hypersonic vehicles
7. **Hypersonic missile defense** — counter-hypersonic systems, hypersonic interceptors, Glide Breaker, missile defense technology
8. **Fighter aircraft** — development, testing, production, deployment, or modernization of fighter/combat aircraft (J-20, J-35, F-35, F-22, F-15, F-16, Eurofighter, Rafale, Su-27/30/34/35/57, MiG-29/31/35, KF-21, Tejas, etc.), sixth-generation fighter programs (NGAD, GCAP, FCAS, etc.), fighter aircraft technology, fighter engine development, trainer aircraft
9. **Unmanned aerial vehicles (UAVs)** — military drone development, testing, and deployment (MQ-9, Global Hawk, attack-11, GJ-11, Chinese UAVs, loitering munitions), unmanned combat aerial vehicles (UCAVs), Collaborative Combat Aircraft (CCA), drone swarms, autonomous aircraft technology
10. **Air combat operations & tactics** — air combat operations, beyond-visual-range (BVR) combat, within-visual-range (WVR) engagement, air superiority campaigns, air combat training and exercises, air combat tactics and doctrine

RULES:
- Reply YES if the article discusses any aspect of AAM systems: ENGINEERING, TECHNOLOGY, TESTING, DEPLOYMENT, PROCUREMENT, or WEAPON INTEGRATION
- Reply YES for: seeker technology, missile guidance algorithms, missile control systems, missile warheads and fuzes — these are applicable to AAMs even if not explicitly AAM-branded
- Reply YES for: fighter aircraft articles that mention AAM capability, armament, testing, or combat use
- Reply YES for: defense news articles that mention specific AAM models, AAM contracts, AAM programs, or AAM technology development
- Reply YES for: hypersonic weapon PROGRAM developments, flight tests, new contracts, technology demonstrations (e.g., ARRW, HACM, LRHW, Dark Eagle, Glide Breaker, or other hypersonic weapon systems)
- Reply YES for: hypersonic missile technology — propulsion, aerodynamics, thermal protection, guidance, materials for hypersonic vehicles
- Reply YES for: counter-hypersonic / missile defense technology development and testing
- Reply YES for: ANY military missile test, even if not explicitly labeled as AAM — including surface-to-air, air-to-ground, anti-ship, or ballistic missile tests, as these often share technology with AAMs
- Reply YES for: articles about fighter aircraft development, testing, production, or combat use — including new fighter programs, fighter technology, fighter engine development, and fighter modernization
- Reply YES for: articles about military UAV/UCAV/drone development, testing, deployment, drone technology, drone swarms, autonomous aircraft, or drone warfare
- Reply YES for: articles about trainer aircraft, combat aircraft engine development, aircraft armament and weapon systems integration
- Reply YES for: articles about air combat operations, tactics, air superiority, BVR/WVR engagements, air combat training and exercises
- Reply NO for: battlefield reports, combat footage, or "X launched Y missiles at Z city" — articles whose primary focus is a military strike event rather than the weapon system itself
- Reply NO for: market research reports, business/industry size forecasts, or financial analysis pieces
- Reply NO for: articles that are purely about autonomous driving, automotive technology, commercial aviation, or airport operations with zero military relevance
- Reply NO for: articles PRIMARILY about nuclear weapons, nuclear strategy, nuclear deterrence, nuclear arms control, or nuclear proliferation — these should go to the DW (防务观察) panel instead
- Reply NO for: articles that MENTION a fighter model number (F-16, F-35, F-15, F-22, F/A-18, MiG-29, J-20, Su-57, etc.) in passing but whose PRIMARY TOPIC is geopolitics, defense budgets, military sales, NATO security, regional security, sanctions, arms deals, or general military strategy — these should go to the DW (防务观察) panel instead

PATENT-SPECIFIC RULES:
- For PATENT articles: Reply NO if AAM/missile/guidance terms appear ONLY in a generic list of potential applications (e.g., "used in ABS, fuel pumps, fans, HDDs, motors, MRI, wind turbines, satellites, and missiles"). A patent passing mention of "missile" or "guidance" as one of many unrelated applications does NOT make it relevant.
- Reply NO for patents about materials science, chemistry, metallurgy, magnets, batteries, ceramics, coatings, or manufacturing processes, even if the summary mentions "missile" — unless the patent is SUBSTANTIVELY about AAM technology.
- Reply NO for patents about general-purpose components (motors, sensors, bearings, valves, connectors, magnets) that list "missile" as one of many application examples but are not designed specifically for AAMs.

When in doubt, reply YES for military technology articles, reply NO only for battlefield event reports and market research.

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

_FILTER_DW = """You are a global defense and military intelligence filter. Determine if the following article is relevant to the military power, weapons systems, strategy, or defense intelligence of major military powers:

1. **US military & weapons** — US force posture, defense budget, weapons programs (fighters, bombers, carriers, submarines, missiles), military technology, Pentagon strategy, defense industry, military exercises, overseas basing
2. **Chinese military modernization** — PLA force structure, defense budget, military reform, joint operations, military-civil fusion, military exercises, defense white papers
3. **Chinese weapon systems** — naval (carriers, destroyers, submarines, amphibious ships), air (fighters, bombers, UAVs, AWACS), missile (ballistic, cruise, anti-ship, air defense, hypersonic), ground (tanks, artillery, rocket artillery)
4. **Russian military & weapons** — Russian armed forces, new weapons systems, military modernization, defense industry, nuclear forces, hypersonic weapons, military exercises, operations
5. **European defense** — NATO capabilities, European defense initiatives, European fighter programs (Eurofighter, Rafale, GCAP, FCAS/SCAF), European missile systems, EU defense policy, defense spending
6. **Indian military & weapons** — Indian armed forces modernization, weapons development, defense industry, China-India military rivalry, Indian procurement
7. **Indo-Pacific defense dynamics** — Japan, South Korea, Australia, Taiwan military developments, defense modernization, regional security, military exercises
8. **Military strategy and doctrine** — A2/AD, space/cyber warfare, nuclear policy and deterrence, military diplomacy, defense strategy documents
9. **Defense intelligence and assessment** — military balance assessments, capability analyses, US/foreign defense intelligence reports, military comparison studies
10. **Defense industry globally** — production capacity, military technology development, defense spending, arms trade

RULES:
- Reply YES for any article substantially about military capabilities, weapon systems, military strategy, or defense intelligence of major powers
- Reply YES for government defense reports, defense white papers, military assessments
- Reply YES for defense industry and military technology development
- Reply YES for military exercises, defense activities, military diplomacy
- Reply YES for hypersonic weapons and missile systems in any major power context
- Reply YES for nuclear weapons, nuclear strategy, nuclear deterrence, nuclear policy, and nuclear proliferation
- Reply YES for articles about geopolitics, defense budgets, military sales, NATO/regional security, or arms deals — even if they mention fighter model numbers (F-16, F-35, etc.) or missile names in passing
- Reply NO for articles PRIMARILY about air-to-air missile (AAM) technology — these should go to the AAM panel instead
- Reply NO for articles PRIMARILY about fighter aircraft or unmanned aerial vehicles (UAVs) — including fighter development, fighter programs, military drones, UAV technology, or combat aircraft — these should go to the AAM panel instead
- Reply NO for articles PRIMARILY about air combat operations, tactics, or air superiority — these should go to the AAM panel instead
- Reply NO for articles PRIMARILY about solid rocket propulsion / ramjet propulsion — these should go to the NEWS (固体动力) panel instead
- Reply NO for general domestic politics, economics, or social issues without a substantive military/defense component
- Reply NO for battlefield reports focused on military strike events rather than the weapon system itself
- Reply NO for market research or financial analysis

When in doubt, reply YES for military technology and strategy articles.

Article title: {title}
Article summary: {summary}

Reply with ONLY "YES" or "NO"."""

_TRANSLATE_DW = """You are a professional defense and intelligence translator. Translate the following news article title and summary from {source_lang} to Chinese (中文).

Requirements:
- Keep military/defense terms accurate
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
            # ── New energetic materials ──
            "TKX-50", "FOX-7", "FOX-12", "MAD-X1",
            "LLM-105", "TAGeT", "TAGeT propellant",
            "GAP propellant", "GAP推进剂",
            "polyNIMMO", "polyGLYN",
            "HTPE propellant", "HTPE推进剂",
            "NEPE推进剂", "NEPE propellant",
            "Al-icet", "纳米铝粉", "nano-aluminum",
            "LiAlH4", "铝氢化锂",
            "储氢推进剂", "hydrogen storage propellant",
            "高能固体推进剂", "high energy solid propellant",
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
            # ── RDRE / RDE program names ──
            "RDRE program", "RDE program",
            "rotating detonation rocket engine program",
            "RDE demonstrator", "RDE flight demo",
            "RDE test stand", "detonation engine test",
            "rotating detonation test",
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
    rss_sources={},  # Unified in data/rss_sources_all.json

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
    app_subtitle="总体 · 导引头 · 引战 · 舵机 · 制导",
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
            # ── New AAM program names ──
            "JNAAM", "KF-21 AAM", "Korean AAM",
            "quadpack", "quad missile carriage",
            "internal carriage", "weapon bay",
            "外挂导弹", "内埋弹舱", "导弹挂架",
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
            # ── New EW／countermeasure terms ──
            "electronic attack missile",
            "decoy missile", "微型空射诱饵",
            "MALD", "miniature air-launched decoy",
            "towed decoy", "拖曳诱饵",
            "missile warning system", "导弹逼近告警系统",
            "分布式孔径系统", "DAS",
            "光电对抗", "EO countermeasure",
            "多光谱对抗", "multispectral countermeasure",
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
            # ── New countermeasure terms ──
            "C-UAS missile", "anti-drone missile",
            "drone intercept missile", "反无人机导弹",
            "loitering munition countermeasure",
            "directed energy weapon", "高能激光",
            "electronic warfare missile",
        ],
        "fighter_uav": [
            # ── Air combat general keywords ──
            "空战", "air combat",
            "制空权", "air superiority", "空中优势",
            "air dominance",
            "超视距空战", "BVR combat", "近距格斗",
            "dogfight", "WVR combat", "空中交战",
            "夺取制空权", "空战战术",
            "空战训练", "air combat exercise",
            "空战模拟", "air combat simulation",
            # ── Chinese fighters & UAVs (moved from DW) ──
            "歼-20", "J-20", "威龙",
            "歼-10", "歼-16", "歼轰-7",
            "歼-36", "J-36", "歼-50", "J-50",
            "歼-15", "歼-15T", "J-15",
            "六代机", "第六代战斗机", "sixth-generation China",
            "隐身战机", "stealth fighter China",
            "无人机", "UAV China", "攻击-11", "GJ-11",
            "翔龙", "彩虹", "翼龙", "无侦-8",
            "Chinese drone", "unmanned China military",
            "教练机", "trainer aircraft China",
            "发动机&&歼", "涡扇&&中国",
            # ── US fighters & UAVs (moved from DW) ──
            "F-35", "F-22", "F-15", "F-16", "F/A-18",
            "NGAD", "Next Generation Air Dominance",
            "CCA", "Collaborative Combat Aircraft",
            "六代机美国", "美国六代机",
            "MQ-9", "MQ-4", "RQ-4", "Global Hawk",
            # ── European fighter programs (moved from DW) ──
            "Eurofighter", "Typhoon",
            "Rafale", "阵风",
            "GCAP", "Global Combat Air Programme",
            "FCAS", "SCAF", "未来空战系统",
            "TEMPEST", "暴风雨",
            "六代机欧洲",
            # ── Russian fighters (moved from DW) ──
            "Su-27", "Su-30", "Su-34", "Su-35", "Su-57",
            "MiG-29", "MiG-31", "MiG-35",
            "俄罗斯战机", "Russian fighter",
            # ── Indian fighter programs (moved from DW) ──
            "Su-30MKI", "Rafale India", "Tejas",
            "AMCA", "印度五代机",
            "印度六代机",
            # ── Japan/Korea fighters (moved from DW) ──
            "F-15J", "F-2", "日本战机",
            "日本六代机",
            "KF-21", "韩国战机", "韩国五代机",
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
    rss_sources={},  # Unified in data/rss_sources_all.json

    llm_filter_prompt=_FILTER_AAM,
    translation_prompt=_TRANSLATE_AAM,
    briefing_subject="空空导弹与空战平台周报 - {date_range}",
    briefing_prompt="""You are a technical defense analyst. Produce a weekly briefing in Chinese (中文) covering news articles about air-to-air missile (AAM) technology, fighter aircraft and UAVs, and hypersonic weapons.

Format the briefing with these sections:
1. **本周概述 (Weekly Overview)**: 1-2 paragraph summary of the week's major developments in AAM technology, fighter/UAV developments, and hypersonic weapons
2. **关键动态 (Key Developments)**: Bullet points of the most important stories with technical analysis
3. **详细摘要 (Detailed Summaries)**: For each article, provide:
   - 标题 (Chinese)
   - 来源 | 日期
   - 要点 (2-3 sentences focusing on the defense technology aspects)
   - 原文链接
4. **趋势观察 (Trends & Analysis)**: Notable patterns, emerging technologies, and strategic developments

Articles:""",

    monthly_report_prompt="""You are a senior defense technology researcher writing a professional monthly technical research survey in Chinese (\u4e2d\u6587). The report covers air-to-air missile (AAM) technology, fighter aircraft and UAVs, and hypersonic weapons.

CORE REQUIREMENTS:
- Write a flowing, integrated analysis. Do NOT split sections into "\u9886\u57df\u73b0\u72b6" + "\u672c\u6708\u8865\u5145". Combine domain knowledge with this month\'s news naturally.
- Every claim about this month\'s developments MUST cite the article number [N]. Domain knowledge from your training does not need citations.
- BE SPECIFIC: name missile designations (AIM-120D, PL-15, Meteor, AIM-260, etc.), weapon systems (J-20, F-35, NGAD, etc.), technical parameters, programs, countries, companies.
- Focus on HARDWARE, PROGRAMS, SENSORS, PROPULSION, STRATEGY. Do NOT explain basic concepts. Assume the reader is a defense professional.
- Show deep domain knowledge: know the global AAM landscape (US/EU/CN/RU/emerging programs), fighter/UAV programs worldwide, hypersonic weapons programs, fielded system performance, current technology frontiers.
- Write naturally. Each section should be a coherent narrative, not a bullet list or template.
- Total length: 2000-4000 Chinese characters.

## Suggested Structure (adapt as needed \u2014 combine or split based on content):

# {year}\u5e74{month}\u6708\u7a7a\u7a7a\u5bfc\u5f39\u4e0e\u7a7a\u6218\u5e73\u53f0\u7814\u7a76\u8fdb\u5c55\u7efc\u8ff0

## \u6458\u8981
~300\u5b57\u9ad8\u5ea6\u6982\u62ec\u672c\u6708\u6838\u5fc3\u52a8\u6001\u548c\u6280\u672f\u683c\u5c40\u3002\u5305\u542b\u81f3\u5c115\u4e2a\u5177\u4f53\u578b\u53f7\u548c\u6570\u636e\u70b9\u3002

## 1. \u5f15\u8a00
\u6982\u8ff0\u5f53\u524d\u7a7a\u6218\u6280\u672f\u683c\u5c40\u548c\u672c\u6708\u503c\u5f97\u5173\u6ce8\u7684\u52a8\u6001\u3002

## 2. \u7a7a\u7a7a\u5bfc\u5f39\u6280\u672f
\u7efc\u5408\u5206\u6790\u8fdc\u7a0b\u5316\uff08AIM-260/PL-17/Meteor\u5c04\u7a0b150-300km\uff09\u3001\u5c0f\u578b\u5316\u5185\u57cb\u5316\u3001\u5bfc\u5f15\u5934\u6280\u672f\u3001\u53cc\u8109\u51b2/\u51b2\u538b\u63a8\u8fdb\u3001\u5236\u5bfc\u63a7\u5236\u7b49\u65b9\u5411\u7684\u6700\u65b0\u8fdb\u5c55\u3002

## 3. \u6218\u6597\u673a\u4e0e\u65e0\u4eba\u673a
\u7efc\u5408\u5206\u6790\u5168\u7403\u6218\u6597\u673a\u9879\u76ee\uff08\u516d\u4ee3\u673aNGAD/GCAP/FCAS\u3001F-35\u3001\u6b7c-20/\u6b7c-35\u3001Su-57\u7b49\uff09\u548c\u519b\u7528\u65e0\u4eba\u673a\uff08CCA\u3001\u653b\u51fb-11\u3001MQ-9\u7b49\uff09\u7684\u53d1\u5c55\u52a8\u6001\u3002

## 4. \u9ad8\u8d85\u97f3\u901f\u6b66\u5668
\u7efc\u5408\u5206\u6790\u5168\u7403\u9ad8\u8d85\u97f3\u901f\u5bfc\u5f39\u9879\u76ee\uff08ARRW\u3001HACM\u3001LRHW\u3001\u9506\u77f3\u7b49\uff09\u3001\u9ad8\u8d85\u97f3\u901f\u9632\u5fa1\u6280\u672f\u53ca\u76f8\u5173\u8bd5\u9a8c\u52a8\u6001\u3002

## 5. \u9879\u76ee\u52a8\u6001\u4e0e\u8d8b\u52bf
\u7efc\u5408\u5206\u6790\u5168\u7403AAM\u9879\u76ee\u3001\u6218\u6597\u673a/UAV\u9879\u76ee\u91c7\u529e\u3001\u5408\u540c\u3001\u56fd\u9645\u5408\u4f5c\u4e0e\u6280\u672f\u53d1\u5c55\u8d8b\u52bf\u3002

## 6. \u6280\u672f\u6311\u6218\u4e0e\u53d1\u5c55\u8d8b\u52bf
\u6307\u51fa\u5f53\u524d\u9762\u4e34\u7684\u5173\u952e\u74f6\u9888\u3001\u672a\u67653-5\u5e74\u7684\u6838\u5fc3\u6280\u672f\u65b9\u5411\u3002

## \u53c2\u8003\u6587\u732e
[1] \u6807\u9898, \u6765\u6e90, \u65e5\u671f
[2] \u6807\u9898, \u6765\u6e90, \u65e5\u671f
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

DW = MonitorTheme(
    name="dw",
    app_name="Defense Watch Monitor",
    app_name_cn="防务观察采集系统",
    app_subtitle="大国防务 · 武器系统 · 军事战略 · 国防情报",
    logger_name="dw-monitor",
    db_name="dw",
    has_event_grouping=True,
    stats_title="防务观察采集系统",
    fallback_briefing_title="# 防务观察周报",

    keywords={
        "china_military_power": [
            "中国人民解放军", "解放军", "PLA", "People's Liberation Army",
            "中国军队", "中国军事", "中国国防",
            "Chinese military", "Chinese armed forces",
            "中国军力", "军力建设", "国防现代化",
            "国防预算", "defense budget China",
            "军事改革", "军事现代化",
            "China defense", "China national defense",
            "军民融合", "military-civil fusion", "MCF",
            "十五五", "15th Five-Year Plan&&military",
            "军事战略", "军事政策", "积极防御",
            "国防白皮书", "国防政策",
            "军委", "中央军委",
            "战区", "东部战区", "南部战区", "西部战区", "北部战区", "中部战区",
            "火箭军", "PLARF", "战略支援部队",
            "军事训练", "实战化训练",
            "联合作战", "joint operations China",
            "军队改革", "国防动员",
            "军事外交", "中外联演",
            "政治建军", "依法治军", "从严治军",
            "国防科技创新",
        ],
        "china_weapons_naval": [
            "福建舰", "山东舰", "辽宁舰", "航母",
            "aircraft carrier China", "Chinese carrier",
            "歼-35", "J-35",
            "空警-600", "KJ-600",
            "电磁弹射", "electromagnetic catapult",
            "舰载机", "carrier-based aircraft",
            "055型", "055驱逐舰", "Type 055", "万吨大驱",
            "052D", "052DL", "Type 052D",
            "054A", "054B", "Type 054B",
            "075型", "076型", "四川舰", "两栖攻击舰",
            "amphibious assault ship China",
            "中国海军", "PLAN", "People's Liberation Army Navy",
            "Chinese Navy", "中国舰船", "军舰",
            "护卫舰", "驱逐舰", "frigate", "destroyer",
            "核潜艇", "submarine China", "093B", "094", "096",
            "041型", "039型", "潜艇",
            "中国航母编队", "carrier strike group China",
            "海警", "coast guard China",
            "舷号", "入列", "服役",
            "中国造船", "shipbuilding China",
            "无人舰艇", "USV China",
        ],
        "china_weapons_air": [
            "运-20", "Y-20", "运油-20", "YY-20",
            "空警-500", "空警-2000",
            "轰-6", "H-6", "轰-20", "H-20", "JH-XX",
            "中国空军", "PLAAF", "People's Liberation Army Air Force",
            "Chinese Air Force", "中国空天",
            "预警机", "AWACS China",
            "电子战飞机", "electronic warfare China",
            "空中加油", "aerial refueling China",
            "中国航空工业", "航空工业集团",
        ],
        "china_weapons_missile": [
            "东风导弹", "DF-", "东风-",
            "长剑", "CJ-10", "CJ-100",
            "中国导弹", "Chinese missile",
            "弹道导弹", "ballistic missile China",
            "巡航导弹", "cruise missile China",
            "反舰导弹", "anti-ship missile China",
            "高超音速导弹", "hypersonic missile China",
            "中国高超音速", "Chinese hypersonic",
            "鹰击", "YJ-", "YJ-18", "YJ-21", "YJ-83", "YJ-62",
            "红旗", "HQ-", "HQ-9", "HQ-16", "HQ-19", "HQ-22", "HQ-29",
            "中国防空", "Chinese air defense",
            "反导系统", "Chinese missile defense",
            "反卫星", "ASAT China",
            "火箭军", "PLA Rocket Force",
            "中程导弹", "短程导弹", "洲际导弹",
            "巨浪", "JL-2", "JL-3",
            "中国火箭军",
            "反辐射导弹", "anti-radiation missile China",
            "Chinese missile arsenal",
            "China&&missile", "Chinese&&missile&&program",
            "PLA&&missile", "PRC&&missile",
        ],
        "china_weapons_ground": [
            "中国陆军", "PLAGF", "Chinese Army",
            "坦克", "tank China",
            "一百式", "轻型坦克",
            "装甲车", "armored vehicle China",
            "自行火炮", "self-propelled howitzer China",
            "火箭炮", "Chinese rocket artillery",
            "远程火箭炮", "multiple launch rocket China",
            "野战防空", "field air defense China",
            "反坦克导弹", "anti-tank missile China",
            "单兵装备", "individual equipment China",
            "无人车", "UGV China", "机器狗",
            "陆战", "地面作战",
        ],
        "china_strategy_doctrine": [
            "中国战略", "Chinese strategy",
            "国防战略", "defense strategy China",
            "积极防御", "active defense",
            "反介入/区域拒止", "A2/AD", "anti-access area denial",
            "区域拒止", "反介入",
            "近海防御", "远海护卫",
            "远洋作战", "blue water navy China",
            "突破岛链", "first island chain",
            "台湾", "Taiwan&&military", "台海&&军事",
            "南海&&军事", "South China Sea&&military",
            "东海&&军事", "East China Sea&&military",
            "印太战略", "Indo-Pacific China",
            "一带一路&&军事", "Belt and Road&&military",
            "海外基地", "overseas base China",
            "军事存在", "military presence",
            "战略威慑", "strategic deterrence China",
            "核政策", "nuclear policy China",
            "核威慑", "nuclear deterrence China",
            "军控", "arms control China",
            "军事透明度",
            "战略博弈", "大国竞争",
            "多域战", "all-domain warfare",
            "智能化战争", "intelligentized warfare",
            "无人化作战", "unmanned warfare China",
            "新域新质", "new domain new quality",
            "太空军事", "space military China",
            "网络战", "cyber warfare China",
            "认知战", "cognitive warfare",
            "混合战争", "hybrid warfare",
            "兵力运用", "军事力量运用",
            "2027", "建军百年",
            "中国外交&&军事",
            "白皮书&&军事",
            "经略海洋", "海洋强国",
            "全球安全倡议", "global security initiative",
            # ── Space warfare / counterspace ──
            "counterspace", "space warfare", "太空战",
            "anti-satellite weapon", "ASAT", "反卫星武器",
            "space control", "orbital warfare",
            "space-based intercept", "天基拦截",
            "direct ascent ASAT", "共轨反卫",
            "太空军事化", "militarization of space",
            "GPS warfare", "导航战",
            # ── Cyber warfare ──
            "cyber command", "cyber operations",
            "offensive cyber", "网络战", "网络攻击",
            "military cyber", "cyber defense military",
            "网络作战", "网络空间军事",
            # ── Critical minerals for defense ──
            "rare earth defense", "稀土军事",
            "critical mineral supply chain", "国防稀土",
            "弹药稀土", "关键矿产&&国防",
        ],
        "china_intel_assessment": [
            "中国军力报告", "Pentagon China report",
            "五角大楼&&中国",
            "Chinese military power report",
            "中国威胁论", "China threat",
            "China defense intelligence",
            "中国军事实力评估",
            "中国武器库", "Chinese weapons arsenal",
            "PLA capabilities",
            "China military assessment",
            "China modernization&&military",
            "China strategic intent",
            "PLA weakness", "Chinese military weakness",
            "中国军事能力",
            "中外军力对比",
            "军力对比", "军事对比",
            "U.S.&&China&&military&&comparison",
            "美中军事", "中美军力",
            "日本&&中国&&军事", "日美&&中国&&军事",
            "印太&&中国&&军事",
            "PLA reform progress",
            "Chinese defense industry",
            "中国军工", "中国国防工业",
            "中国军事技术", "Chinese military technology",
            "技术转让&&军事",
            "中国间谍", "Chinese espionage",
            "知识产权&&军事",
            "中国留学生&&军事",
            "中国产能&&军事", "military production China",
            "弹药产能", "shell production China",
            "中国物流", "military logistics China",
            "中国核力量", "China nuclear forces", "Chinese ICBM",
            "PLA Rocket Force", "火箭军现代化",
            "中国军事演习", "PLA exercise", "环太平洋&&中国",
            "军事供应链", "supply chain&&military China",
            "military innovation China",
            "中国太空站&&军事", "Chinese ASAT", "反卫星试验",
            "AI&&military China",
        ],
        "us_military": [
            # US military power & modernization
            "US military", "United States military", "U.S. armed forces",
            "US defense", "Pentagon", "Department of Defense",
            "US defense budget", "defense spending US",
            "US military modernization", "US force posture",
            "US military exercise", "US military operation",
            "US military deployment", "overseas basing US",
            "美国军事", "美国国防", "美军", "五角大楼",
            "美国国防预算", "美军现代化",
            "美军部署", "美军演习",
            # US Air Force
            "US Air Force", "USAF", "美国空军",
            "B-2", "B-21", "B-52", "B-1",
            "KC-46", "KC-135", "C-17", "C-130",
            "E-3", "E-7", "E-8", "RC-135",
            "隐身轰炸机", "stealth bomber US",
            # US Navy
            "US Navy", "USN", "美国海军",
            "aircraft carrier US", "carrier strike group",
            "Nimitz", "Ford-class", "Gerald R. Ford",
            "Arleigh Burke", "Zumwalt", "Constellation-class",
            "Virginia-class", "Columbia-class", "Los Angeles-class",
            "Seawolf-class", "Ohio-class",
            "amphibious assault ship US", "America-class",
            "naval exercise US",
            "美国航母", "美国海军舰艇",
            # US Army & Marine Corps
            "US Army", "美国陆军",
            "US Marine Corps", "USMC", "美国海军陆战队",
            "Army modernization", "美国陆军现代化",
            "M1 Abrams", "Bradley", "Stryker", "AMPV",
            "HIMARS", "Patriot", "THAAD",
            "long-range precision fires",
            "美国陆军装备",
            # US Space Force
            "US Space Force", "美国太空军",
            "Space Force", "space-based missile warning",
            "GPS modernization", "太空军",
            # US weapons programs
            "LRHW", "Dark Eagle", "远程高超音速武器",
            "C-HGB", "hypersonic weapon US",
            "PRSM", "ATACMS", "JASSM", "LRASM",
            "NSM", " Naval Strike Missile",
            "standard missile", "SM-6", "SM-3",
            "Aegis", "宙斯盾",
            "美军导弹", "美国高超音速",
            # US defense industry
            "Lockheed Martin", "Northrop Grumman", "Boeing defense",
            "Raytheon", "L3Harris", "General Dynamics",
            "美国军工", "美国国防工业",
            # ── New US weapons programs ──
            "Iron Dome for America", "Golden Dome",
            "PrSM", "precision strike missile",
            "Typhon missile", "Typhon launcher",
            "Mid-Band Capability", "MBC",
            "Lower Tier Air Defense", "LTAMD",
            "PATRIOT&&最新", "PAC-3 MSE",
            "THAAD", "萨德",
            "AIM-174B",
        ],
        "russian_military": [
            # Russian military
            "Russian military", "Russian armed forces", "Russia defense",
            "Russian defense budget", "Russian military modernization",
            "俄罗斯军事", "俄罗斯国防", "俄军",
            "俄罗斯军队", "俄罗斯武装力量",
            "俄罗斯国防预算", "俄军现代化",
            # Russian nuclear forces
            "Russia nuclear", "Russian nuclear forces",
            "Russian ICBM", "Russian strategic forces",
            "萨尔马特", "RS-28", "Sarmat",
            "亚尔斯", "Yars", "白杨", "Topol",
            "布拉瓦", "Bulava", "北风之神", "Borei-class",
            "核潜艇俄罗斯", "战略核潜艇",
            "俄罗斯核力量",
            # Russian Air Force
            "Russian Air Force", "Russian Aerospace Forces",
            "Tu-95", "Tu-160", "Tu-22",
            "A-50", "A-100",
            "俄罗斯空军", "俄罗斯战机",
            # Russian Navy
            "Russian Navy", "Russian fleet",
            "俄罗斯海军", "俄罗斯舰队",
            "Russian submarine", "俄罗斯潜艇",
            "护卫舰俄罗斯", "frigate Russia",
            # Russian missile programs
            "Russian missile", "俄罗斯导弹",
            "俄罗斯高超音速", "Russian hypersonic",
            "锆石", "Zircon", "Tsirkon",
            "匕首", "Kinzhal",
            "先锋", "Avangard",
            "口径", "Kalibr",
            "伊斯坎德尔", "Iskander",
            # Russian defense industry
            "俄罗斯军工", "俄罗斯国防工业",
            "Russian defense industry",
            # Ukraine war military aspects
            "Ukraine&&military", "Ukraine&&weapons",
            "乌克兰&&军事", "乌克兰&&武器",
        ],
        "europe_defense": [
            # European defense general
            "European defense", "EU defense", "European security",
            "NATO", "北约", "NATO capability",
            "欧洲防务", "欧洲安全",
            "欧洲国防预算", "European defense spending",
            # European missile systems
            "MBDA", "欧洲导弹",
            "Meteor missile", "流星空空导弹",
            "CAMM", "Sea Ceptor",
            "ASTER", "紫菀",
            "欧洲防空", "European air defense",
            # European military
            "European army", "European military modernization",
            "French military", "法国军事",
            "German military", "德国军事",
            "British military", "UK defense", "英国国防",
            "Italian defense", "意大利国防",
            "Spanish defense", "西班牙国防",
            "Swedish defense", "瑞典国防",
            "Polish military", "波兰军事",
            "法国国防", "德国国防",
            "英国军事", "英国国防",
            # European defense industry
            "BAE Systems", "Airbus Defence",
            "Thales", "Leonardo", "SAAB",
            "Rheinmetall", "KNDS", "Nexter",
            "欧洲军工",
            # European naval
            "欧洲海军", "European naval",
            "Queen Elizabeth-class", "法国航母",
            "P-8 Poseidon", "波塞冬",
        ],
        "india_military": [
            # Indian military general
            "Indian military", "Indian armed forces", "India defense",
            "印度军事", "印度国防", "印度军队",
            "印度国防预算", "India defense budget",
            # Indian Navy
            "Indian Navy", "印度海军",
            "印度航母", "INS Vikrant", "INS Vikramaditya",
            "Indian submarine", "印度潜艇",
            "Indian destroyer", "印度驱逐舰",
            "印度海军舰艇",
            # Indian missile programs
            "Indian missile", "印度导弹",
            "Agni", "烈火导弹",
            "Brahmos", "布拉莫斯",
            "印度高超音速", "Indian hypersonic",
            "Indian ballistic missile",
            "Indian cruise missile",
            "印度反导", "Indian missile defense",
            # Indian defense industry
            "印度军工", "印度国防工业",
            "DRDO", "HAL",
            "India defense procurement",
        ],
        "japan_korea_military": [
            # Japan military
            "Japan military", "Japan Self-Defense Force", "JSDF",
            "日本军事", "日本国防", "日本自卫队",
            "日本防卫预算", "Japan defense budget",
            "日本军力", "日本军事现代化",
            "Japanese Air Force", "日本空军",
            "Japanese Navy", "日本海军",
            "日本驱逐舰", "日本潜艇",
            "日本航母", "helicopter destroyer",
            "Japanese missile", "日本导弹",
            "日本高超音速", "Japanese hypersonic",
            "日本军工", "日本国防工业",
            "美日军事", "Japan-US alliance",
            # South Korea military
            "South Korea military", "ROK military", "Korean defense",
            "韩国军事", "韩国国防", "韩国军队",
            "韩国军力", "韩国军事现代化",
            "Korean Air Force", "韩国空军",
            "Korean Navy", "韩国海军",
            "韩国驱逐舰", "韩国潜艇",
            "Korean missile", "韩国导弹",
            "韩国高超音速",
            "韩国军工", "韩国国防工业",
            "韩美军事", "ROK-US alliance",
            # Australia military
            "Australia military", "Australian defence",
            "澳大利亚军事", "澳大利亚国防",
            "Australian defense",
            "澳大利亚军力",
            "Australian Navy", "澳大利亚海军",
            "Australian submarine", "AUKUS",
            "澳英美", "澳大利亚潜艇",
            "Australian Air Force", "澳大利亚空军",
            "澳大利亚导弹",
            "美澳军事", "Australia-US alliance",
            # ── AUKUS & expanded Australia ──
            "AUKUS Pillar 2", "AUKUS pillar 2",
            "AUKUS defense", "AUKUS security",
            "Australian defense budget", "澳大利亚国防预算",
            "澳大利亚国防军", "ADF",
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
    rss_sources={},

    llm_filter_prompt=_FILTER_DW,
    translation_prompt=_TRANSLATE_DW,
    briefing_subject="防务观察周报 - {date_range}",
    briefing_prompt="""You are a global defense intelligence analyst. Produce a weekly briefing in Chinese (中文) covering news articles about military power, weapons systems, strategy, and defense intelligence of major military powers (US, China, Russia, Europe, India, Japan, Korea, etc.).

Format the briefing with these sections:
1. **本周概述 (Weekly Overview)**: 1-2 paragraph summary of the week's major developments in global defense and military affairs
2. **关键动态 (Key Developments)**: Bullet points of the most important stories with analysis
3. **详细摘要 (Detailed Summaries)**: For each article, provide:
   - 标题 (Chinese)
   - 来源 | 日期
   - 要点 (2-3 sentences focusing on the defense technology or intelligence aspects)
   - 原文链接
4. **趋势观察 (Trends & Analysis)**: Notable patterns, emerging technologies, and strategic developments

Articles:""",

    monthly_report_prompt="""You are a senior global defense intelligence analyst writing a professional monthly research survey in Chinese (中文). The report covers military modernization, weapon systems development, military strategy, and defense intelligence assessments across major military powers.

CORE REQUIREMENTS:
- Write a flowing, integrated analysis covering US, China, Russia, Europe, India, and Indo-Pacific defense developments.
- Every claim about this month's developments MUST cite the article number [N].
- BE SPECIFIC: name weapon systems, programs, technical parameters.
- Focus on HARDWARE, PROGRAMS, SENSORS, STRATEGY.
- Write naturally. Each section should be a coherent narrative.
- Total length: 3000-5000 Chinese characters.

## Suggested Structure (adapt as needed):

# {year}年{month}月防务观察研究进展综述

## 摘要
~300字高度概括本月核心动态。

## 1. 引言
概述当前全球防务格局和本月值得关注的动态。

## 2. 美国军力与武器发展
美军现代化、武器项目、国防预算、军事战略调整等。

## 3. 中国军力与武器发展
综合分析海军、空军、导弹武器、陆军装备的最新进展及军事战略。

## 4. 俄罗斯/欧洲/印太防务动态
俄罗斯军事现代化、欧洲防务合作、印度/日本/韩国/澳大利亚军事发展。

## 5. 国防工业与技术
军工产能、技术创新、防务科技、全球军贸等。

## 6. 外部评估与情报分析
各国防务报告、军事能力评估、力量对比分析等。

## 7. 技术挑战与发展趋势
关键瓶颈、未来发展方向。

## 参考文献
[1] 标题, 来源, 日期

Articles to review:""",

    dashboard_port=8080,
    dashboard_title="防务观察采集系统",
    dashboard_other_theme_name="空空导弹",
    dashboard_other_theme_url="http://47.103.207.227:8080",
    dashboard_other_theme_color="#fb923c",
    dashboard_other_theme_color_rgb="251,146,160",

    dashboard_color_primary="#22c55e",
    dashboard_color_primary_rgb="34,197,94",
    dashboard_header_bg="linear-gradient(135deg,#0d2818,#0a1a10)",
    dashboard_header_border="#1a4a2e",
    dashboard_header_bg_light="#0d2818",
    dashboard_event_header_bg="linear-gradient(135deg,#0d2818,#0a1a10)",
    dashboard_event_border="#1a4a2e",
    dashboard_source_tag_domestic_bg="#0d2818",
    dashboard_source_tag_domestic_color="#22c55e",

    telegram_msg_cjk="🏛️ 防务观察推送",
    telegram_msg_en="🏛️ Defense Watch Alert",
    email_html_prefix="🏛️ Defense Watch",
    email_subject_prefix="🏛️ [防务观察]",
    notification_prefix="🏛️",
)


_THEME_CACHE: Optional[MonitorTheme] = None
_THEME_MAP = {"news": NEWS, "aam": AAM, "dw": DW}


def get_theme() -> MonitorTheme:
    """Get the active theme based on MONITOR_THEME env var (default: 'news')."""
    global _THEME_CACHE
    if _THEME_CACHE is None:
        name = os.environ.get("MONITOR_THEME", "news").lower()
        _THEME_CACHE = _THEME_MAP.get(name, NEWS)
    return _THEME_CACHE
