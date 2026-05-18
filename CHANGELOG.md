# Changelog

## v0.5.0 (2026-05-19)

### Added
- 自建 RSSHub 实例 (Docker, localhost:1200)
- 切换 21 个 RSSHub 源至自建实例，延迟更低更稳定
- 新增 15+ RSS 源：Springer 系列期刊、Combustion Sci & Tech、Propulsion & Power Research、
  ESA Space Engineering、Lockheed Martin、Shephard Media、Janes、Breaking Defense、
  National Defense Mag、The Defense Post、TASS Defense、SpaceWatch Global 等
- 新增中文源：中国新闻网、参考消息、知乎想法日报、知乎每周精选、环球网军事、
  BBC中文、央视新闻
- 新增学术源：AIAA J. Spacecraft & Rockets、Chinese J. Aeronautics、Defence Technology
- Hacker News (tech/engineering discussions)

### Removed
- 清理 16 个不可用的 RSSHub 源（知乎话题、新浪/凤凰/澎湃/网易/腾讯/搜狐军事等）

### Fixed
- Dashboard theme-badge 颜色从硬编码修复为使用 config.COLOR_PRIMARY 变量

## v0.2.0 (2026-05-18)

### Added
- arXiv academic paper sources: 3 keyword-based Atom feeds for solid rocket, ramjet/scramjet, and hypersonic propulsion papers
- CNKI Chinese academic journal sources: 5 core journals (推进技术, 固体火箭技术, 宇航学报, 航空动力学报, 火箭推进)
- Chinese news sources: 联合早报 中国/国际 feeds
- Article detail page: click title to view full translated content with collapsible original summary
- Patent search function in collector.py for Google Patents
- 4 new international RSS sources (European Spaceflight, JAXA, Universe Today, Space.com)
- 3 additional technical/defense sources (Ars Technica, The War Zone, Interesting Engineering)
- Chinese time format on article cards (年月日 时分秒)
- Expanded keyword list from 66 to 77 terms
- Relaxed LLM filter to accept missile/hypersonic propulsion content

### Changed
- Dashboard: dark theme redesign with stats bar, filter tabs, source type classification
- Dashboard: title links now point to article detail page instead of original URL
- POLL_INTERVAL changed from 120min to 1440min (daily), cron set for 9am
- Database schema includes translated fields (translated_title, translated_summary)

### Fixed
- LLM filter handling of thinking blocks (Anthropic API)
- Translation parsing for flexible response headers
- Dashboard column index off-by-one for translated fields
- Date format to Chinese locale

## v0.1.0 (2026-05-16)

### Added
- Initial aerospace news monitoring system
- International RSS sources (Defense News, Spaceflight Now, NASA, etc.)
- Two-tier filtering: keyword matching + LLM semantic filter (Claude Sonnet)
- English-to-Chinese translation via Anthropic API
- SQLite database with WAL mode
- Web dashboard with dark theme (BaseHTTPRequestHandler)
- Telegram and email notification support
- Weekly briefing generator
- CLI entry point (poll, serve, daemon, briefing, stats)
- Domestic collector script for Chinese news sources
