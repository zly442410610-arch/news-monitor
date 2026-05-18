#!/usr/bin/env python3
"""
Web dashboard for the aerospace news monitor.
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
from monitor import init_db, get_articles, get_event_grouped_articles, mark_read, search_articles

log = logging.getLogger("news-monitor.dashboard")

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

CSS = """
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
       background:#0b1121; color:#e2e8f0; min-height:100vh; }

/* Header */
.header { background:linear-gradient(135deg,#1e293b,#0f172a); border-bottom:1px solid #1e3a5f;
          padding:1rem 2rem; }
.header-top { display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:1rem; }
.header h1 { font-size:1.3rem; color:#38bdf8; letter-spacing:0.5px; }
.header .subtitle { color:#64748b; font-size:0.8rem; margin-top:0.2rem; }
.header-actions { display:flex; gap:0.8rem; }
.header-actions a { color:#94a3b8; font-size:0.85rem; text-decoration:none; padding:0.3rem 0.7rem;
                    border:1px solid #334155; border-radius:6px; transition:all 0.2s; }
.header-actions a:hover { background:#1e293b; color:#38bdf8; border-color:#38bdf8; }

/* Stats bar */
.stats-bar { display:flex; gap:1rem; padding:0.75rem 2rem; background:#0f172a;
             border-bottom:1px solid #1e293b; flex-wrap:wrap; }
.stat-card { display:flex; align-items:center; gap:0.5rem; padding:0.4rem 0.8rem;
             background:#1e293b; border-radius:6px; border:1px solid #334155; }
.stat-card .num { color:#38bdf8; font-weight:700; font-size:1rem; }
.stat-card .label { color:#64748b; font-size:0.75rem; }
.stat-card .num.green { color:#22c55e; }
.stat-card .num.purple { color:#a78bfa; }
.stat-card .num.orange { color:#fb923c; }

/* Filter tabs */
.filter-bar { display:flex; gap:0; padding:0 2rem; background:#0f172a; border-bottom:1px solid #1e293b; }
.filter-bar a { padding:0.5rem 1rem; color:#64748b; text-decoration:none; font-size:0.85rem;
                border-bottom:2px solid transparent; transition:all 0.2s; }
.filter-bar a:hover { color:#94a3b8; }
.filter-bar a.active { color:#38bdf8; border-bottom-color:#38bdf8; }

/* Search bar */
.search-bar { background:#0f172a; padding:0.75rem 2rem; border-bottom:1px solid #1e293b; }
.search-bar form { display:flex; gap:0.5rem; max-width:500px; }
.search-bar input { flex:1; padding:0.5rem 1rem; border:1px solid #334155; border-radius:6px;
                    background:#1e293b; color:#e2e8f0; font-size:0.85rem; }
.search-bar input:focus { outline:none; border-color:#38bdf8; }
.search-bar button { padding:0.5rem 1.2rem; background:#38bdf8; color:#0b1121;
                     border:none; border-radius:6px; font-weight:600; cursor:pointer; font-size:0.85rem; }

.container { max-width:1000px; margin:0 auto; padding:1.5rem 2rem; }

/* Article card */
.article { background:#1e293b; border:1px solid #334155; border-radius:10px;
           padding:1.2rem 1.5rem; margin-bottom:1rem; transition:all 0.2s;
           position:relative; overflow:hidden; }
.article:hover { border-color:#38bdf8; box-shadow:0 0 20px rgba(56,189,248,0.05); }
.article.unread { border-left:3px solid #38bdf8; }
.article .top-row { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.4rem; }
.article .source { font-size:0.78rem; color:#64748b; display:flex; align-items:center; gap:0.3rem; }
.article .source-tag { font-size:0.65rem; padding:0.1rem 0.35rem; border-radius:3px; font-weight:600; }
.article .source-tag.domestic { background:#1e3a5f; color:#60a5fa; }
.article .source-tag.international { background:#3b1f3b; color:#c084fc; }
.article .badge { display:inline-block; background:#38bdf8; color:#0b1121; font-size:0.65rem;
                  font-weight:700; padding:0.1rem 0.35rem; border-radius:3px; vertical-align:middle; }
.article .score { display:inline-flex; align-items:center; gap:0.2rem; font-size:0.75rem;
                  padding:0.15rem 0.5rem; border-radius:4px; font-weight:600; }
.article .score.high { background:#166534; color:#86efac; }
.article .score.med { background:#713f12; color:#fde047; }
.article .score.low { background:#3b1111; color:#fca5a5; }
.article .title { font-size:1.05rem; margin:0.4rem 0 0.2rem; line-height:1.5; }
.article .title a { color:#e2e8f0; text-decoration:none; }
.article .title a:hover { color:#38bdf8; }
.article .orig-title { font-size:0.78rem; color:#475569; margin-bottom:0.3rem; }
.article .kw { display:inline-block; background:#0f172a; color:#38bdf8; font-size:0.7rem;
               padding:0.15rem 0.5rem; border-radius:4px; margin-right:0.3rem; margin-top:0.3rem; }
.article .summary { color:#94a3b8; font-size:0.88rem; line-height:1.6; margin:0.5rem 0; }
.article .actions { margin-top:0.6rem; display:flex; gap:0.5rem; }
.article .actions button, .article .actions a {
  font-size:0.78rem; padding:0.3rem 0.8rem; border-radius:5px; cursor:pointer; text-decoration:none; }
.article .actions button { background:transparent; border:1px solid #475569; color:#94a3b8; }
.article .actions button:hover { background:#334155; color:#e2e8f0; }
.article .actions a { background:transparent; border:1px solid #475569; color:#94a3b8; }
.article .actions a:hover { background:#334155; color:#38bdf8; }
.article .translated-tag { display:inline-block; background:#1e3a5f; color:#60a5fa; font-size:0.65rem;
                           padding:0.1rem 0.35rem; border-radius:3px; }
.article .author-line { font-size:0.78rem; color:#94a3b8; margin:0.2rem 0; }
.article .affiliation { color:#64748b; font-size:0.72rem; }
.type-tag { font-size:0.65rem; padding:0.1rem 0.4rem; border-radius:3px; font-weight:600; vertical-align:middle; }
.type-tag.paper { background:#1a1a3e; color:#818cf8; }
.type-tag.news { background:#1a2e1a; color:#4ade80; }

/* Pagination */
.pagination { display:flex; justify-content:center; gap:0.5rem; margin:2rem 0; flex-wrap:wrap; }
.pagination a { color:#94a3b8; text-decoration:none; padding:0.4rem 0.8rem;
                border:1px solid #334155; border-radius:6px; font-size:0.85rem; transition:all 0.2s; }
.pagination a:hover { background:#1e293b; color:#38bdf8; border-color:#38bdf8; }
.pagination a.active { background:#38bdf8; color:#0b1121; border-color:#38bdf8; font-weight:600; }
.empty { text-align:center; color:#475569; padding:3rem 1rem; font-size:0.95rem; }

/* Event group */
.event-group { margin-bottom:1.5rem; }
.event-header { background:linear-gradient(135deg,#1a2a3a,#0f172a); border:1px solid #2a4a6a;
                border-radius:8px; padding:0.6rem 1rem; margin-bottom:0.6rem;
                display:flex; align-items:center; justify-content:space-between; gap:0.5rem; flex-wrap:wrap; }
.event-header .event-title { color:#38bdf8; font-size:0.9rem; font-weight:600; }
.event-header .event-count { color:#64748b; font-size:0.78rem; background:#1e293b;
                             padding:0.15rem 0.5rem; border-radius:4px; }
.event-header .event-sources { color:#64748b; font-size:0.72rem; width:100%; }
.event-group .article:last-child { margin-bottom:0; }

/* Toast */
.toast { position:fixed; bottom:2rem; right:2rem; background:#22c55e; color:#fff;
         padding:0.75rem 1.5rem; border-radius:8px; display:none; z-index:100;
         font-size:0.85rem; box-shadow:0 4px 12px rgba(0,0,0,0.3); }

/* Footer */
.footer { text-align:center; color:#334155; font-size:0.75rem; padding:2rem; }
"""

HEADER = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>航天动力监测</title>
<style>{CSS}</style>
</head>
<body>"""

FOOTER = """
<div class="toast" id="toast"></div>
<script>
async function markRead(id) {
  await fetch('/api/mark-read?id='+id, {method:'POST'});
  const el = document.getElementById('a-'+id);
  if (el) el.classList.remove('unread');
  const b = document.querySelector(`#a-${id} .badge`);
  if (b) b.remove();
  showToast('已标记为已读');
}
function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.style.display='block';
  setTimeout(()=>{t.style.display='none'}, 2000);
}
</script>
</body>
</html>"""


class NewsHandler(http.server.BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        log.debug(fmt % args)

    def _send_html(self, content: str, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    def _send_json(self, data: dict, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def _get_conn(self):
        return init_db()

    def _source_type(self, source: str) -> str:
        """Classify source as domestic (CN) or international."""
        domestic_keywords = ["采集", "国内", "百度", "新浪", "搜狐", "网易", "凤凰",
                             "观察者", "环球", "新华", "人民", "央视", "航天科技", "航天科工"]
        for kw in domestic_keywords:
            if kw in source:
                return "domestic"
        # Known international feeds
        intl_feeds = ["Defense News", "Spaceflight Now", "NASA", "Air Force Technology",
                      "UK Defence", "European Defence", "IEEE", "Air & Space",
                      "Phys.org", "Science Daily", "Space Intel", "SpaceRef", "Naval News",
                      "UK MOD", "Aviation Week",
                      "European Spaceflight", "Ars Technica", "JAXA",
                      "Universe Today", "Space.com", "The War Zone",
                      "Interesting Engineering", "arXiv",
                      "Military Times", "Navy Recognition", "FlightGlobal", "C4ISRNet"]
        for f in intl_feeds:
            if f.lower() in source.lower():
                return "international"
        # Default based on Chinese chars in source name
        import re
        if re.search(r"[一-鿿]", source):
            return "domestic"
        return "international"

    def _article_type(self, source: str) -> str:
        """Classify article as 论文 (paper) or 新闻 (news)."""
        paper_sources = ["arXiv", "cnki", "CNKI", "IEEE"]
        for s in paper_sources:
            if s.lower() in source.lower():
                return "paper"
        return "news"

    def _render_article(self, row) -> str:
        a_id = row[0]
        title = html.escape(row[1])
        url = html.escape(row[2])
        source = html.escape(row[3])
        published = html.escape(row[4] or "")
        summary = html.escape((row[6] or "")[:400])
        matched_kw = row[7] or ""
        relevance = row[8] or 0
        is_read = row[9]
        translated_title = html.escape(row[11] or "") if len(row) > 11 else ""
        translated_summary = html.escape((row[12] or "")[:400]) if len(row) > 12 else ""
        is_translated = row[13] if len(row) > 13 else 0
        author = html.escape(row[14] or "") if len(row) > 14 else ""
        affiliation = html.escape(row[15] or "") if len(row) > 15 else ""

        unread_cls = "" if is_read else "unread"
        unread_badge = "" if is_read else '<span class="badge">NEW</span>'
        cjk_tag = '<span class="translated-tag">中译</span>' if is_translated else ''

        s_type = self._source_type(row[3])
        s_type_label = "🇨🇳 国内" if s_type == "domestic" else "🌏 国际"
        s_type_tag = f'<span class="source-tag {s_type}">{s_type_label}</span>'

        # Article type tag
        art_type = self._article_type(row[3])
        type_tag = f'<span class="type-tag {art_type}">{"📄 论文" if art_type == "paper" else "📰 新闻"}</span>'

        # Score badge
        score_cls = "high" if relevance >= 60 else ("med" if relevance >= 25 else "low")
        score_badge = f'<span class="score {score_cls}">{relevance}</span>'

        kws = "".join(f'<span class="kw">{html.escape(k.strip())}</span>'
                      for k in matched_kw.split(",") if k.strip())

        pub_display = format_time_cn(published)

        display_title = translated_title or title
        orig_line = ""
        if translated_title and translated_title != title:
            orig_line = f'<div class="orig-title">原文: {title}</div>'
        display_summary = translated_summary or summary

        author_line = ""
        if author:
            author_line = f'<div class="author-line">👤 {author}'
            if affiliation:
                author_line += f' <span class="affiliation">📌 {affiliation}</span>'
            author_line += '</div>'

        return f"""
        <div class="article {unread_cls}" id="a-{a_id}">
          <div class="top-row">
            <div>
              {s_type_tag}
              <span class="source">{html.escape(source)}</span>
              {unread_badge}
              {cjk_tag}
            </div>
            <div style="display:flex;align-items:center;gap:0.5rem;">
              {type_tag}
              {score_badge}
              <span class="source">{pub_display}</span>
            </div>
          </div>
          <div class="title"><a href="/article?id={a_id}">{display_title}</a></div>
          {author_line}
          {orig_line}
          <div class="meta">{kws}</div>
          <div class="summary">{display_summary}</div>
          <div class="actions">
            <button onclick="markRead('{a_id}')">✓ 已读</button>
            <a href="{url}" target="_blank" rel="noopener">原文 →</a>
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
          <span class="event-title">📰 {display_title}</span>
          <span class="event-count">{count} 篇报道</span>
          <div class="event-sources">来源：{html.escape(source_str)}</div>
        </div>"""

    def _render_stats_bar(self, conn) -> str:
        total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        unread = conn.execute("SELECT COUNT(*) FROM articles WHERE is_read=0").fetchone()[0]
        translated = conn.execute("SELECT COUNT(*) FROM articles WHERE is_translated=1").fetchone()[0]
        today = conn.execute(
            "SELECT COUNT(*) FROM articles WHERE fetched_at > datetime('now', '-1 day')"
        ).fetchone()[0]
        return f"""
        <div class="stats-bar">
          <div class="stat-card"><span class="num">{total}</span><span class="label">总文章</span></div>
          <div class="stat-card"><span class="num orange">{unread}</span><span class="label">未读</span></div>
          <div class="stat-card"><span class="num purple">{translated}</span><span class="label">已翻译</span></div>
          <div class="stat-card"><span class="num green">{today}</span><span class="label">今日</span></div>
        </div>"""

    def _render_filter_tabs(self, current: str, base_url: str = "/") -> str:
        tabs = [
            ("all", "全部"),
            ("unread", "未读"),
            ("domestic", "🇨🇳 国内"),
            ("international", "🌏 国际"),
        ]
        links = []
        for key, label in tabs:
            active = "active" if key == current else ""
            if key == "all":
                href = base_url
            elif key in ("domestic", "international"):
                href = f"/{key}"
            else:
                href = f"/?{key}"
            links.append(f'<a href="{href}" class="{active}">{label}</a>')
        return f'<div class="filter-bar">{"".join(links)}</div>'

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        conn = self._get_conn()
        try:
            if path in ("/", "/index.html", "/unread", "/domestic", "/international"):
                page = int(params.get("page", [1])[0])
                limit = 30
                offset = (page - 1) * limit

                # Determine filter
                active_tab = "all"
                unread_only = False
                domestic_only = False
                international_only = False

                if path == "/unread":
                    active_tab = "unread"
                    unread_only = True
                elif path == "/domestic":
                    active_tab = "domestic"
                    domestic_only = True
                elif path == "/international":
                    active_tab = "international"
                    international_only = True

                # Build query
                where_clauses = []
                if unread_only:
                    where_clauses.append("is_read = 0")

                rows = get_articles(conn, limit=limit, offset=offset, unread_only=unread_only)

                # Filter by source type
                if domestic_only or international_only:
                    target = "domestic" if domestic_only else "international"
                    rows = [r for r in rows if self._source_type(r[3]) == target]

                total = conn.execute(
                    "SELECT COUNT(*) FROM articles" + (" WHERE is_read=0" if unread_only else "")
                ).fetchone()[0]

                # Start building page
                html_content = HEADER

                # Header
                html_content += f"""
                <div class="header">
                  <div class="header-top">
                    <div>
                      <h1>🚀 航天动力技术监测</h1>
                      <div class="subtitle">固体火箭发动机 · 冲压发动机 / 超燃冲压发动机</div>
                    </div>
                    <div class="header-actions">
                      <a href="/search">🔍 搜索</a>
                      <a href="http://47.103.207.227:8081" target="_blank">🎯 空空导弹</a>
                      <a href="#" onclick="location.reload();return false;">🔄 刷新</a>
                    </div>
                  </div>
                </div>"""

                # Stats bar
                html_content += self._render_stats_bar(conn)

                # Filter tabs
                html_content += self._render_filter_tabs(active_tab)

                # Articles (grouped by event)
                html_content += '<div class="container">'
                if not rows:
                    html_content += '<div class="empty">暂无文章 · 等待下一轮采集</div>'
                else:
                    # Group rows by event_group
                    groups = []  # [(event_group_id, event_title, [rows]), ...]
                    standalone = []
                    current_group = None
                    for row in rows:
                        eg = row[16] if len(row) > 16 else ""
                        if eg:
                            if current_group is not None and current_group[0] == eg:
                                current_group[2].append(row)
                            else:
                                if current_group is not None:
                                    groups.append(current_group)
                                et = row[17] if len(row) > 17 else ""
                                current_group = [eg, et, [row]]
                        else:
                            if current_group is not None:
                                groups.append(current_group)
                                current_group = None
                            standalone.append(row)
                    if current_group is not None:
                        groups.append(current_group)

                    # Sort groups by newest article date (descending)
                    def _group_newest(g):
                        newest = ""
                        for r in g[2]:
                            d = r[4] or ""
                            if d > newest:
                                newest = d
                        return newest
                    groups.sort(key=_group_newest, reverse=True)

                    # Render: events first, then standalone articles
                    for eg_id, eg_title, eg_rows in groups:
                        if len(eg_rows) > 1:
                            html_content += '<div class="event-group">'
                            html_content += self._render_event_header(eg_title, eg_rows)
                            for r in eg_rows:
                                html_content += self._render_article(r)
                            html_content += '</div>'
                        else:
                            # Single-article events render as standalone
                            standalone.append(eg_rows[0])

                    for row in standalone:
                        html_content += self._render_article(row)
                    # Pagination
                    if total > limit:
                        pages = (total + limit - 1) // limit
                        html_content += '<div class="pagination">'
                        if page > 1:
                            html_content += f'<a href="{path}?page={page-1}">←</a>'
                        for p in range(1, pages + 1):
                            cls = "active" if p == page else ""
                            html_content += f'<a href="{path}?page={p}" class="{cls}">{p}</a>'
                        if page < pages:
                            html_content += f'<a href="{path}?page={page+1}">→</a>'
                        html_content += '</div>'
                html_content += "</div>"
                html_content += FOOTER
                self._send_html(html_content)

            elif path == "/search":
                q = params.get("q", [""])[0]
                rows = search_articles(conn, q) if q else []
                html_content = HEADER
                html_content += f"""
                <div class="header"><div class="header-top">
                  <div><h1>🔍 搜索文章</h1></div>
                  <div class="header-actions"><a href="/">← 返回</a></div>
                </div></div>
                <div class="search-bar">
                  <form action="/search" method="get">
                    <input type="text" name="q" placeholder="搜索关键词..." value="{html.escape(q)}">
                    <button type="submit">搜索</button>
                  </form>
                </div>
                <div class="container">"""
                if not q:
                    html_content += '<div class="empty">输入关键词搜索文章</div>'
                elif not rows:
                    html_content += f'<div class="empty">未找到 "{html.escape(q)}" 的相关结果</div>'
                else:
                    html_content += f'<p style="color:#64748b;font-size:0.85rem;margin-bottom:1rem;">找到 {len(rows)} 条结果</p>'
                    for row in rows:
                        html_content += self._render_article(row)
                html_content += "</div>" + FOOTER
                self._send_html(html_content)

            elif path == "/article":
                a_id = params.get("id", [""])[0]
                if not a_id:
                    self._send_html(HEADER + '<div class="container"><div class="empty">缺少文章ID</div><a href="/" style="color:#38bdf8;">← 返回首页</a></div>' + FOOTER, 404)
                    return
                row = conn.execute("SELECT * FROM articles WHERE id=?", (a_id,)).fetchone()
                if not row:
                    self._send_html(HEADER + '<div class="container"><div class="empty">文章不存在</div><a href="/" style="color:#38bdf8;">← 返回首页</a></div>' + FOOTER, 404)
                    return

                art_title = html.escape(row[1])
                art_url = html.escape(row[2])
                art_source = html.escape(row[3])
                art_pub = html.escape(row[4] or "")
                art_summary = html.escape(row[6] or "")
                art_kw = html.escape(row[7] or "")
                art_relevance = row[8] or 0
                art_trans_title = html.escape(row[11] or "") if len(row) > 11 else ""
                art_trans_summary = html.escape(row[12] or "") if len(row) > 12 else ""
                art_is_translated = row[13] if len(row) > 13 else 0
                art_author = html.escape(row[14] or "") if len(row) > 14 else ""
                art_affiliation = html.escape(row[15] or "") if len(row) > 15 else ""

                pub_display = format_time_cn(art_pub)

                score_cls = "high" if art_relevance >= 60 else ("med" if art_relevance >= 25 else "low")
                kws = "".join(f'<span class="kw">{html.escape(k.strip())}</span>'
                             for k in art_kw.split(",") if k.strip())

                display_title = art_trans_title or art_title

                art_type = self._article_type(row[3])
                art_type_tag = f'<span class="type-tag {art_type}">{"📄 论文" if art_type == "paper" else "📰 新闻"}</span>'

                html_content = HEADER
                html_content += f"""
                <div class="header"><div class="header-top">
                  <div><h1>📄 文章详情</h1></div>
                  <div class="header-actions"><a href="/">← 返回</a></div>
                </div></div>
                <div class="container">
                  <div class="article" style="border-left:3px solid #38bdf8;">
                    <div class="top-row">
                      <div>
                        <span class="source">{art_source}</span>
                        {'<span class="translated-tag">中译</span>' if art_is_translated else ''}
                      </div>
                      <div style="display:flex;align-items:center;gap:0.5rem;">
                        {art_type_tag}
                        <span class="score {score_cls}">{art_relevance}</span>
                        <span class="source">{pub_display}</span>
                      </div>
                    </div>
                    {('<div class="author-line" style="margin:0.4rem 0;">👤 ' + art_author + (' <span class="affiliation">' + art_affiliation + '</span>' if art_affiliation else '') + '</div>') if art_author else ''}
                    <h2 style="font-size:1.3rem;margin:0.8rem 0 0.3rem;line-height:1.5;">{display_title}</h2>"""

                if art_trans_title and art_trans_title != art_title:
                    html_content += f'<div style="color:#94a3b8;font-size:0.85rem;margin-bottom:0.8rem;border-left:2px solid #334155;padding-left:0.6rem;">原文标题: {art_title}</div>'

                html_content += f'<div style="margin:0.5rem 0;">{kws}</div>'

                # Build full article content: prefer cached full text, fallback to summary
                snapshot_path_html = Path(config.ARCHIVE_DIR) / f"{a_id}.html"
                snapshot_path_txt = Path(config.ARCHIVE_DIR) / f"{a_id}.txt"
                full_content = ""
                has_full_content = False

                # Try .html first (current save_snapshot format), then .txt (legacy)
                for sp in [snapshot_path_html, snapshot_path_txt]:
                    if sp.exists():
                        try:
                            raw = sp.read_text(encoding="utf-8").strip()
                            # Strip HTML wrapper if present (save_snapshot wraps in HTML)
                            m = re.search(r"<pre[^>]*>(.*?)</pre>", raw, re.DOTALL)
                            full_content = (m.group(1) if m else raw).strip()[:10000]
                            if full_content:
                                has_full_content = True
                                break
                        except Exception:
                            pass

                if has_full_content:
                    # Show full translated/original content
                    if art_trans_summary:
                        html_content += f'<div style="font-size:0.85rem;color:#64748b;margin-bottom:0.5rem;">📝 翻译摘要</div>'
                        html_content += f'<div style="font-size:0.95rem;line-height:1.8;color:#cbd5e1;margin:1rem 0;white-space:pre-wrap;">{art_trans_summary}</div>'
                    full_escaped = html.escape(full_content)
                    html_content += f'<div style="font-size:0.9rem;line-height:1.7;color:#94a3b8;margin:1rem 0;padding:1rem;background:#0f172a;border-radius:8px;border:1px solid #1e293b;white-space:pre-wrap;">{full_escaped}</div>'
                    if art_trans_summary != art_summary and art_summary:
                        html_content += f'<details style="margin:0.5rem 0 1.5rem;"><summary style="color:#64748b;cursor:pointer;font-size:0.85rem;">原文摘要（{ "英文" if not art_trans_title else "原文"}）</summary>'
                        html_content += f'<div style="color:#94a3b8;font-size:0.85rem;line-height:1.6;margin-top:0.3rem;white-space:pre-wrap;">{art_summary}</div>'
                        html_content += f'</details>'
                else:
                    # No cached full text — show the best available content
                    if art_trans_summary:
                        html_content += f'<div style="font-size:0.95rem;line-height:1.8;color:#cbd5e1;margin:1rem 0;white-space:pre-wrap;">{art_trans_summary}</div>'
                        if art_trans_summary != art_summary and art_summary:
                            html_content += f'<details style="margin:0.5rem 0 1.5rem;" open>'
                            html_content += f'<summary style="color:#64748b;cursor:pointer;font-size:0.85rem;margin-bottom:0.3rem;">原文摘要（英文）</summary>'
                            html_content += f'<div style="color:#94a3b8;font-size:0.85rem;line-height:1.6;white-space:pre-wrap;">{art_summary}</div>'
                            html_content += f'</details>'
                    else:
                        html_content += f'<div style="font-size:0.95rem;line-height:1.8;color:#cbd5e1;margin:1rem 0;white-space:pre-wrap;">{art_summary}</div>'

                html_content += f"""
                    <div class="actions" style="margin-top:1.5rem;">
                      <a href="{art_url}" target="_blank" rel="noopener" style="display:inline-block;background:#38bdf8;color:#0b1121;padding:0.5rem 1.2rem;border-radius:6px;font-weight:600;text-decoration:none;">📄 查看原文 →</a>
                    </div>
                  </div>
                </div>
                """ + FOOTER
                self._send_html(html_content)

            elif path == "/api/stats":
                total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
                unread = conn.execute("SELECT COUNT(*) FROM articles WHERE is_read=0").fetchone()[0]
                recent = conn.execute(
                    "SELECT COUNT(*) FROM articles WHERE fetched_at > datetime('now', '-1 day')"
                ).fetchone()[0]
                translated = conn.execute(
                    "SELECT COUNT(*) FROM articles WHERE is_translated=1"
                ).fetchone()[0]
                keywords = conn.execute(
                    "SELECT matched_kw FROM articles WHERE matched_kw != '' ORDER BY fetched_at DESC LIMIT 100"
                ).fetchall()
                kw_count = {}
                for (kw_str,) in keywords:
                    for k in kw_str.split(","):
                        k = k.strip()
                        if k:
                            kw_count[k] = kw_count.get(k, 0) + 1
                top_kw = sorted(kw_count.items(), key=lambda x: -x[1])[:20]
                self._send_json({
                    "total": total, "unread": unread, "last_24h": recent,
                    "translated": translated,
                    "top_keywords": [{"kw": k, "count": c} for k, c in top_kw],
                })

            elif path == "/api/articles":
                page = int(params.get("page", [1])[0])
                unread_only = "unread" in params
                offset = (page - 1) * 30
                rows = get_articles(conn, limit=30, offset=offset, unread_only=unread_only)
                articles = [
                    {
                        "id": r[0], "title": r[1], "url": r[2], "source": r[3],
                        "published": r[4], "summary": (r[6] or "")[:300],
                        "matched_kw": r[7], "is_read": bool(r[9]),
                    }
                    for r in rows
                ]
                self._send_json({"articles": articles, "page": page})

            else:
                self._send_html(HEADER + '<div class="container"><h2 style="color:#475569;">404</h2><a href="/" style="color:#38bdf8;">← 返回首页</a></div>' + FOOTER, 404)
        finally:
            conn.close()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        conn = self._get_conn()
        try:
            if parsed.path == "/api/mark-read":
                a_id = params.get("id", [""])[0]
                if a_id:
                    mark_read(conn, a_id)
                    self._send_json({"ok": True})
                else:
                    self._send_json({"ok": False, "error": "missing id"}, 400)

            elif parsed.path == "/api/collect":
                content_len = int(self.headers.get("Content-Length", 0))
                if content_len == 0:
                    self._send_json({"ok": False, "error": "empty body"}, 400)
                    return
                body = self.rfile.read(content_len).decode("utf-8")
                data = json.loads(body)
                api_key = data.get("api_key", "")
                if config.COLLECTOR_API_KEY and api_key != config.COLLECTOR_API_KEY:
                    self._send_json({"ok": False, "error": "invalid api key"}, 403)
                    return
                articles = data.get("articles", [])
                saved = 0
                for art in articles:
                    from monitor import make_article_id, article_exists
                    art["id"] = make_article_id(art["url"], art["title"])
                    if article_exists(conn, art["id"]):
                        continue
                    art["fetched_at"] = datetime.now(timezone.utc).isoformat()
                    art.setdefault("matched_kw", "")
                    art.setdefault("relevance", 0)
                    art.setdefault("summary", "")
                    art.setdefault("translated_title", "")
                    art.setdefault("translated_summary", "")
                    from monitor import save_article
                    if save_article(conn, art):
                        saved += 1
                self._send_json({"ok": True, "saved": saved})

            else:
                self._send_json({"ok": False, "error": "not found"}, 404)
        finally:
            conn.close()


def run(host: str = None, port: int = None):
    host = host or config.DASHBOARD_HOST
    port = port or config.DASHBOARD_PORT
    server = http.server.HTTPServer((host, port), NewsHandler)
    log.info(f"Dashboard running at http://{host if host != '0.0.0.0' else 'localhost'}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    run()
