#!/usr/bin/env python3
"""
Web dashboard for the news monitor.
"""
import html
import http.server
import json
import logging
import re
import sqlite3
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import config
from monitor import init_db, get_articles, get_event_grouped_articles, mark_read, search_articles, fetch_article_content, save_snapshot
from translator import translate_content

log = logging.getLogger(f"{config.LOGGER_NAME}.dashboard")

# ── Date formatting ────────────────────────────────────────────────────

RSS_DATE_PATTERNS = [
    "%a, %d %b %Y %H:%M:%S %z",     # Thu, 14 May 2026 12:00:00 +0000
    "%a, %d %b %Y %H:%M:%S %Z",     # Thu, 14 May 2026 12:00:00 GMT
    "%d %b %Y %H:%M:%S %z",         # 14 May 2026 12:00:00 +0000
    "%Y-%m-%dT%H:%M:%S",            # 2026-05-14T12:00:00
    "%Y-%m-%dT%H:%M:%SZ",           # 2026-05-14T12:00:00Z
    "%Y-%m-%dT%H:%M:%S%z",          # 2026-05-14T12:00:00+0000
    "%Y-%m-%d",                     # 2026-05-14
]


def format_time_cn(date_str: str) -> str:
    """Convert various date formats to Chinese: 2026年05月14日 12:00:00"""
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

CSS = f"""
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
       background:#0b1121; color:#e2e8f0; min-height:100vh; }}

/* Header */
.header {{ background:{config.HEADER_BG}; border-bottom:1px solid {config.HEADER_BORDER};
          padding:1rem 2rem; }}
.header-top {{ display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:1rem; }}
.header h1 {{ font-size:1.3rem; color:{config.COLOR_PRIMARY}; letter-spacing:0.5px; }}
.header .subtitle {{ color:#64748b; font-size:0.8rem; margin-top:0.2rem; }}
.header-actions {{ display:flex; gap:0.5rem; flex-wrap:wrap; justify-content:flex-end; }}
.header-actions a {{ color:#94a3b8; font-size:0.82rem; text-decoration:none; padding:0.3rem 0.7rem;
                    border:1px solid #334155; border-radius:6px; transition:all 0.2s;
                    white-space:nowrap; }}
.header-actions a:hover {{ background:{config.HEADER_BG_LIGHT}; color:{config.COLOR_PRIMARY}; border-color:{config.COLOR_PRIMARY}; }}
.header-actions a.active {{ background:{config.COLOR_PRIMARY}; color:#0b1121; border-color:{config.COLOR_PRIMARY}; font-weight:600; }}
.header-actions .nav-group {{ display:inline-flex; gap:0.3rem; align-items:center; }}

/* Corner badge — fixed top-right */
.theme-badge {{ position:fixed; top:12px; right:12px; z-index:999;
  display:flex; align-items:center; gap:4px;
  padding:4px 10px; border-radius:20px;
  font-size:0.75rem; font-weight:600; text-decoration:none;
  background:rgba(15,23,42,0.85); backdrop-filter:blur(4px);
  border:1px solid #fb923c; color:#fb923c;
  transition:all 0.2s; }}
.theme-badge:hover {{ background:rgba(251,146,60,0.15); }}

/* Stats bar */
.stats-bar {{ display:flex; gap:1rem; padding:0.75rem 2rem; background:#0f172a;
             border-bottom:1px solid #1e293b; flex-wrap:wrap; }}
.stat-card {{ display:flex; align-items:center; gap:0.5rem; padding:0.4rem 0.8rem;
             background:#1e293b; border-radius:6px; border:1px solid #334155; }}
.stat-card .num {{ color:{config.COLOR_PRIMARY}; font-weight:700; font-size:1rem; }}
.stat-card .label {{ color:#64748b; font-size:0.75rem; }}
.stat-card .num.green {{ color:#22c55e; }}
.stat-card .num.purple {{ color:#a78bfa; }}
.stat-card .num.orange {{ color:#fb923c; }}

/* Search bar */
.search-bar {{ background:#0f172a; padding:0.75rem 2rem; border-bottom:1px solid #1e293b; }}
.search-bar form {{ display:flex; gap:0.5rem; max-width:500px; }}
.search-bar input {{ flex:1; padding:0.5rem 1rem; border:1px solid #334155; border-radius:6px;
                    background:#1e293b; color:#e2e8f0; font-size:0.85rem; }}
.search-bar input:focus {{ outline:none; border-color:{config.COLOR_PRIMARY}; }}
.search-bar button {{ padding:0.5rem 1.2rem; background:{config.COLOR_PRIMARY}; color:#0b1121;
                     border:none; border-radius:6px; font-weight:600; cursor:pointer; font-size:0.85rem; }}

.container {{ max-width:1000px; margin:0 auto; padding:1.5rem 2rem; }}

/* Article card */
.article {{ background:#1e293b; border:1px solid #334155; border-radius:10px;
           padding:1.2rem 1.5rem; margin-bottom:1rem; transition:all 0.2s;
           position:relative; overflow:hidden; }}
.article:hover {{ border-color:{config.COLOR_PRIMARY}; box-shadow:0 0 20px rgba({config.COLOR_PRIMARY_RGB},0.05); }}
.article.unread {{ border-left:3px solid {config.COLOR_PRIMARY}; }}
.article .top-row {{ display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.4rem; }}
.article .source {{ font-size:0.78rem; color:#64748b; display:flex; align-items:center; gap:0.3rem; }}
.article .source-tag {{ font-size:0.65rem; padding:0.1rem 0.35rem; border-radius:3px; font-weight:600; }}
.article .source-tag.domestic {{ background:{config.SOURCE_TAG_DOMESTIC_BG}; color:{config.SOURCE_TAG_DOMESTIC_COLOR}; }}
.article .source-tag.international {{ background:#3b1f3b; color:#c084fc; }}
.article .badge {{ display:inline-block; background:{config.COLOR_PRIMARY}; color:#0b1121; font-size:0.65rem;
                  font-weight:700; padding:0.1rem 0.35rem; border-radius:3px; vertical-align:middle; }}
.article .score {{ display:inline-flex; align-items:center; gap:0.2rem; font-size:0.75rem;
                  padding:0.15rem 0.5rem; border-radius:4px; font-weight:600; }}
.article .score.high {{ background:#166534; color:#86efac; }}
.article .score.med {{ background:#713f12; color:#fde047; }}
.article .score.low {{ background:#3b1111; color:#fca5a5; }}
.article .title {{ font-size:1.05rem; margin:0.4rem 0 0.2rem; line-height:1.5; }}
.article .title a {{ color:#e2e8f0; text-decoration:none; }}
.article .title a:hover {{ color:{config.COLOR_PRIMARY}; }}
.article .orig-title {{ font-size:0.78rem; color:#475569; margin-bottom:0.3rem; }}
.article .kw {{ display:inline-block; background:#0f172a; color:{config.COLOR_PRIMARY}; font-size:0.7rem;
               padding:0.15rem 0.5rem; border-radius:4px; margin-right:0.3rem; margin-top:0.3rem; }}
.article .summary {{ color:#94a3b8; font-size:0.88rem; line-height:1.6; margin:0.5rem 0; }}
.article .actions {{ margin-top:0.6rem; display:flex; gap:0.5rem; }}
.article .actions button, .article .actions a {{
  font-size:0.78rem; padding:0.3rem 0.8rem; border-radius:5px; cursor:pointer; text-decoration:none; }}
.article .actions button {{ background:transparent; border:1px solid #475569; color:#94a3b8; }}
.article .actions button:hover {{ background:#334155; color:#e2e8f0; }}
.article .actions a {{ background:transparent; border:1px solid #475569; color:#94a3b8; }}
.article .actions a:hover {{ background:#334155; color:{config.COLOR_PRIMARY}; }}
.article .translated-tag {{ display:inline-block; background:{config.SOURCE_TAG_DOMESTIC_BG}; color:{config.SOURCE_TAG_DOMESTIC_COLOR}; font-size:0.65rem;
                           padding:0.1rem 0.35rem; border-radius:3px; }}
.article-body {{ display:flex; gap:1rem; align-items:flex-start; }}
.article-thumb {{ width:120px; height:80px; object-fit:cover; border-radius:6px; flex-shrink:0;
                 margin-top:0.3rem; background:#0f172a; border:1px solid #334155; }}
.article .author-line {{ font-size:0.78rem; color:#94a3b8; margin:0.2rem 0; }}
.article .affiliation {{ color:#64748b; font-size:0.72rem; }}
.type-tag {{ font-size:0.65rem; padding:0.1rem 0.4rem; border-radius:3px; font-weight:600; vertical-align:middle; }}
.type-tag.paper {{ background:#1a1a3e; color:#818cf8; }}
.type-tag.news {{ background:#1a2e1a; color:#4ade80; }}

/* Pagination */
.pagination {{ display:flex; justify-content:center; gap:0.5rem; margin:2rem 0; flex-wrap:wrap; }}
.pagination a {{ color:#94a3b8; text-decoration:none; padding:0.4rem 0.8rem;
                border:1px solid #334155; border-radius:6px; font-size:0.85rem; transition:all 0.2s; }}
.pagination a:hover {{ background:{config.HEADER_BG_LIGHT}; color:{config.COLOR_PRIMARY}; border-color:{config.COLOR_PRIMARY}; }}
.pagination a.active {{ background:{config.COLOR_PRIMARY}; color:#0b1121; border-color:{config.COLOR_PRIMARY}; font-weight:600; }}
.empty {{ text-align:center; color:#475569; padding:3rem 1rem; font-size:0.95rem; }}

/* Event group */
.event-group {{ margin-bottom:1.5rem; }}
.event-header {{ background:{config.EVENT_HEADER_BG}; border:1px solid {config.EVENT_BORDER};
                border-radius:8px; padding:0.6rem 1rem; margin-bottom:0.6rem;
                display:flex; align-items:center; justify-content:space-between; gap:0.5rem; flex-wrap:wrap; }}
.event-header .event-title {{ color:{config.COLOR_PRIMARY}; font-size:0.9rem; font-weight:600; }}
.event-header .event-count {{ color:#64748b; font-size:0.78rem; background:#1e293b;
                             padding:0.15rem 0.5rem; border-radius:4px; }}
.event-header .event-sources {{ color:#64748b; font-size:0.72rem; width:100%; }}
.event-group .article:last-child {{ margin-bottom:0; }}

/* Toast */
.toast {{ position:fixed; bottom:2rem; right:2rem; background:#22c55e; color:#fff;
         padding:0.75rem 1.5rem; border-radius:8px; display:none; z-index:100; }}

/* ── Mobile responsive ────────────────────────────────────────────── */

@media (max-width: 768px) {{
  .header {{ padding:0.75rem 1rem; }}
  .header h1 {{ font-size:1.1rem; }}
  .header-actions {{ gap:0.4rem; }}
  .header-actions a {{ font-size:0.78rem; padding:0.3rem 0.5rem; }}
  .theme-badge {{ top:8px; right:8px; font-size:0.7rem; padding:3px 8px; }}

  .stats-bar {{ padding:0.5rem 0.75rem; gap:0.5rem; }}
  .stat-card {{ padding:0.3rem 0.6rem; }}
  .stat-card .num {{ font-size:0.9rem; }}
  .stat-card .label {{ font-size:0.7rem; }}


  .search-bar {{ padding:0.5rem 0.75rem; }}
  .search-bar form {{ max-width:100%; }}
  .search-bar input {{ font-size:16px; /* prevent iOS zoom */ }}

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
  .header-actions {{ align-self:stretch; justify-content:center; }}

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
"""

HEADER = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{config.DASHBOARD_TITLE}</title>
<style>{CSS}</style>
</head>
<body>
<a class="theme-badge" href="{config.DASHBOARD_OTHER_THEME_URL}" target="_blank">{config.DASHBOARD_OTHER_THEME_NAME} →</a>
<div class="header">
<div class="header-top">
<div>
<h1>{config.APP_NAME_CN}</h1>
<div class="subtitle">{config.APP_SUBTITLE}</div>
</div>
<div class="header-actions" id="header-actions">
<span class="nav-group">
<a href="/" class="active">全部</a>
<a href="/?unread=1" id="unread-link">未读</a>
<a href="/?search=1">搜索</a>
</span>
</div>
</div>
</div>
"""

FOOTER = '</div></body></html>'


class DashboardHandler(http.server.BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        log.info(f"{self.client_address[0]} - {fmt % args}")

    def _send_html(self, html: str, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _send_json(self, data: dict):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _render_article(self, row: tuple) -> str:
        """Render a single article card."""
        art_id = row[0]
        art_title = row[1]
        art_url = row[2]
        art_source = row[3]
        art_published = format_time_cn(row[4] or "")
        art_summary = row[6] if len(row) > 6 else ""
        art_kw = row[7] if len(row) > 7 else ""
        art_relevance = row[8] if len(row) > 8 else 0
        art_is_read = row[9] if len(row) > 9 else 0
        art_translated_title = row[11] if len(row) > 11 else ""
        art_translated_summary = row[12] if len(row) > 12 else ""
        art_is_translated = row[13] if len(row) > 13 else 0
        art_author = row[14] if len(row) > 14 and row[14] else ""
        art_affiliation = row[15] if len(row) > 15 and row[15] else ""
        art_trans_content = row[18] if len(row) > 18 and row[18] else ""
        art_image_url = row[19] if len(row) > 19 and row[19] else ""

        # Detect domestic/international source
        has_cjk = bool(re.search(r"[一-鿿]", art_source))
        source_tag_class = "domestic" if has_cjk else "international"
        source_tag = "国内" if has_cjk else "外媒"

        display_title = art_translated_title or art_title
        display_summary = art_translated_summary or art_summary
        orig_line = ""
        if art_translated_title:
            orig_line = f'<div class="orig-title">原文: {html.escape(art_title[:120])}</div>'

        # Relevance score class
        if art_relevance >= 50:
            score_class = "high"
        elif art_relevance >= 20:
            score_class = "med"
        else:
            score_class = "low"

        # Article type tag
        type_tag = ""
        if art_author:
            type_tag = '<span class="type-tag paper">论文</span> '
        else:
            type_tag = '<span class="type-tag news">新闻</span> '

        unread_class = "unread" if not art_is_read else ""

        author_line = ""
        if art_author:
            author_line = f'<div class="author-line">作者: {html.escape(art_author)}</div>'
        if art_affiliation:
            author_line += f'<div class="affiliation">{html.escape(art_affiliation)}</div>'

        kw_html = ""
        if art_kw:
            for kw in art_kw.split(", ")[:5]:
                kw_html += f'<span class="kw">{html.escape(kw)}</span>'

        trans_tag = ""
        if art_is_translated or art_trans_content:
            trans_tag = '<span class="translated-tag">中译</span>'

        return f"""
        <div class="article {unread_class}" data-id="{art_id}">
          <div class="top-row">
            <div class="source">
              <span class="source-tag {source_tag_class}">{source_tag}</span>
              {html.escape(art_source[:40])} · {art_published}
            </div>
            <div>
              {type_tag}
              <span class="score {score_class}">{art_relevance}</span>
              {trans_tag}
            </div>
          </div>
          <div class="title"><a href="/article?id={art_id}">{html.escape(display_title[:120])}</a></div>
          {orig_line}
          <div class="article-body">
          {f'<img class="article-thumb" src="{html.escape(art_image_url)}" alt="" loading="lazy">' if art_image_url else ''}
          {author_line}
          <div class="summary">{html.escape(display_summary[:500])}</div>
          </div>
          {kw_html}
          <div class="actions">
            <a href="{art_url}" target="_blank" rel="noopener">查看原文</a>
            <button onclick="toggleRead('{art_id}')">{'标为已读' if not art_is_read else '标为未读'}</button>
          </div>
        </div>"""

    def _render_event_header(self, group_title: str, rows: list) -> str:
        """Render an event group header with title and source list."""
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

    def _handle_page(self, params: dict):
        page = int(params.get("page", "1"))
        limit = 50
        offset = (page - 1) * limit
        unread_only = params.get("unread", "") == "1"

        conn = init_db()
        try:
            total = conn.execute("SELECT COUNT(*) FROM articles WHERE 1=1" + (" AND is_read=0" if unread_only else "")).fetchone()[0]
            total_pages = max(1, (total + limit - 1) // limit)

            html_content = '<div class="container">'

            # Stats
            all_count = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
            unread_count = conn.execute("SELECT COUNT(*) FROM articles WHERE is_read=0").fetchone()[0]
            last_24h = conn.execute("SELECT COUNT(*) FROM articles WHERE fetched_at > datetime('now', '-1 day')").fetchone()[0]
            html_content += f"""
            <div class="stats-bar">
              <div class="stat-card"><span class="num">{all_count}</span><span class="label">总计</span></div>
              <div class="stat-card"><span class="num">{unread_count}</span><span class="label">未读</span></div>
              <div class="stat-card"><span class="num green">{last_24h}</span><span class="label">最近24h</span></div>
            </div>"""

            # Articles
            if config.HAS_EVENT_GROUPING:
                grouped = get_event_grouped_articles(conn, limit=limit, offset=offset, unread_only=unread_only)
                # Group contiguous rows by event_group
                event_groups = []
                standalone = []
                current_group = None

                for row, is_start in grouped:
                    eg = row[16] if len(row) > 16 else ""
                    if is_start:
                        if current_group is not None:
                            event_groups.append(current_group)
                        current_group = [eg, row, []]
                        current_group[2].append(row)
                    elif current_group is not None and eg == current_group[0]:
                        current_group[2].append(row)
                    else:
                        if current_group is not None:
                            event_groups.append(current_group)
                            current_group = None
                        standalone.append(row)

                if current_group is not None:
                    event_groups.append(current_group)

                # Render events first, then standalone
                for eg_id, first_row, eg_rows in event_groups:
                    if len(eg_rows) > 1:
                        html_content += '<div class="event-group">'
                        eg_title = first_row[17] if len(first_row) > 17 else ""
                        html_content += self._render_event_header(eg_title or "", eg_rows)
                        for r in eg_rows:
                            html_content += self._render_article(r)
                        html_content += '</div>'
                    else:
                        standalone.append(eg_rows[0])

                for row in standalone:
                    html_content += self._render_article(row)
            else:
                rows = get_articles(conn, limit=limit, offset=offset, unread_only=unread_only)
                for row in rows:
                    html_content += self._render_article(row)

            # Pagination
            if total_pages > 1:
                html_content += '<div class="pagination">'
                for p in range(max(1, page - 5), min(total_pages, page + 5) + 1):
                    active = "active" if p == page else ""
                    url = f"/?page={p}" + ("&unread=1" if unread_only else "")
                    html_content += f'<a href="{url}" class="{active}">{p}</a>'
                html_content += '</div>'

            html_content += '</div>'

            # Toast + read toggle script
            html_content += """
            <div id="toast" class="toast"></div>
            <script>
            function setActiveNav() {
              var params = new URLSearchParams(window.location.search);
              var links = document.querySelectorAll('#header-actions a');
              links.forEach(function(a) {
                a.classList.remove('active');
                var href = a.getAttribute('href');
                if (href === '/' && !params.has('unread') && !params.has('search')) a.classList.add('active');
                if (href === '/?unread=1' && params.get('unread') === '1') a.classList.add('active');
                if (href === '/?search=1' && params.get('search') === '1') a.classList.add('active');
              });
            }
            setActiveNav();

            function toggleRead(id) {
              fetch("/mark-read?id=" + id).then(r => r.json()).then(d => {
                if (d.ok) {
                  var el = document.querySelector('.article[data-id="' + id + '"]');
                  if (el) {
                    var isUnread = el.classList.contains('unread');
                    el.classList.toggle('unread');
                    var btn = el.querySelector('.actions button');
                    btn.textContent = isUnread ? '标为未读' : '标为已读';
                  }
                  var toast = document.getElementById('toast');
                  toast.textContent = '✅ ' + d.msg;
                  toast.style.display = 'block';
                  setTimeout(function() { toast.style.display = 'none'; }, 2000);
                }
              });
            }
            </script>
            """

            self._send_html(HEADER + html_content + FOOTER)
        finally:
            conn.close()

    def _handle_article(self, params: dict):
        article_id = params.get("id", "")
        if not article_id:
            self._send_html(HEADER + '<div class="container"><div class="empty">缺少文章ID</div><a href="/" style="color:{config.COLOR_PRIMARY};">← 返回首页</a></div>' + FOOTER, 404)
            return

        conn = init_db()
        try:
            row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
            if not row:
                self._send_html(HEADER + '<div class="container"><div class="empty">文章不存在</div><a href="/" style="color:{config.COLOR_PRIMARY};">← 返回首页</a></div>' + FOOTER, 404)
                return

            # Mark as read
            mark_read(conn, article_id)

            art_id = row[0]
            art_title = row[1]
            art_url = row[2]
            art_source = row[3]
            art_published = format_time_cn(row[4] or "")
            art_summary = row[6] if len(row) > 6 else ""
            art_kw = row[7] if len(row) > 7 else ""
            art_relevance = row[8] if len(row) > 8 else 0
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
            orig_line = ""
            if art_translated_title:
                orig_line = f'<p style="color:#64748b;font-size:0.85rem;">原文: {html.escape(art_title)}</p>'

            kw_html = ""
            if art_kw:
                for kw in art_kw.split(", ")[:10]:
                    kw_html += f'<span class="kw">{html.escape(kw)}</span>'

            # Fetch full content if available
            content_html = ""
            if art_trans_content:
                content_html = f"""
                <div style="margin-top:2rem;padding-top:1.5rem;border-top:1px solid #334155;">
                  <h3 style="color:#e2e8f0;font-size:1rem;margin-bottom:0.8rem;">全文翻译</h3>
                  <div style="color:#94a3b8;font-size:0.88rem;line-height:1.8;white-space:pre-wrap;">{html.escape(art_trans_content)}</div>
                </div>"""
            else:
                # Try to fetch and display original content
                snap = config.ARCHIVE_DIR / f"{art_id}.html"
                if snap.exists():
                    raw = snap.read_text("utf-8")
                    import re as _re
                    m = _re.search(r"<pre[^>]*>(.*?)</pre>", raw, _re.DOTALL)
                    if m:
                        text = m.group(1).strip()
                        content_html = f"""
                        <div style="margin-top:2rem;padding-top:1.5rem;border-top:1px solid #334155;">
                          <h3 style="color:#e2e8f0;font-size:1rem;margin-bottom:0.8rem;">原文内容</h3>
                          <div style="color:#94a3b8;font-size:0.88rem;line-height:1.8;white-space:pre-wrap;">{html.escape(text[:5000])}</div>
                        </div>"""

            title_tag = f"<title>{html.escape(display_title[:80])} - {config.DASHBOARD_TITLE}</title>"
            article_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
{title_tag}
<style>{CSS}</style>
</head>
<body>
<a class="theme-badge" href="{config.DASHBOARD_OTHER_THEME_URL}" target="_blank">{config.DASHBOARD_OTHER_THEME_NAME} →</a>
<div class="header">
<div class="header-top">
<div>
<h1><a href="/" style="color:{config.COLOR_PRIMARY};text-decoration:none;">{config.APP_NAME_CN}</a></h1>
</div>
<div class="header-actions">
<span class="nav-group">
<a href="/" class="active">全部</a>
<a href="/?unread=1">未读</a>
<a href="/?search=1">搜索</a>
</span>
</div>
</div>
</div>
<div class="container" style="max-width:800px;">
<div class="article" style="border-left:3px solid {config.COLOR_PRIMARY};">

<div class="top-row">
<div class="source">
<span class="source-tag {source_tag_class}">{source_tag}</span>
{html.escape(art_source)} · {art_published}
</div>
<div>
<span class="score {'high' if art_relevance >= 50 else 'med' if art_relevance >= 20 else 'low'}">{art_relevance}</span>
{'<span class="translated-tag">中译</span>' if art_is_translated or art_trans_content else ''}
</div>
</div>

<h2 style="color:#e2e8f0;font-size:1.2rem;margin:0.6rem 0 0.2rem;line-height:1.5;">{html.escape(display_title)}</h2>
{orig_line}
{f'<img src="{html.escape(art_image_url)}" alt="" style="max-width:100%;max-height:400px;border-radius:8px;margin:0.8rem 0;border:1px solid #334155;">' if art_image_url else ''}

<div style="margin:0.5rem 0;">
{kw_html}
</div>

<div style="color:#94a3b8;font-size:0.9rem;line-height:1.7;margin:1rem 0;">{html.escape(display_summary)}</div>

<div style="margin-top:1.5rem;">
<a href="{art_url}" target="_blank" rel="noopener" style="display:inline-block;background:{config.COLOR_PRIMARY};color:#0b1121;padding:0.5rem 1.2rem;border-radius:6px;font-weight:600;text-decoration:none;">查看原文</a>
<a href="/" style="margin-left:1rem;color:{config.COLOR_PRIMARY};">← 返回首页</a>
</div>

</div>
{content_html}
</div>
</body>
</html>"""

            self._send_html(article_html)

        finally:
            conn.close()

    def _handle_search(self, params: dict):
        q = params.get("q", "")
        page = int(params.get("page", "1"))
        limit = 50
        offset = (page - 1) * limit

        conn = init_db()
        try:
            if q:
                rows = conn.execute(
                    "SELECT * FROM articles WHERE title LIKE ? OR summary LIKE ? "
                    "OR translated_title LIKE ? OR translated_summary LIKE ? "
                    "ORDER BY published DESC, relevance DESC LIMIT ? OFFSET ?",
                    (f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%", limit, offset),
                ).fetchall()
                total = conn.execute(
                    "SELECT COUNT(*) FROM articles WHERE title LIKE ? OR summary LIKE ? "
                    "OR translated_title LIKE ? OR translated_summary LIKE ?",
                    (f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%"),
                ).fetchone()[0]
            else:
                rows = []
                total = 0

            html_content = '<div class="container">'

            # Search form
            html_content += f"""
            <div class="search-bar">
            <form action="/" method="get">
            <input type="hidden" name="search" value="1">
            <input type="text" name="q" placeholder="搜索文章标题或摘要..." value="{html.escape(q)}">
            <button type="submit">搜索</button>
            </form>
            </div>"""

            if q:
                html_content += f'<div style="padding:0.5rem 0;color:#64748b;font-size:0.85rem;">找到 {total} 条结果</div>'
                for row in rows:
                    html_content += self._render_article(row)
                if not rows:
                    html_content += '<div class="empty">未找到匹配的文章</div>'

                total_pages = max(1, (total + limit - 1) // limit)
                if total_pages > 1:
                    html_content += '<div class="pagination">'
                    for p in range(max(1, page - 5), min(total_pages, page + 5) + 1):
                        active = "active" if p == page else ""
                        html_content += f'<a href="/?search=1&q={urllib.parse.quote(q)}&page={p}" class="{active}">{p}</a>'
                    html_content += '</div>'
            else:
                html_content += '<div class="empty">输入关键词搜索文章</div>'

            html_content += '</div>'
            self._send_html(HEADER + html_content + FOOTER)
        finally:
            conn.close()

    def _handle_mark_read(self, params: dict):
        article_id = params.get("id", "")
        conn = init_db()
        try:
            row = conn.execute("SELECT is_read FROM articles WHERE id = ?", (article_id,)).fetchone()
            if row:
                new_val = 0 if row[0] else 1
                conn.execute("UPDATE articles SET is_read = ? WHERE id = ?", (new_val, article_id))
                conn.commit()
                self._send_json({"ok": True, "msg": "已读" if new_val else "标为未读", "is_read": new_val})
            else:
                self._send_json({"ok": False, "msg": "文章不存在"})
        finally:
            conn.close()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)
        params = {k: v[0] for k, v in params.items()}

        if path == "/":
            if params.get("search") == "1":
                self._handle_search(params)
            else:
                self._handle_page(params)
        elif path == "/article":
            self._handle_article(params)
        elif path == "/mark-read":
            self._handle_mark_read(params)
        else:
            self._send_html(HEADER + '<div class="container"><h2 style="color:#475569;">404</h2><a href="/" style="color:{config.COLOR_PRIMARY};">← 返回首页</a></div>' + FOOTER, 404)


def run():
    """Start the dashboard server."""
    server = http.server.HTTPServer((config.DASHBOARD_HOST, config.DASHBOARD_PORT), DashboardHandler)
    log.info(f"{config.APP_NAME_CN} Dashboard running at http://{config.DASHBOARD_HOST}:{config.DASHBOARD_PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Dashboard stopped")
        server.server_close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    run()
