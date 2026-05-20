"""CSS and HTML rendering functions for the unified dashboard."""
import html
import re
import urllib.parse
from datetime import datetime, timezone


def _safe_href(url: str) -> str:
    """Return url only if it's a safe http/https link (prevents javascript: XSS)."""
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme in ("http", "https"):
            return url
    except Exception:
        pass
    return ""

from monitor import article_type
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
    for pattern in RSS_DATE_PATTERNS:
        try:
            dt = datetime.strptime(text, pattern)
            if dt.tzinfo:
                dt = dt.astimezone(timezone.utc)
            return dt.strftime("%Y年%m月%d日 %H:%M:%S")
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.strftime("%Y年%m月%d日 %H:%M:%S")
    except (ValueError, TypeError):
        pass
    return text[:10]


# ── CSS ────────────────────────────────────────────────────────────────

def get_css(t: MonitorTheme) -> str:
    return f"""
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
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

.nav-primary {{ display:flex; gap:0.3rem; }}
.nav-primary a {{ font-size:0.85rem; padding:0.35rem 1rem; border-radius:20px; font-weight:600;
                text-decoration:none; color:#94a3b8; border:1px solid transparent; transition:all 0.2s; }}
.nav-primary a:hover {{ color:#e2e8f0; background:rgba(255,255,255,0.05); }}
.nav-primary a.active {{ background:rgba({t.dashboard_color_primary_rgb},0.12); color:{t.dashboard_color_primary}; border-color:rgba({t.dashboard_color_primary_rgb},0.35); }}

.nav-secondary {{ display:flex; gap:0.2rem; }}
.nav-secondary a {{ font-size:0.8rem; padding:0.3rem 0.6rem; text-decoration:none; color:#64748b;
                  border-bottom:2px solid transparent; transition:all 0.2s; white-space:nowrap; }}
.nav-secondary a:hover {{ color:#94a3b8; }}
.nav-secondary a.active {{ color:{t.dashboard_color_primary}; border-bottom-color:{t.dashboard_color_primary}; }}

.nav-divider {{ width:1px; height:20px; background:#3b4a5a; flex-shrink:0; }}

.nav-tertiary {{ display:flex; gap:0.2rem; }}
.nav-tertiary a {{ font-size:0.75rem; padding:0.3rem 0.5rem; text-decoration:none; color:#64748b;
                  transition:all 0.2s; white-space:nowrap; }}
.nav-tertiary a:hover {{ color:#94a3b8; }}
.nav-tertiary a.active {{ color:{t.dashboard_color_primary}; }}
.poll-trigger-btn {{ background:transparent; border:1px solid #334155; border-radius:6px; color:#64748b; font-size:0.75rem; padding:0.3rem 0.5rem; cursor:pointer; transition:all 0.2s; white-space:nowrap; }}
.poll-trigger-btn:hover {{ background:{t.dashboard_header_bg_light}; color:#94a3b8; border-color:#475569; }}


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
.search-bar input {{ flex:1; padding:0.5rem 1rem; border:1px solid #3b4a5a; border-radius:6px;
                    background:#2a3a4a; color:#e2e8f0; font-size:0.85rem; }}
.search-bar input:focus {{ outline:none; border-color:{t.dashboard_color_primary}; }}
.search-bar button {{ padding:0.5rem 1.2rem; background:rgba({t.dashboard_color_primary_rgb},0.12); color:{t.dashboard_color_primary}; border:1px solid rgba({t.dashboard_color_primary_rgb},0.35);
                     border:none; border-radius:6px; font-weight:600; cursor:pointer; font-size:0.85rem; }}

.container {{ max-width:1000px; margin:0 auto; padding:1.5rem 2rem; }}

/* Article card */
.article {{ background:#243447; border:1px solid #3b4a5a; border-radius:10px;
           padding:1.2rem 1.5rem; margin-bottom:1rem; transition:all 0.2s;
           position:relative; overflow:hidden; }}
.article:hover {{ border-color:{t.dashboard_color_primary}; box-shadow:0 0 20px rgba({t.dashboard_color_primary_rgb},0.05); }}
.article.unread {{ border-left:3px solid {t.dashboard_color_primary}; }}
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
/* Star button */
.star-btn {{ background:none; border:none; font-size:1rem; cursor:pointer; padding:0 0.2rem; opacity:0.4; transition:opacity 0.2s; color:#fde047; line-height:1; }}
.star-btn:hover {{ opacity:1; }}
.star-btn.active {{ opacity:1; }}

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

/* Footer stat line */
.footer-stat {{ text-align:center; color:#64748b; font-size:0.78rem; padding:0.5rem 1rem 1.5rem; }}
.footer-stat a {{ color:{t.dashboard_color_primary}; text-decoration:none; }}
.footer-stat a:hover {{ text-decoration:underline; }}

/* Summary expand */
.summary.collapsed {{ overflow:hidden; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; }}
.expand-btn {{ background:none; border:none; color:{t.dashboard_color_primary}; font-size:0.78rem; cursor:pointer; padding:0; }}
.expand-btn:hover {{ text-decoration:underline; }}

/* Read article — lighter background, no opacity dim */
.article.read {{ background:#1e2e40; border-color:#2a3a4a; }}
.article.read .title a {{ color:#94a3b8; }}
.article.read .summary {{ color:#64748b; }}

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
  .nav-primary a {{ font-size:0.8rem; padding:0.3rem 0.8rem; }}
  .nav-secondary a {{ font-size:0.75rem; padding:0.2rem 0.4rem; }}
  .nav-tertiary a {{ font-size:0.7rem; padding:0.2rem 0.4rem; }}
  .stats-bar {{ padding:0.5rem 0.75rem; gap:0.5rem; }}
  .stat-card {{ padding:0.3rem 0.6rem; }}
  .stat-card .num {{ font-size:0.9rem; }}
  .stat-card .label {{ font-size:0.7rem; }}
  .search-bar {{ padding:0.5rem 0.75rem; }}
  .search-bar form {{ max-width:100%; }}
  .search-bar input {{ font-size:16px; }}
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

/* Footer */
.footer-nav {{ text-align:center; padding:1.5rem 2rem; border-top:1px solid #2a3a4a; margin-top:2rem; }}
.footer-nav a {{ color:#64748b; font-size:0.8rem; text-decoration:none; padding:0.3rem 0.8rem; transition:color 0.2s; }}
.footer-nav a:hover {{ color:#38bdf8; }}
.footer-nav .sep {{ color:#3b4a5a; font-size:0.7rem; }}
"""


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
<a href="{prefix}/?unread=1" id="unread-link">未读</a>
<a href="{prefix}/?starred=1" id="starred-link">收藏</a>
</div>
<div class="nav-secondary">
<a href="{prefix}/?type=paper">论文</a>
<a href="{prefix}/?type=news">新闻</a>
</div>
<div class="nav-tertiary">
<a href="{prefix}/export?days=7">导出</a>
<a href="{prefix}/?search=1">搜索</a>
<button class="poll-trigger-btn" id="poll-btn" onclick="triggerPoll()">手动采集</button>
</div>
</div>
</div>
"""


# ── Article rendering (standalone, no class dependency) ────────────────

def render_article(row: tuple, t: MonitorTheme, theme_name: str,
                   highlight: str = "") -> str:
    art_id = row[0]
    art_title = row[1]
    art_url = row[2]
    art_source = row[3]
    art_published = format_time_cn(row[4] or "")
    art_summary = row[6] if len(row) > 6 else ""
    art_kw = row[7] if len(row) > 7 else ""
    art_relevance = row[8] if len(row) > 8 else 0
    art_is_read = row[9] if len(row) > 9 else 0
    art_is_starred = row[22] if len(row) > 22 else 0
    art_translated_title = row[11] if len(row) > 11 else ""
    art_translated_summary = row[12] if len(row) > 12 else ""
    art_is_translated = row[13] if len(row) > 13 else 0
    art_author = row[14] if len(row) > 14 and row[14] else ""
    art_affiliation = row[15] if len(row) > 15 and row[15] else ""
    art_trans_content = row[18] if len(row) > 18 and row[18] else ""
    art_image_url = row[19] if len(row) > 19 and row[19] else ""
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

    art_type = row[21] if len(row) > 21 else ""
    type_tag = '<span class="type-tag paper">论文</span> ' if art_type == "paper" else '<span class="type-tag news">新闻</span> '

    read_class = "read" if art_is_read else "unread"

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
    read_btn = "标为已读" if not art_is_read else "标为未读"
    art_prefix = "" if theme_name == "news" else "/aam"

    return f"""
    <div class="article {read_class}" data-id="{art_id}">
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
        <button class="star-btn{" active" if art_is_starred else ""}" onclick="toggleStar('{art_id}')" title="收藏">{"★" if art_is_starred else "☆"}</button>
        <a href="{_safe_href(art_url)}" target="_blank" rel="noopener">查看原文</a>
        <button onclick="toggleRead('{art_id}')">{read_btn}</button>
      </div>
    </div>"""


def render_event_header(group_title: str, rows: list, t: MonitorTheme) -> str:
    sources = []
    for r in rows:
        s = r[3] if len(r) > 3 else ""
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
