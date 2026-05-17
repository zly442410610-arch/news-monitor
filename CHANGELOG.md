# Changelog

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
