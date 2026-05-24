"""CSS and HTML rendering functions for the unified dashboard."""
import html
import re
import urllib.parse
from datetime import datetime, timezone


def _safe_href(url: str) -> str:
    """Return url only if it's a safe http/https link (prevents javascript: XSS)."""
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return ""
        if "news.google.com" in parsed.netloc:
            from monitor import decode_google_news_url
            decoded = decode_google_news_url(url)
            if decoded != url:
                return decoded
            return ""
        return url
    except Exception:
        pass
    return ""

from theme import AAM, NEWS, MonitorTheme

# ── Date formatting ────────────────────────────────────────────────────

RSS_DATE_PATTERNS = [
    "%a, %d %b %Y %H:%M:%S %z",
    "%a, %d %b %Y %H:%M:%S %Z",
    "%d %b %Y %H:%M:%S %z",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%d",
]


def format_time_cn(date_str: str) -> str:
    if not date_str:
        return "?"
    text = date_str.strip()
    # Try fromisoformat first (covers ISO 8601, 90%+ of cases)
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.strftime("%Y年%m月%d日 %H:%M:%S")
    except (ValueError, TypeError):
        pass
    for pattern in RSS_DATE_PATTERNS:
        try:
            dt = datetime.strptime(text, pattern)
            if dt.tzinfo:
                dt = dt.astimezone(timezone.utc)
            return dt.strftime("%Y年%m月%d日 %H:%M:%S")
        except ValueError:
            continue
    return text[:10]


# ── CSS ────────────────────────────────────────────────────────────────

_css_cache: dict[str, str] = {}


def get_css(t: MonitorTheme) -> str:
    key = t.app_name_cn
    if key not in _css_cache:
        _css_cache[key] = f"""
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:'Noto Sans CJK SC','PingFang SC','Microsoft YaHei','WenQuanYi Micro Hei',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
       background:#1a2332; color:#e2e8f0; min-height:100vh; }}

/* Header */
.header {{ background:{t.dashboard_header_bg}; border-bottom:1px solid {t.dashboard_header_border};
          padding:1rem 2rem; }}
.header-top {{ display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:1rem; }}
.header h1 {{ font-size:1.3rem; color:{t.dashboard_color_primary}; letter-spacing:0.5px; }}
.header .subtitle {{ color:#64748b; font-size:0.8rem; margin-top:0.2rem; }}
.header-actions {{ display:flex; gap:0.5rem; flex-wrap:wrap; justify-content:flex-end; }}
.header-actions a, .header-actions a:visited {{ color:#94a3b8; font-size:0.82rem; text-decoration:none; padding:0.3rem 0.7rem;
                    border:1px solid #334155; border-radius:6px; transition:all 0.2s;
                    white-space:nowrap; }}
.header-actions a:hover {{ background:{t.dashboard_header_bg_light}; color:{t.dashboard_color_primary}; border-color:{t.dashboard_color_primary}; }}
.header-actions a.active, .header-actions a.active:visited {{ background:rgba({t.dashboard_color_primary_rgb},0.12); color:{t.dashboard_color_primary}; border-color:rgba({t.dashboard_color_primary_rgb},0.35); font-weight:600; }}
.header-actions .nav-group {{ display:inline-flex; gap:0.3rem; align-items:center; }}
/* Navigation tiers */
.header-nav {{ display:flex; align-items:center; gap:0.8rem; padding:0.5rem 2rem 0.75rem; flex-wrap:wrap; }}

.nav-primary {{ display:flex; gap:0.3rem; align-items:center; flex-wrap:wrap; }}
.nav-primary a {{ font-size:0.85rem; padding:0.35rem 1rem; border-radius:20px; font-weight:600;
                text-decoration:none; color:#94a3b8; border:1px solid transparent; transition:all 0.2s; }}
.nav-primary a:hover {{ color:#e2e8f0; background:rgba(255,255,255,0.05); }}
.nav-primary a.active {{ background:rgba({t.dashboard_color_primary_rgb},0.12); color:{t.dashboard_color_primary}; border-color:rgba({t.dashboard_color_primary_rgb},0.35); }}
.nav-divider {{ width:1px; height:18px; background:#3b4a5a; flex-shrink:0; margin:0 0.2rem; }}

/* Inline nav search */



/* Stats bar */
.stats-bar {{ display:flex; gap:1rem; padding:0.75rem 2rem; background:#1a2332;
             border-bottom:1px solid #2a3a4a; flex-wrap:wrap; }}
.stat-card {{ display:flex; align-items:center; gap:0.5rem; padding:0.4rem 0.8rem;
             background:#2a3a4a; border-radius:6px; border:1px solid #3b4a5a; }}
.stat-card .num {{ color:{t.dashboard_color_primary}; font-weight:700; font-size:1rem; }}
.stat-card .label {{ color:#64748b; font-size:0.75rem; }}
.stat-card .num.green {{ color:#22c55e; }}
.stat-card .num.purple {{ color:#a78bfa; }}
.stat-card .num.orange {{ color:#fb923c; }}

/* Search bar */
.search-bar {{ background:#1a2332; padding:0.75rem 2rem; border-bottom:1px solid #2a3a4a; }}
.search-bar form {{ display:flex; gap:0.5rem; max-width:500px; }}
.search-bar input {{ flex:1; padding:0.6rem 1rem; border:1px solid #3b4a5a; border-radius:8px;
                    background:#2a3a4a; color:#e2e8f0; font-size:0.9rem; }}
.search-bar input:focus {{ outline:none; border-color:{t.dashboard_color_primary}; }}
.search-bar button {{ padding:0.5rem 1.2rem; background:rgba({t.dashboard_color_primary_rgb},0.12); color:{t.dashboard_color_primary}; border:1px solid rgba({t.dashboard_color_primary_rgb},0.35);
                     border:none; border-radius:6px; font-weight:600; cursor:pointer; font-size:0.85rem; }}

.container {{ max-width:1000px; margin:0 auto; padding:1.5rem 2rem; }}

/* Article card */
.article {{ background:#243447; border:1px solid #3b4a5a; border-radius:10px;
           padding:1.2rem 1.5rem; margin-bottom:1rem; transition:all 0.2s;
           position:relative; overflow:hidden; }}
.article:hover {{ border-color:{t.dashboard_color_primary}; box-shadow:0 0 20px rgba({t.dashboard_color_primary_rgb},0.05); }}
.article .top-row {{ display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.4rem; }}
.article .source {{ font-size:0.78rem; color:#64748b; display:flex; align-items:center; gap:0.3rem; }}
.article .source-tag {{ font-size:0.65rem; padding:0.1rem 0.35rem; border-radius:3px; font-weight:600; }}
.article .source-tag.domestic {{ background:{t.dashboard_source_tag_domestic_bg}; color:{t.dashboard_source_tag_domestic_color}; }}
.article .source-tag.international {{ background:#3b1f3b; color:#c084fc; }}
.article .badge {{ display:inline-block; background:rgba({t.dashboard_color_primary_rgb},0.12); color:{t.dashboard_color_primary}; font-size:0.65rem;
                  font-weight:700; padding:0.1rem 0.35rem; border-radius:3px; vertical-align:middle; }}
.article .score {{ display:inline-flex; align-items:center; gap:0.2rem; font-size:0.75rem;
                  padding:0.15rem 0.5rem; border-radius:4px; font-weight:600; }}
.article .score.high {{ background:#166534; color:#86efac; }}
.article .score.med {{ background:#713f12; color:#fde047; }}
.article .score.low {{ background:#3b1111; color:#fca5a5; }}
.article .title {{ font-size:1.05rem; margin:0.4rem 0 0.2rem; line-height:1.5; }}
.article .title a {{ color:#e2e8f0; text-decoration:none; }}
.article .title a:hover {{ color:{t.dashboard_color_primary}; }}
.article .orig-title {{ font-size:0.78rem; color:#475569; margin-bottom:0.3rem; }}
.type-line {{ margin:0.3rem 0; }}
.article .kw {{ display:inline-block; background:#1e2e40; color:{t.dashboard_color_primary}; font-size:0.7rem;
               padding:0.15rem 0.5rem; border-radius:4px; margin-right:0.3rem; margin-top:0.3rem; }}
.article .summary {{ color:#94a3b8; font-size:0.88rem; line-height:1.6; margin:0.5rem 0; }}
.article .actions {{ margin-top:0.6rem; display:flex; gap:0.5rem; }}
.article .actions button, .article .actions a {{
  font-size:0.78rem; padding:0.3rem 0.8rem; border-radius:5px; cursor:pointer; text-decoration:none; }}
.article .actions button {{ background:transparent; border:1px solid #475569; color:#94a3b8; }}
.article .actions button:hover {{ background:#334155; color:#e2e8f0; }}
.article .actions a {{ background:transparent; border:1px solid #475569; color:#94a3b8; }}
.article .actions a:hover {{ background:#334155; color:{t.dashboard_color_primary}; }}
.article .translated-tag {{ display:inline-block; background:{t.dashboard_source_tag_domestic_bg}; color:{t.dashboard_source_tag_domestic_color}; font-size:0.65rem;
                           padding:0.1rem 0.35rem; border-radius:3px; }}
.article-body {{ display:flex; gap:1rem; align-items:flex-start; }}
.article-thumb {{ width:120px; height:80px; object-fit:cover; border-radius:6px; flex-shrink:0;
                 margin-top:0.3rem; background:#1e2e40; border:1px solid #3b4a5a; }}
.article .author-line {{ font-size:0.78rem; color:#94a3b8; margin:0.2rem 0; }}
.article .affiliation {{ color:#64748b; font-size:0.72rem; }}
.type-tag {{ font-size:0.75rem; padding:0.2rem 0.6rem; border-radius:5px; font-weight:700; vertical-align:middle; letter-spacing:0.5px; }}
.type-tag.paper {{ background:#312e81; color:#a5b4fc; border:1px solid #4f46e5; }}
.type-tag.news {{ background:#14532d; color:#86efac; border:1px solid #16a34a; }}
.type-tag.patent {{ background:#3b1f3b; color:#c084fc; border:1px solid #9333ea; }}

/* Footer stat line */
.footer-stat {{ text-align:center; color:#64748b; font-size:0.78rem; padding:0.5rem 1rem 1.5rem; }}
.footer-stat a {{ color:{t.dashboard_color_primary}; text-decoration:none; }}
.footer-stat a:hover {{ text-decoration:underline; }}

/* Summary expand */
.summary.collapsed {{ overflow:hidden; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; }}
.expand-btn {{ background:none; border:none; color:{t.dashboard_color_primary}; font-size:0.78rem; cursor:pointer; padding:0; }}
.expand-btn:hover {{ text-decoration:underline; }}


/* Search highlight */
mark {{ background:#fde047; color:#0b1121; padding:0 2px; border-radius:2px; }}


/* Corner badge — linking to the other theme */
.theme-badge {{ position:fixed; top:12px; right:12px; z-index:999;
  display:flex; align-items:center; gap:4px;
  padding:4px 10px; border-radius:20px;
  font-size:0.75rem; font-weight:600; text-decoration:none;
  background:rgba(26,35,50,0.85); backdrop-filter:blur(4px);
  border:1px solid {t.dashboard_other_theme_color}; color:{t.dashboard_other_theme_color};
  transition:all 0.2s; }}
.theme-badge:hover {{ background:rgba({t.dashboard_other_theme_color_rgb},0.15); }}

/* Toast */
.toast {{ position:fixed; bottom:20px; left:50%; transform:translateX(-50%); background:#2a3a4a;
        color:#e2e8f0; padding:0.5rem 1.2rem; border-radius:8px; font-size:0.85rem;
        border:1px solid {t.dashboard_color_primary}; display:none; z-index:1000; }}

/* Sources page */
.sources-list {{ max-width:700px; margin:0 auto; padding:1rem 0; }}
.sources-list h2 {{ font-size:1.1rem; color:{t.dashboard_color_primary}; margin-bottom:1rem; }}
.source-item {{ display:flex; justify-content:space-between; align-items:center;
               padding:0.5rem 0.8rem; border-bottom:1px solid #2a3a4a; gap:0.5rem; }}
.source-item:hover {{ background:rgba(255,255,255,0.02); }}
.source-item .name {{ color:#94a3b8; font-size:0.85rem; flex-shrink:0; }}
.source-item .url {{ color:#475569; font-size:0.75rem; overflow:hidden; text-overflow:ellipsis;
                    white-space:nowrap; min-width:0; }}
.source-count {{ text-align:center; color:#64748b; font-size:0.82rem; padding:0.5rem 0 1rem; }}

/* Pagination */
.pagination {{ display:flex; justify-content:center; gap:0.5rem; margin:2rem 0; flex-wrap:wrap; }}
.pagination a {{ color:#94a3b8; text-decoration:none; padding:0.4rem 0.8rem;
                border:1px solid #3b4a5a; border-radius:6px; font-size:0.85rem; transition:all 0.2s; }}
.pagination a:hover {{ background:{t.dashboard_header_bg_light}; color:{t.dashboard_color_primary}; border-color:{t.dashboard_color_primary}; }}
.pagination a.active {{ background:rgba({t.dashboard_color_primary_rgb},0.12); color:{t.dashboard_color_primary}; border-color:rgba({t.dashboard_color_primary_rgb},0.35); font-weight:600; }}
.empty {{ text-align:center; color:#475569; padding:3rem 1rem; font-size:0.95rem; }}

/* Event group */
.event-group {{ margin-bottom:1.5rem; }}
.event-header {{ background:{t.dashboard_event_header_bg}; border:1px solid {t.dashboard_event_border};
                border-radius:8px; padding:0.6rem 1rem; margin-bottom:0.6rem;
                display:flex; align-items:center; justify-content:space-between; gap:0.5rem; flex-wrap:wrap; }}
.event-header .event-title {{ color:{t.dashboard_color_primary}; font-size:0.9rem; font-weight:600; }}
.event-header .event-count {{ color:#64748b; font-size:0.78rem; background:#2a3a4a;
                             padding:0.15rem 0.5rem; border-radius:4px; }}
.event-header .event-sources {{ color:#64748b; font-size:0.72rem; width:100%; }}
.event-group .article:last-child {{ margin-bottom:0; }}

/* Source status */
.source-status-ok {{ color:#22c55e; font-size:0.72rem; margin-left:0.5rem; flex-shrink:0; }}
.source-status-fail {{ color:#ef4444; font-size:0.72rem; margin-left:0.5rem; flex-shrink:0; }}
.source-status-na {{ color:#64748b; font-size:0.72rem; margin-left:0.5rem; flex-shrink:0; }}
.source-error {{ color:#ef4444; font-size:0.65rem; display:block; }}
.source-status-disabled {{ color:#6b7280; font-size:0.72rem; margin-left:0.5rem; flex-shrink:0; font-style:italic; }}

/* Archive nav */
.archive-nav {{ display:flex; align-items:center; gap:0.4rem; padding:0.75rem 0; flex-wrap:wrap; }}
.archive-nav a {{ color:#94a3b8; font-size:0.8rem; text-decoration:none; padding:0.25rem 0.6rem; border:1px solid #3b4a5a; border-radius:5px; transition:all 0.2s; }}
.archive-nav a:hover {{ border-color:{t.dashboard_color_primary}; color:{t.dashboard_color_primary}; }}
.archive-nav a.active {{ background:rgba({t.dashboard_color_primary_rgb},0.12); color:{t.dashboard_color_primary}; border-color:rgba({t.dashboard_color_primary_rgb},0.35); font-weight:600; }}
@media (max-width: 768px) {{
  .theme-badge {{ top:8px; right:8px; font-size:0.7rem; padding:3px 8px; }}
  .header {{ padding:0.75rem 1rem; }}
  .header h1 {{ font-size:1.1rem; }}
  .header-nav {{ padding:0.4rem 1rem 0.6rem; gap:0.5rem; }}
  .nav-primary a {{ font-size:0.78rem; padding:0.25rem 0.7rem; }}
  .stats-bar {{ padding:0.5rem 0.75rem; gap:0.5rem; }}
  .stat-card {{ padding:0.3rem 0.6rem; }}
  .stat-card .num {{ font-size:0.9rem; }}
  .stat-card .label {{ font-size:0.7rem; }}
  .search-bar {{ padding:0.5rem 0.75rem; }}
  .search-bar form {{ max-width:100%; }}
  .search-bar input {{ font-size:16px; padding:0.5rem 0.8rem; }}
  .container {{ padding:1rem 0.75rem; }}
  .article {{ padding:0.8rem 1rem; }}
  .article .top-row {{ flex-direction:column; align-items:flex-start; }}
  .article .title {{ font-size:0.95rem; }}
  .article-body {{ flex-direction:column; }}
  .article-thumb {{ width:100%; height:auto; max-height:180px; margin-top:0; }}
  .article .summary {{ font-size:0.82rem; }}
  .article .actions {{ flex-wrap:wrap; }}
  .article .actions button, .article .actions a {{
    font-size:0.75rem; padding:0.4rem 0.7rem; min-height:36px;
    display:flex; align-items:center; justify-content:center;
  }}
  .article .orig-title {{ font-size:0.72rem; }}
  .pagination {{ gap:0.3rem; }}
  .pagination a {{ padding:0.35rem 0.6rem; font-size:0.8rem; }}
  .event-header {{ padding:0.5rem 0.8rem; }}
  .event-header .event-title {{ font-size:0.82rem; }}
  .event-header .event-sources {{ font-size:0.68rem; }}
  .related-title-row a {{ font-size:0.82rem; }}
  .related-source {{ font-size:0.7rem; }}
  .related-title-row .type-tag {{ font-size:0.65rem; padding:0.05rem 0.4rem; }}
}}

@media (max-width: 480px) {{
  .header h1 {{ font-size:1rem; }}
  .header-top {{ flex-direction:column; align-items:flex-start; }}
  .header-nav {{ gap:0.4rem; justify-content:center; }}
  .stats-bar {{ justify-content:center; }}
  .container {{ padding:0.75rem 0.5rem; }}
  .article {{ padding:0.7rem 0.8rem; border-radius:8px; }}
  .article .source {{ font-size:0.72rem; flex-wrap:wrap; }}
  .article .title {{ font-size:0.9rem; }}
  .article .summary {{ font-size:0.8rem; }}
  .article .score {{ font-size:0.7rem; }}
  .article .kw {{ font-size:0.65rem; }}
  .article .actions button, .article .actions a {{ font-size:0.72rem; padding:0.35rem 0.6rem; }}
  .article .translated-tag {{ font-size:0.6rem; }}
  .pagination a {{ padding:0.3rem 0.5rem; font-size:0.75rem; }}
}}

/* Article content (detail page) */
.content-section {{ margin-top:2rem; padding-top:1.5rem; border-top:1px solid #334155; }}
.content-heading {{ color:#e2e8f0; font-size:1rem; margin-bottom:0.8rem; }}
.content-body {{ color:#d1d5db; font-size:1.05rem; line-height:1.9; white-space:pre-wrap; word-break:break-word; max-width:100%; overflow-wrap:break-word; }}
.content-body.original {{ color:#cbd5e1; }}
.content-body.translation {{ color:#d1d5db; }}
.content-body p {{ margin:0.6em 0; }}

/* Footer */
.footer-nav {{ text-align:center; padding:1.5rem 2rem; border-top:1px solid #2a3a4a; margin-top:2rem; }}
.footer-nav a {{ color:#64748b; font-size:0.8rem; text-decoration:none; padding:0.3rem 0.8rem; transition:color 0.2s; }}
.footer-nav a:hover {{ color:#38bdf8; }}
.footer-nav .sep {{ color:#3b4a5a; font-size:0.7rem; }}

/* Trend page */
.trend-header {{ display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.5rem; padding:1rem 0; }}
.trend-header h2 {{ margin:0; }}
.trend-controls {{ display:flex; gap:0.5rem; flex-wrap:wrap; align-items:center; }}
.trend-controls select, .trend-controls input {{
  padding:0.4rem 0.6rem; border:1px solid #3b4a5a; border-radius:6px;
  background:#243447; color:#e2e8f0; font-size:0.85rem;
}}
.trend-controls button {{
  padding:0.4rem 1rem; border:none; border-radius:6px;
  background:{t.dashboard_color_primary}; color:#0f172a;
  font-size:0.85rem; font-weight:600; cursor:pointer;
}}
.trend-days {{ display:flex; gap:0.3rem; }}
.trend-days a {{
  padding:0.3rem 0.7rem; border:1px solid #3b4a5a; border-radius:6px;
  color:#94a3b8; text-decoration:none; font-size:0.8rem;
}}
.trend-days a.active {{ background:{t.dashboard_color_primary}; color:#0f172a; border-color:{t.dashboard_color_primary}; }}
.trend-chart-box {{ background:#243447; border:1px solid #3b4a5a; border-radius:8px; padding:1rem; margin-bottom:1rem; }}
.trend-chart-box h3 {{ color:#e2e8f0; font-size:0.95rem; margin:0 0 0.5rem 0; }}
.trend-chart-box .trend-count {{ color:#64748b; font-size:0.8rem; margin-left:0.5rem; }}
.trend-empty {{ text-align:center; padding:2rem; color:#64748b; }}

/* Related articles (article detail) */
.related-section {{ margin-top:1.5rem; padding-top:1rem; border-top:1px solid #334155; }}
.related-item {{
  padding:0.5rem 0; border-bottom:1px solid #2a3a4a;
}}
.related-title-row {{
  display:flex; align-items:center; gap:0.4rem; margin-bottom:0.15rem;
}}
.related-title-row a {{
  color:{t.dashboard_color_primary}; text-decoration:none; font-size:0.9rem;
  word-break:break-word;
}}
.related-title-row a:hover {{ text-decoration:underline; }}
.related-title-row .type-tag {{ font-size:0.7rem; padding:0.1rem 0.5rem; flex-shrink:0; }}
.related-source {{ color:#64748b; font-size:0.75rem; display:block; }}

/* AI Q&A page */
.qa-form {{ display:flex; gap:0.5rem; margin-bottom:1.5rem; }}
.qa-form input[type="text"] {{
  flex:1; padding:0.7rem 1rem; border:1px solid #3b4a5a; border-radius:8px;
  background:#2a3a4a; color:#e2e8f0; font-size:1rem;
}}
.qa-form button {{
  padding:0.7rem 1.5rem; background:{t.dashboard_color_primary}; color:#0f172a;
  border:none; border-radius:8px; font-weight:600; cursor:pointer; font-size:0.95rem;
}}
.qa-meta {{ display:flex; gap:1rem; padding:0.5rem 0; color:#64748b; font-size:0.78rem; border-bottom:1px solid #2a3a4a; margin-bottom:1rem; }}
.qa-answer {{ background:#243447; border:1px solid #3b4a5a; border-radius:10px; padding:1.5rem; margin-bottom:1.5rem; }}
.qa-content {{ font-size:0.95rem; line-height:1.8; color:#cbd5e1; }}
.qa-content p {{ margin:0.6em 0; }}
.qa-content strong {{ color:#f1f5f9; }}
.qa-content code {{ background:rgba(255,255,255,0.08); padding:0.1rem 0.3rem; border-radius:3px; font-size:0.9rem; }}
.qa-cite a {{ color:{t.dashboard_color_primary}; text-decoration:none; font-weight:600; }}
.qa-cite a:hover {{ text-decoration:underline; }}
.qa-sources {{ background:#1e2e40; border:1px solid #2a3a4a; border-radius:8px; padding:1rem 1.5rem; }}
.qa-sources h3 {{ color:#e2e8f0; font-size:0.95rem; margin-bottom:0.8rem; }}
.qa-source-item {{ display:flex; align-items:center; gap:0.5rem; padding:0.4rem 0; border-bottom:1px solid #2a3a4a; }}
.qa-source-item:last-child {{ border-bottom:none; }}
.qa-source-index {{ color:{t.dashboard_color_primary}; font-weight:600; font-size:0.85rem; min-width:2rem; }}
.qa-source-item a {{ color:#e2e8f0; text-decoration:none; font-size:0.85rem; flex:1; }}
.qa-source-item a:hover {{ color:{t.dashboard_color_primary}; }}
.qa-source-name {{ color:#64748b; font-size:0.72rem; flex-shrink:0; }}
.qa-empty {{ color:#64748b; text-align:center; padding:2rem; }}
.qa-loading {{ text-align:center; padding:2rem; color:#64748b; }}"""

    return _css_cache[key]


# ── SVG Chart ────────────────────────────────────────────────────────────

def render_svg_bar_chart(data, bar_color="#38bdf8", width=800, height=300):
    """Render an SVG bar chart from daily {day, cnt} data. Zero external deps."""
    if not data:
        return '<div class="trend-empty">暂无数据</div>'
    max_val = max(d["cnt"] for d in data)
    if max_val == 0:
        return '<div class="trend-empty">所选时间范围内无数据</div>'

    pad = {"t": 20, "r": 20, "b": 50, "l": 50}
    cw = width - pad["l"] - pad["r"]
    ch = height - pad["t"] - pad["b"]
    n = len(data)
    bw = max(4, cw // n - 2)

    parts = [
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
        f'style="width:100%;max-width:{width}px;background:#1e2e40;border-radius:8px;">'
    ]
    # Grid lines
    for i in range(5):
        y = pad["t"] + ch - (ch * i // 4)
        val = max_val * i // 4
        parts.append(f'<line x1="{pad["l"]}" y1="{y}" x2="{width - pad["r"]}" y2="{y}" stroke="#2a3a4a" stroke-width="1"/>')
        parts.append(f'<text x="{pad["l"] - 8}" y="{y + 4}" text-anchor="end" fill="#64748b" font-size="11">{val}</text>')
    # Bars
    for idx, d in enumerate(data):
        bh = int(ch * d["cnt"] / max_val) if max_val > 0 else 0
        x = pad["l"] + idx * (bw + 2)
        y = pad["t"] + ch - bh
        parts.append(
            f'<rect x="{x}" y="{y}" width="{bw}" height="{max(bh, 1)}" '
            f'fill="{bar_color}" rx="2" opacity="0.85">'
            f'<title>{d["day"]}: {d["cnt"]}篇</title></rect>'
        )
        # X-axis label (show every Nth)
        interval = max(1, n // 20)
        if idx % interval == 0 or idx == n - 1:
            label = d["day"][-5:]
            angle = '-45' if n > 15 else '0'
            x_pos = x + bw // 2
            y_pos = height - 10 if n <= 15 else height - 5
            parts.append(
                f'<text x="{x_pos}" y="{y_pos}" text-anchor="end" '
                f'fill="#64748b" font-size="10" '
                f' transform="rotate({angle},{x_pos},{y_pos})">{label}</text>'
            )
    parts.append('</svg>')
    return '\n'.join(parts)


# ── Header & Footer ────────────────────────────────────────────────────

def render_footer(prefix: str = "") -> str:
    """Render page footer with bottom navigation links."""
    return f"""
<div class="footer-nav">
<a href="{prefix}/archive">归档</a>
<span class="sep">|</span>
<a href="{prefix}/poll-history">采集历史</a>
<span class="sep">|</span>
<a href="{prefix}/monthly-report">月度报告</a>
<span class="sep">|</span>
<a href="{prefix}/trends">关键词趋势</a>
<span class="sep">|</span>
<a href="{prefix}/ask">AI问答</a>
<span class="sep">|</span>
<a href="{prefix}/missing-content">补抓全文</a>
<span class="sep">|</span>
<a href="{prefix}/keywords">关键词管理</a>
<span class="sep">|</span>
<a href="{prefix}/changelog">更新历史</a>
</div>
</div>
</body>
</html>"""


def get_header(t: MonitorTheme, theme_name: str = "news") -> str:
    """Generate header HTML with corner badge linking to the other theme."""
    other = AAM if theme_name == "news" else NEWS
    other_url = "/aam" if theme_name == "news" else "/"
    prefix = "" if theme_name == "news" else "/aam"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{t.dashboard_title}</title>
<link rel="icon" type="image/svg+xml" href="/favicon.ico">
<style>{get_css(t)}</style>
</head>
<body>
<a class="theme-badge" href="{other_url}">{other.app_name_cn} →</a>
<div class="header">
<div class="header-top">
<div>
<h1>{t.app_name_cn}</h1>
<div class="subtitle">{t.app_subtitle}</div>
</div>
</div>
<div class="header-nav">
<div class="nav-primary">
<a href="{prefix}/" class="active">全部</a>
<a href="{prefix}/monthly-report">月度报告</a>
<span class="nav-divider"></span>
<a href="{prefix}/?type=paper">论文</a>
<a href="{prefix}/?type=news">新闻</a>
<a href="{prefix}/?type=patent">专利</a>
</div>
</div>
</div>
<div class="search-bar">
<form action="{prefix}/" method="get">
<input type="hidden" name="search" value="1">
<input type="text" name="q" placeholder="搜索文章标题或摘要..." value="">
</form>
</div>
</div>
"""


# ── Article rendering (standalone, no class dependency) ────────────────

def render_article(row, t: MonitorTheme, theme_name: str,
                   highlight: str = "") -> str:
    art_id = row['id']
    art_title = row['title']
    art_url = row['url']
    art_source = row['source']
    art_published = format_time_cn(row['published'] or "")
    art_summary = row['summary'] or ""
    art_kw = row['matched_kw'] or ""
    art_relevance = row['relevance'] or 0
    art_translated_title = row['translated_title'] or ""
    art_translated_summary = row['translated_summary'] or ""
    art_is_translated = row['is_translated'] or 0
    art_author = row['author'] or ""
    art_affiliation = row['affiliation'] or ""
    art_trans_content = row['translated_content'] or ""
    art_image_url = row['image_url'] or ""
    has_cjk = bool(re.search(r"[一-鿿]", art_source))
    source_tag_class = "domestic" if has_cjk else "international"
    source_tag = "国内" if has_cjk else "外媒"

    display_title = art_translated_title or art_title
    display_summary = art_translated_summary or art_summary

    def h(text):
        if not highlight:
            return html.escape(str(text))
        escaped = html.escape(str(text))
        return re.sub(f'(?i)({re.escape(highlight)})', r'<mark>\1</mark>', escaped)

    orig_line = ""
    if art_translated_title:
        orig_line = f'<div class="orig-title">原文: {h(art_title[:120])}</div>'

    if art_relevance >= 50:
        score_class = "high"
    elif art_relevance >= 20:
        score_class = "med"
    else:
        score_class = "low"

    art_type = row['article_type'] or ""
    if art_type == "paper":
        type_tag = '<span class="type-tag paper">论文</span> '
    elif art_type == "patent":
        type_tag = '<span class="type-tag patent">专利</span> '
    else:
        type_tag = '<span class="type-tag news">新闻</span> '

    author_line = ""
    if art_author:
        author_line = f'<div class="author-line">作者: {h(art_author)}</div>'
    if art_affiliation:
        author_line += f'<div class="affiliation">{h(art_affiliation)}</div>'

    kw_html = ""
    if art_kw:
        for kw in art_kw.split(", ")[:5]:
            kw_html += f'<span class="kw">{html.escape(kw)}</span>'

    trans_tag = ""
    if art_is_translated or art_trans_content:
        trans_tag = '<span class="translated-tag">中译</span>'

    summary_text = display_summary[:500]
    summary_collapsed = " collapsed" if len(summary_text) > 150 else ""
    img_html = f'<img class="article-thumb" src="{html.escape(art_image_url)}" alt="" loading="lazy">' if art_image_url else ""
    expand_html = f'<button class="expand-btn" id="e-{art_id}" onclick="expandSummary(\'{art_id}\')">展开全文</button>' if summary_collapsed else ""
    art_prefix = "" if theme_name == "news" else "/aam"

    return f"""
    <div class="article" data-id="{art_id}">
      <div class="top-row">
        <div class="source">
          <span class="source-tag {source_tag_class}">{source_tag}</span>
          {html.escape(art_source[:40])} · {art_published}
        </div>
        <div>
          <span class="score {score_class}">{art_relevance}</span>
          {trans_tag}
        </div>
      </div>
      <div class="title"><a href="{art_prefix}/article?id={art_id}">{h(display_title[:120])}</a></div>
      <div class="type-line">{type_tag}</div>
      {orig_line}
      <div class="article-body">
      {img_html}
      {author_line}
      <div class="summary{summary_collapsed}" id="s-{art_id}">{h(summary_text)}</div>
      </div>
      {expand_html}
      {kw_html}
      <div class="actions">
        <a href="{html.escape(_safe_href(art_url))}" target="_blank" rel="noopener">查看原文</a>
      </div>
    </div>"""


def render_event_header(group_title: str, rows: list, t: MonitorTheme) -> str:
    sources = []
    for r in rows:
        s = r['source']
        if s and s not in sources:
            sources.append(s)
    count = len(rows)
    source_str = " · ".join(sources[:5])
    if len(sources) > 5:
        source_str += f" · +{len(sources)-5}"
    display_title = html.escape(group_title[:120])
    return f"""
    <div class="event-header">
      <span class="event-title">{display_title}</span>
      <span class="event-count">{count} 篇报道</span>
      <div class="event-sources">来源：{html.escape(source_str)}</div>
    </div>"""
