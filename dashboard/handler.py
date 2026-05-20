"""Dashboard HTTP request handler."""
import html
import http.server
import json
import re
import sqlite3
import threading
import urllib.parse
from collections import Counter


def _safe_href(url: str) -> str:
    """Return url only if it's a safe http/https link (prevents javascript: XSS)."""
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme in ("http", "https"):
            return url
    except Exception:
        pass
    return ""
from datetime import datetime
from pathlib import Path
from typing import Optional

from monitor import (
    fetch_article_content, get_articles, get_articles_by_month,
    get_articles_for_briefing, get_available_months, get_event_grouped_articles,
    get_source_status, mark_read, search_articles,
)

from .render import (
    format_time_cn, get_css, get_header, render_footer, render_article, render_event_header,
)
from .state import BASE_DIR, THEMES, log, _poll_lock, _poll_status


def init_db_for_theme(theme_name: str) -> sqlite3.Connection:
    """Initialize theme-specific database."""
    t = THEMES[theme_name]
    db_path = BASE_DIR / "data" / f"{t.db_name}.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id                TEXT PRIMARY KEY,
            title             TEXT NOT NULL,
            url               TEXT NOT NULL,
            source            TEXT DEFAULT '',
            published         TEXT,
            fetched_at        TEXT NOT NULL,
            summary           TEXT DEFAULT '',
            matched_kw        TEXT DEFAULT '',
            relevance         INTEGER DEFAULT 0,
            is_read           INTEGER DEFAULT 0,
            is_archived       INTEGER DEFAULT 0,
            translated_title  TEXT DEFAULT '',
            translated_summary TEXT DEFAULT '',
            is_translated     INTEGER DEFAULT 0,
            author            TEXT DEFAULT '',
            affiliation       TEXT DEFAULT '',
            event_group       TEXT DEFAULT '',
            event_title       TEXT DEFAULT '',
            translated_content TEXT DEFAULT '',
            image_url         TEXT DEFAULT '',
            content           TEXT DEFAULT '',
            article_type      TEXT DEFAULT ''
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_articles_published
        ON articles(published)
    """)
    for col_spec in [
        ("translated_title", "TEXT DEFAULT ''"),
        ("translated_summary", "TEXT DEFAULT ''"),
        ("is_translated", "INTEGER DEFAULT 0"),
        ("author", "TEXT DEFAULT ''"),
        ("affiliation", "TEXT DEFAULT ''"),
        ("event_group", "TEXT DEFAULT ''"),
        ("event_title", "TEXT DEFAULT ''"),
        ("translated_content", "TEXT DEFAULT ''"),
        ("image_url", "TEXT DEFAULT ''"),
        ("content", "TEXT DEFAULT ''"),
        ("article_type", "TEXT DEFAULT ''"),
        ("is_starred", "INTEGER DEFAULT 0"),
    ]:
        try:
            conn.execute(f"SELECT {col_spec[0]} FROM articles LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute(f"ALTER TABLE articles ADD COLUMN {col_spec[0]} {col_spec[1]}")
    conn.commit()

    # poll_stats table
    try:
        conn.execute("SELECT 1 FROM poll_stats LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("""CREATE TABLE IF NOT EXISTS poll_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            duration_sec INTEGER NOT NULL,
            articles_found INTEGER NOT NULL,
            sources_count INTEGER NOT NULL
        )""")
        conn.commit()

    # source_stats table
    try:
        conn.execute("SELECT 1 FROM source_stats LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("""CREATE TABLE IF NOT EXISTS source_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_name TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            success INTEGER NOT NULL DEFAULT 1,
            articles_found INTEGER NOT NULL DEFAULT 0,
            error_msg TEXT DEFAULT ''
        )""")
        conn.commit()

    # source_config table
    try:
        conn.execute("SELECT 1 FROM source_config LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("""CREATE TABLE IF NOT EXISTS source_config (
            source_name TEXT PRIMARY KEY,
            consecutive_failures INTEGER NOT NULL DEFAULT 0,
            disabled INTEGER NOT NULL DEFAULT 0,
            last_success_at TEXT DEFAULT '',
            last_error TEXT DEFAULT ''
        )""")
        conn.commit()

    return conn


class DashboardHandler(http.server.BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        log.info(f"{self.client_address[0]} - {fmt % args}")

    def _send_html(self, html_content: str, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html_content.encode("utf-8"))

    def _send_json(self, data: dict):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _archive_dir(self, theme_name: str) -> Path:
        return BASE_DIR / "snapshots" / theme_name

    @property
    def prefix(self) -> str:
        return "/aam" if getattr(self, "_theme", "news") == "aam" else ""

    def _set_theme_from_path(self, path: str):
        if path.startswith("/aam"):
            self._theme = "aam"
        else:
            self._theme = "news"

    # ── Page handlers ─────────────────────────────────────────────────

    def _handle_page(self, params: dict):
        theme_name = self._theme
        t = THEMES[theme_name]
        page = int(params.get("page", "1"))
        limit = 50
        offset = (page - 1) * limit
        unread_only = params.get("unread", "") == "1"
        starred_only = params.get("starred", "") == "1"
        type_filter = params.get("type", "")
        prefix = self.prefix

        extra_conds = []
        extra_params: list = []
        if unread_only:
            extra_conds.append("is_read=0")
        if starred_only:
            extra_conds.append("is_starred=1")
        if type_filter in ("paper", "news"):
            extra_conds.append("article_type=?")
            extra_params.append(type_filter)
        type_cond = (" AND " + " AND ".join(extra_conds)) if extra_conds else ""

        conn = init_db_for_theme(theme_name)
        try:
            total = conn.execute("SELECT COUNT(*) FROM articles WHERE 1=1" + type_cond, extra_params).fetchone()[0]
            total_pages = max(1, (total + limit - 1) // limit)

            html_content = '<div class="container">'

            # Stats
            all_count = conn.execute("SELECT COUNT(*) FROM articles WHERE 1=1" + type_cond, extra_params).fetchone()[0]
            unread_count = conn.execute("SELECT COUNT(*) FROM articles WHERE 1=1" + type_cond + " AND is_read=0", extra_params).fetchone()[0]
            last_24h = conn.execute("SELECT COUNT(*) FROM articles WHERE fetched_at > datetime('now', '-1 day')" + type_cond, extra_params).fetchone()[0]

            poll_row = conn.execute(
                "SELECT duration_sec FROM poll_stats ORDER BY id DESC LIMIT 1"
            ).fetchone()
            poll_footer = f'<div class="footer-stat"><a href="{prefix}/sources">数据源列表</a></div>'
            if poll_row:
                dur = poll_row[0]
                if dur < 60:
                    dur_str = f"{dur}秒"
                else:
                    dur_str = f"{dur//60}分{dur%60}秒"
                poll_footer = f'<div class="footer-stat">上次采集耗时 {dur_str} · <a href="{prefix}/sources">数据源列表</a></div>'

            html_content += f"""
            <div class="stats-bar">
              <div class="stat-card"><span class="num">{all_count}</span><span class="label">总计</span></div>
              <div class="stat-card"><span class="num">{unread_count}</span><span class="label">未读</span></div>
              <div class="stat-card"><span class="num green">{last_24h}</span><span class="label">最近24h</span></div>
            </div>"""

            # Articles
            if t.has_event_grouping:
                grouped = get_event_grouped_articles(conn, limit=limit, offset=offset, unread_only=unread_only, starred_only=starred_only, type_filter=type_filter)
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

                for eg_id, first_row, eg_rows in event_groups:
                    if len(eg_rows) > 1:
                        html_content += '<div class="event-group">'
                        eg_title = first_row[17] if len(first_row) > 17 else ""
                        html_content += render_event_header(eg_title or "", eg_rows, t)
                        for r in eg_rows:
                            html_content += render_article(r, t, theme_name)
                        html_content += '</div>'
                    else:
                        standalone.append(eg_rows[0])

                for row in standalone:
                    html_content += render_article(row, t, theme_name)
            else:
                rows = get_articles(conn, limit=limit, offset=offset, unread_only=unread_only, starred_only=starred_only, type_filter=type_filter)
                for row in rows:
                    html_content += render_article(row, t, theme_name)

            # Pagination
            if total_pages > 1:
                html_content += '<div class="pagination">'
                for p in range(max(1, page - 5), min(total_pages, page + 5) + 1):
                    active = "active" if p == page else ""
                    url = f"{prefix}/?page={p}" if prefix else f"/?page={p}"
                    if unread_only:
                        url += "&unread=1"
                    if starred_only:
                        url += "&starred=1"
                    if type_filter:
                        url += f"&type={type_filter}"
                    html_content += f'<a href="{url}" class="{active}">{p}</a>'
                html_content += '</div>'

            html_content += '</div>'
            html_content += poll_footer

            # Script
            html_content += """
            <div id="toast" class="toast"></div>
            <script>
            function getPrefix() {
              var p = window.location.pathname;
              return p.startsWith('/aam') ? '/aam' : '';
            }

            function setActiveNav() {
              var params = new URLSearchParams(window.location.search);
              var links = document.querySelectorAll('.header-nav a');
              links.forEach(function(a) {
                a.classList.remove('active');
                var href = a.getAttribute('href');
                if (href.indexOf('unread=1') !== -1 && params.get('unread') === '1') a.classList.add('active');
                else if (href.indexOf('starred=1') !== -1 && params.get('starred') === '1') a.classList.add('active');
                else if (href.indexOf('search=1') !== -1 && params.get('search') === '1') a.classList.add('active');
                else if (href.indexOf('type=paper') !== -1 && params.get('type') === 'paper') a.classList.add('active');
                else if (href.indexOf('type=news') !== -1 && params.get('type') === 'news') a.classList.add('active');
                else if (!href.includes('?') && !params.has('unread') && !params.has('starred') && !params.has('search') && !params.has('type')) a.classList.add('active');
              });
            }
            setActiveNav();

            function toggleRead(id) {
              var prefix = getPrefix();
              fetch(prefix + "/mark-read?id=" + id).then(r => r.json()).then(d => {
                if (d.ok) {
                  var el = document.querySelector('.article[data-id="' + id + '"]');
                  if (el) {
                    el.classList.toggle('unread');
                    el.classList.toggle('read');
                    var btns = el.querySelectorAll('.actions button');
                    for (var i = 0; i < btns.length; i++) {
                      if (btns[i].textContent.indexOf('标为') !== -1) {
                        btns[i].textContent = d.is_read ? '标为未读' : '标为已读';
                      }
                    }
                  }
                  showToast(d.msg);
                }
              });
            }

            function expandSummary(id) {
              var s = document.getElementById('s-' + id);
              var e = document.getElementById('e-' + id);
              if (s) s.classList.remove('collapsed');
              if (e) e.style.display = 'none';
            }

            function triggerPoll() {
              var prefix = getPrefix();
              var btn = document.getElementById('poll-btn');
              btn.textContent = '采集中...';
              btn.disabled = true;
              fetch(prefix + "/trigger-poll", {method:'POST'}).then(r => r.json()).then(d => {
                showToast(d.msg || (d.ok ? '采集已开始' : '采集失败'));
                btn.textContent = '手动采集';
                btn.disabled = false;
              });
            }

            function toggleStar(id) {
              var prefix = getPrefix();
              fetch(prefix + "/toggle-star?id=" + id).then(r => r.json()).then(d => {
                if (d.ok) {
                  var el = document.querySelector('.article[data-id="' + id + '"]');
                  if (el) {
                    var btn = el.querySelector('.star-btn');
                    btn.textContent = d.is_starred ? '★' : '☆';
                    btn.classList.toggle('active');
                  }
                  showToast(d.msg);
                }
              });
            }

            function showToast(msg) {
              var t = document.getElementById('toast');
              t.textContent = '✅ ' + msg;
              t.style.display = 'block';
              setTimeout(function() { t.style.display = 'none'; }, 2000);
            }
            </script>
            """

            self._send_html(get_header(t, theme_name) + html_content + render_footer(self.prefix))
        finally:
            conn.close()

    def _handle_article(self, params: dict):
        theme_name = self._theme
        t = THEMES[theme_name]
        from theme import AAM, NEWS
        from monitor import article_type
        article_id = params.get("id", "")
        if not article_id:
            self._send_html(get_header(t) + f'<div class="container"><div class="empty">缺少文章ID</div><a href="/" style="color:{t.dashboard_color_primary};">← 返回首页</a></div>' + render_footer(self.prefix), 404)
            return

        conn = init_db_for_theme(theme_name)
        try:
            row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
            if not row:
                self._send_html(get_header(t) + f'<div class="container"><div class="empty">文章不存在</div><a href="/" style="color:{t.dashboard_color_primary};">← 返回首页</a></div>' + render_footer(self.prefix), 404)
                return

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
            art_content = row[20] if len(row) > 20 and row[20] else ""

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

            author_line = ""
            if art_author:
                author_line = f'<p style="color:#94a3b8;font-size:0.85rem;margin:0.3rem 0;">作者: {html.escape(art_author)}</p>'
            if art_affiliation:
                author_line += f'<p style="color:#64748b;font-size:0.8rem;margin:0.3rem 0;">机构: {html.escape(art_affiliation)}</p>'

            # Content
            content_html = ""
            if art_trans_content:
                content_html = f"""
                <div style="margin-top:2rem;padding-top:1.5rem;border-top:1px solid #334155;">
                  <h3 style="color:#e2e8f0;font-size:1rem;margin-bottom:0.8rem;">全文翻译</h3>
                  <div style="color:#94a3b8;font-size:0.88rem;line-height:1.8;white-space:pre-wrap;">{html.escape(art_trans_content)}</div>
                </div>"""
            elif art_content:
                content_html = f"""
                <div style="margin-top:2rem;padding-top:1.5rem;border-top:1px solid #334155;">
                  <h3 style="color:#e2e8f0;font-size:1rem;margin-bottom:0.8rem;">原文内容</h3>
                  <div style="color:#94a3b8;font-size:0.88rem;line-height:1.8;white-space:pre-wrap;">{html.escape(art_content[:10000])}</div>
                </div>"""
            else:
                snap = self._archive_dir(theme_name) / f"{art_id}.html"
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
                else:
                    live = fetch_article_content(art_url, timeout=10)
                    if live and live.get("text"):
                        text = live["text"]
                        content_html = f"""
                        <div style="margin-top:2rem;padding-top:1.5rem;border-top:1px solid #334155;">
                          <h3 style="color:#e2e8f0;font-size:1rem;margin-bottom:0.8rem;">原文内容</h3>
                          <div style="color:#94a3b8;font-size:0.88rem;line-height:1.8;white-space:pre-wrap;">{html.escape(text[:10000])}</div>
                        </div>"""

            art_prefix = "" if theme_name == "news" else "/aam"
            title_tag = f"<title>{html.escape(display_title[:80])} - {t.dashboard_title}</title>"
            article_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
{title_tag}
<style>{get_css(t)}</style>
</head>
<body>
<a class="theme-badge" href="{AAM.dashboard_title if theme_name == 'news' else '/'}" style="position:fixed;top:12px;right:12px;z-index:999;display:flex;align-items:center;gap:4px;padding:4px 10px;border-radius:20px;font-size:0.75rem;font-weight:600;text-decoration:none;background:rgba(15,23,42,0.85);backdrop-filter:blur(4px);border:1px solid {t.dashboard_other_theme_color};color:{t.dashboard_other_theme_color};transition:all 0.2s;">{(AAM if theme_name == 'news' else NEWS).app_name_cn} →</a>
<div class="header">
<div class="header-top">
<div>
<h1><a href="{art_prefix}/" style="color:{t.dashboard_color_primary};text-decoration:none;">{t.app_name_cn}</a></h1>
</div>
<div class="header-actions">
<span class="nav-group">
<a href="{art_prefix}/" class="active">全部</a>
<a href="{art_prefix}/?unread=1">未读</a>
<a href="{art_prefix}/?search=1">搜索</a>
<a href="{art_prefix}/?type=paper">论文</a>
<a href="{art_prefix}/?type=news">新闻</a>
</span>
</div>
</div>
</div>
<div class="container" style="max-width:800px;">
<div class="article" style="border-left:3px solid {t.dashboard_color_primary};">

<div class="top-row">
<div class="source">
<span class="source-tag {source_tag_class}">{source_tag}</span>
{html.escape(art_source)} · {art_published}
</div>
<div>
<span class="score {'high' if art_relevance >= 50 else 'med' if art_relevance >= 20 else 'low'}">{art_relevance}</span>
{'<span class="translated-tag">中译</span>' if art_is_translated or art_trans_content else ''}
{'<span class="type-tag paper">论文</span> ' if article_type(art_source, art_url, art_author) == "paper" else '<span class="type-tag news">新闻</span> '}
</div>
</div>

<h2 style="color:#e2e8f0;font-size:1.2rem;margin:0.6rem 0 0.2rem;line-height:1.5;">{html.escape(display_title)}</h2>
{orig_line}
{author_line}
{f'<img src="{html.escape(art_image_url)}" alt="" style="max-width:100%;max-height:400px;border-radius:8px;margin:0.8rem 0;border:1px solid #334155;">' if art_image_url else ''}

<div style="margin:0.5rem 0;">
{kw_html}
</div>

<div style="color:#94a3b8;font-size:0.9rem;line-height:1.7;margin:1rem 0;">{html.escape(display_summary)}</div>

<div style="margin-top:1.5rem;">
{f'<a href="{html.escape(_safe_href(art_url))}" target="_blank" rel="noopener" style="display:inline-block;background:#1e293b;color:{t.dashboard_color_primary};border:1px solid {t.dashboard_color_primary};padding:0.5rem 1.2rem;border-radius:6px;font-weight:600;text-decoration:none;">查看原文</a>' if _safe_href(art_url) else '<span style="color:#64748b;font-size:0.85rem;">链接不可用</span>'}
<a href="{art_prefix}/" style="margin-left:1rem;color:#94a3b8;">← 返回首页</a>
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
        theme_name = self._theme
        t = THEMES[theme_name]
        q = params.get("q", "")
        page = int(params.get("page", "1"))
        limit = 50
        offset = (page - 1) * limit
        prefix = self.prefix

        conn = init_db_for_theme(theme_name)
        try:
            if q:
                rows, total = search_articles(conn, q, limit=limit, offset=offset)
            else:
                rows = []
                total = 0

            html_content = '<div class="container">'

            html_content += f"""
            <div class="search-bar">
            <form action="{prefix}/" method="get">
            <input type="hidden" name="search" value="1">
            <input type="text" name="q" placeholder="搜索文章标题或摘要..." value="{html.escape(q)}">
            <button type="submit">搜索</button>
            </form>
            </div>"""

            if q:
                html_content += f'<div style="padding:0.5rem 0;color:#64748b;font-size:0.85rem;">找到 {total} 条结果</div>'
                for row in rows:
                    html_content += render_article(row, t, theme_name, highlight=q)
                if not rows:
                    html_content += '<div class="empty">未找到匹配的文章</div>'

                total_pages = max(1, (total + limit - 1) // limit)
                if total_pages > 1:
                    html_content += '<div class="pagination">'
                    for p in range(max(1, page - 5), min(total_pages, page + 5) + 1):
                        active = "active" if p == page else ""
                        html_content += f'<a href="{prefix}/?search=1&q={urllib.parse.quote(q)}&page={p}" class="{active}">{p}</a>'
                    html_content += '</div>'
            else:
                html_content += '<div class="empty">输入关键词搜索文章</div>'

            html_content += '</div>'
            self._send_html(get_header(t, theme_name) + html_content + render_footer(self.prefix))
        finally:
            conn.close()

    def _handle_mark_read(self, params: dict):
        theme_name = self._theme
        article_id = params.get("id", "")
        conn = init_db_for_theme(theme_name)
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

    def _handle_toggle_star(self, params: dict):
        theme_name = self._theme
        article_id = params.get("id", "")
        conn = init_db_for_theme(theme_name)
        try:
            row = conn.execute("SELECT is_starred FROM articles WHERE id = ?", (article_id,)).fetchone()
            if row:
                new_val = 0 if row[0] else 1
                conn.execute("UPDATE articles SET is_starred = ? WHERE id = ?", (new_val, article_id))
                conn.commit()
                self._send_json({"ok": True, "msg": "已收藏" if new_val else "取消收藏", "is_starred": new_val})
            else:
                self._send_json({"ok": False, "msg": "文章不存在"})
        finally:
            conn.close()

    def _handle_trigger_poll(self):
        theme_name = self._theme
        log.info(f"Manual poll triggered for {theme_name}")

        def _run_poll():
            try:
                from monitor import run
                run(dry_run=False, skip_llm=False)
                log.info(f"Manual poll completed for {theme_name}")
            except Exception as e:
                log.error(f"Manual poll failed for {theme_name}: {e}")

        t = threading.Thread(target=_run_poll, daemon=True)
        t.start()
        self._send_json({"ok": True, "msg": "采集已开始，请等待完成"})

    def _handle_poll_history(self, params: dict):
        theme_name = self._theme
        t = THEMES[theme_name]
        prefix = self.prefix
        conn = init_db_for_theme(theme_name)
        try:
            rows = conn.execute(
                "SELECT id, started_at, duration_sec, articles_found, sources_count "
                "FROM poll_stats ORDER BY id DESC LIMIT 100"
            ).fetchall()

            html_content = f'<div class="container"><h2 style="margin-bottom:1rem;">采集历史统计</h2>'

            if rows:
                total_articles = sum(r[3] for r in rows)
                avg_duration = sum(r[2] for r in rows) // len(rows)
                html_content += f"""
                <div class="stats-bar">
                  <div class="stat-card"><span class="num">{len(rows)}</span><span class="label">采集轮次</span></div>
                  <div class="stat-card"><span class="num">{total_articles}</span><span class="label">总文章数</span></div>
                  <div class="stat-card"><span class="num orange">{avg_duration}秒</span><span class="label">平均耗时</span></div>
                </div>"""

                html_content += """
                <table style="width:100%;border-collapse:collapse;font-size:0.85rem;">
                <thead>
                <tr style="color:#64748b;border-bottom:1px solid #3b4a5a;">
                  <th style="padding:0.5rem;text-align:left;">时间</th>
                  <th style="padding:0.5rem;text-align:right;">耗时</th>
                  <th style="padding:0.5rem;text-align:right;">新文章</th>
                  <th style="padding:0.5rem;text-align:right;">数据源数</th>
                  <th style="padding:0.5rem;text-align:right;">每源文章数</th>
                </tr>
                </thead><tbody>"""

                for row in rows:
                    _, started_at, duration_sec, articles_found, sources_count = row
                    started_display = started_at[:19] if started_at else "?"
                    if duration_sec < 60:
                        dur_str = f"{duration_sec}秒"
                    else:
                        dur_str = f"{duration_sec//60}分{duration_sec%60}秒"
                    per_source = round(articles_found / max(sources_count, 1), 1)
                    bar_width = min(articles_found * 2, 100)
                    html_content += f"""
                    <tr style="border-bottom:1px solid #2a3a4a;">
                      <td style="padding:0.5rem;color:#94a3b8;">{started_display}</td>
                      <td style="padding:0.5rem;text-align:right;color:#e2e8f0;">{dur_str}</td>
                      <td style="padding:0.5rem;text-align:right;color:#22c55e;">
                        {articles_found}
                        <div style="width:100px;height:6px;background:#2a3a4a;border-radius:3px;margin-left:auto;margin-top:2px;">
                          <div style="width:{bar_width}%;height:6px;background:#22c55e;border-radius:3px;"></div>
                        </div>
                      </td>
                      <td style="padding:0.5rem;text-align:right;color:#94a3b8;">{sources_count}</td>
                      <td style="padding:0.5rem;text-align:right;color:#94a3b8;">{per_source}</td>
                    </tr>"""
                html_content += "</tbody></table>"
            else:
                html_content += '<div class="empty">暂无采集记录</div>'

            html_content += f'<div style="text-align:center;padding:1rem 0;"><a href="{prefix}/" style="color:{t.dashboard_color_primary};font-size:0.85rem;">← 返回首页</a></div>'
            html_content += '</div>'
            self._send_html(get_header(t, theme_name) + html_content + render_footer(self.prefix))
        finally:
            conn.close()

    def _handle_sources(self, params: dict):
        theme_name = self._theme
        t = THEMES[theme_name]
        prefix = self.prefix

        conn = init_db_for_theme(theme_name)
        try:
            status_map = {}
            for row in get_source_status(conn):
                status_map[row["source_name"]] = row
            # Load source_config (disabled status, consecutive failures)
            config_map: dict[str, dict] = {}
            try:
                for cr in conn.execute("SELECT source_name, disabled, consecutive_failures FROM source_config").fetchall():
                    config_map[cr[0]] = {"disabled": cr[1], "consecutive_failures": cr[2]}
            except Exception:
                pass
        finally:
            conn.close()

        sources = list(t.rss_sources.items())
        categorized = {"国内媒体": [], "外媒新闻": [], "学术期刊": [], "其他": []}
        for name, url in sorted(sources, key=lambda x: x[0].lower()):
            has_cjk = bool(re.search(r"[一-鿿]", name))
            is_cnki = "cnki" in url.lower() or "CNKI" in name
            is_rsshub = "localhost:1200" in url
            is_arxiv = "arxiv" in url.lower()
            is_springer = "springer" in url.lower()
            is_sciencedirect = "sciencedirect" in url.lower()
            is_tandf = "tandfonline" in url.lower()
            is_aiaa = "aiaa" in url.lower()
            is_fpo = "freepatentsonline" in url.lower()
            if is_cnki or is_arxiv or is_springer or is_sciencedirect or is_tandf or is_aiaa or is_fpo:
                categorized["学术期刊"].append((name, url))
            elif has_cjk or is_rsshub:
                categorized["国内媒体"].append((name, url))
            else:
                categorized["外媒新闻"].append((name, url))

        items = ""
        for cat in ["国内媒体", "外媒新闻", "学术期刊", "其他"]:
            if not categorized[cat]:
                continue
            items += f'<div style="color:{t.dashboard_color_primary};font-size:0.85rem;font-weight:600;margin:0.8rem 0 0.3rem 0;">{cat} ({len(categorized[cat])})</div>'
            for name, url in categorized[cat]:
                st = status_map.get(name)
                sc = config_map.get(name)
                sc_disabled = sc and sc["disabled"]

                if sc_disabled:
                    health = f'<span class="source-status-disabled">⛔ 已禁用（连续{sc["consecutive_failures"]}次失败）<a href="{prefix}/enable-source?name={urllib.parse.quote(name)}" style="color:{t.dashboard_color_primary};font-size:0.7rem;margin-left:0.3rem;">重新启用</a></span>'
                elif st:
                    ok = st["success"]
                    articles_found = st["articles_found"]
                    fetched_at = (st["fetched_at"][:10] + " " + st["fetched_at"][11:16]) if len(st["fetched_at"]) > 16 else st["fetched_at"][:10]
                    status_icon = "✅" if ok else "❌"
                    status_class = "source-status-ok" if ok else "source-status-fail"
                    error_info = f'<span class="source-error">{html.escape(st["error_msg"][:60])}</span>' if not ok and st["error_msg"] else ""
                    health = f'<span class="{status_class}">{status_icon} {fetched_at} ({articles_found}篇){error_info}</span>'
                else:
                    health = '<span class="source-status-na">❓ 暂无数据</span>'
                items += f'<div class="source-item"><span class="name">{html.escape(name)}</span>{health}<span class="url">{html.escape(url)}</span></div>'

        content = f"""<div class="container">
  <div class="sources-list">
    <h2>📡 数据源列表 — {t.app_name_cn}</h2>
    <div class="source-count">共 {len(sources)} 个订阅源</div>
    {items}
  </div>
  <div style="text-align:center;padding:1rem 0;"><a href="{prefix}/" style="color:{t.dashboard_color_primary};font-size:0.85rem;">← 返回首页</a></div>
</div>"""
        self._send_html(get_header(t, theme_name) + content + render_footer(self.prefix))

    def _handle_enable_source(self, params: dict):
        theme_name = self._theme
        source_name = params.get("name", "")
        if not source_name:
            self._send_json({"ok": False, "msg": "missing source name"})
            return
        conn = init_db_for_theme(theme_name)
        try:
            conn.execute("UPDATE source_config SET disabled=0, consecutive_failures=0 WHERE source_name=?", (source_name,))
            conn.commit()
            self.send_response(302)
            self.send_header("Location", f"{self.prefix}/sources")
            self.end_headers()
        except Exception as e:
            self._send_json({"ok": False, "msg": str(e)})
        finally:
            conn.close()

    def _handle_monthly_report(self, params: dict):
        theme_name = self._theme
        t = THEMES[theme_name]
        prefix = self.prefix
        month = params.get("month", "")

        conn = init_db_for_theme(theme_name)
        try:
            months = get_available_months(conn)
            if not month and months:
                month = months[0]
            if not month:
                h = get_header(t, theme_name)
                self._send_html(h + '<div class="container"><div class="empty">暂无数据</div></div>' + render_footer(self.prefix))
                return

            # Serve cached version if exists
            report_dir = BASE_DIR / "briefings" / theme_name
            report_path = report_dir / f"monthly-{month}.html"
            if report_path.exists():
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(report_path.read_bytes())
                return

            # Generate and cache
            report_html = self._generate_monthly_report(conn, t, theme_name, month, months)
            report_dir.mkdir(parents=True, exist_ok=True)
            report_path.write_text(report_html, encoding="utf-8")
            self._send_html(report_html)
        finally:
            conn.close()

    def _generate_monthly_report(self, conn, t, theme_name, month, months):
        """Generate comprehensive monthly HTML report."""
        prefix = self.prefix

        total_articles = conn.execute(
            "SELECT COUNT(*) FROM articles WHERE strftime('%Y-%m', published) = ?", (month,)
        ).fetchone()[0]
        unread_count = conn.execute(
            "SELECT COUNT(*) FROM articles WHERE strftime('%Y-%m', published) = ? AND is_read=0", (month,)
        ).fetchone()[0]

        # Top sources
        source_counts = conn.execute(
            "SELECT source, COUNT(*) as cnt FROM articles "
            "WHERE strftime('%Y-%m', published) = ? "
            "GROUP BY source ORDER BY cnt DESC LIMIT 20", (month,)
        ).fetchall()

        # Keyword aggregation
        kw_rows = conn.execute(
            "SELECT matched_kw FROM articles WHERE strftime('%Y-%m', published) = ? AND matched_kw != ''", (month,)
        ).fetchall()
        kw_counter = Counter()
        for (kw_str,) in kw_rows:
            for kw in kw_str.split(", "):
                if kw:
                    kw_counter[kw] += 1
        top_keywords = kw_counter.most_common(30)

        # Top articles by relevance
        top_articles = conn.execute(
            "SELECT id, title, source, relevance FROM articles "
            "WHERE strftime('%Y-%m', published) = ? "
            "ORDER BY relevance DESC, published DESC LIMIT 10", (month,)
        ).fetchall()

        # Source performance
        source_perf = conn.execute("""
            SELECT s.source_name, SUM(s.success) as succ, COUNT(*) as total,
                   MAX(s.fetched_at) as last_fetch
            FROM source_stats s
            WHERE strftime('%Y-%m', s.fetched_at) = ?
            GROUP BY s.source_name
            ORDER BY succ DESC
        """, (month,)).fetchall()

        # Daily trend
        daily = conn.execute(
            "SELECT substr(published, 1, 10) as day, COUNT(*) as cnt "
            "FROM articles WHERE strftime('%Y-%m', published) = ? "
            "GROUP BY day ORDER BY day", (month,)
        ).fetchall()

        css = get_css(t)
        lines = [f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">']
        lines.append(f'<title>月度报告 {month} - {t.app_name_cn}</title>')
        lines.append('<style>' + css)
        lines.append("""
        .report-section { margin:2rem 0; padding:1.5rem; background:#243447; border-radius:10px; border:1px solid #3b4a5a; }
        .report-section h2 { color:""" + t.dashboard_color_primary + """; font-size:1.1rem; margin-bottom:1rem; }
        .report-section table { width:100%; border-collapse:collapse; font-size:0.85rem; }
        .report-section th { color:#64748b; padding:0.5rem; text-align:left; font-weight:600; border-bottom:1px solid #3b4a5a; }
        .report-section td { padding:0.5rem; color:#94a3b8; border-bottom:1px solid #2a3a4a; }
        .report-section tr:hover { background:rgba(255,255,255,0.02); }
        .daily-chart { display:flex; gap:3px; align-items:flex-end; height:80px; padding:0.5rem 0; }
        .daily-bar { flex:1; background:""" + t.dashboard_color_primary + """; border-radius:2px 2px 0 0; min-width:6px; position:relative; transition:opacity 0.2s; }
        .daily-bar:hover { opacity:0.8; }
        .daily-label { font-size:0.6rem; color:#64748b; text-align:center; margin-top:3px; white-space:nowrap; }
        </style></head><body>""")

        lines.append(f'<div class="header"><div class="header-top"><div><h1>{t.app_name_cn} - 月度报告</h1><div class="subtitle">{month}</div></div></div></div>')
        lines.append('<div class="container">')

        # Summary cards
        lines.append(f"""
        <div class="stats-bar">
          <div class="stat-card"><span class="num">{total_articles}</span><span class="label">文章总数</span></div>
          <div class="stat-card"><span class="num">{unread_count}</span><span class="label">未读</span></div>
          <div class="stat-card"><span class="num purple">{len(source_counts)}</span><span class="label">活跃数据源</span></div>
          <div class="stat-card"><span class="num orange">{len(top_keywords)}</span><span class="label">匹配关键词</span></div>
        </div>""")

        # Daily trend
        if daily:
            max_daily = max(d[1] for d in daily)
            lines.append('<div class="report-section"><h2>每日文章数量</h2><div class="daily-chart">')
            for day_label, cnt in daily:
                height = max(3, int(cnt / max_daily * 70))
                lines.append(f'<div style="flex:1;display:flex;flex-direction:column;align-items:center;">')
                lines.append(f'<div class="daily-bar" style="height:{height}px;" title="{day_label}: {cnt}篇"></div>')
                lines.append(f'<div class="daily-label">{day_label[-5:]}</div>')
                lines.append('</div>')
            lines.append('</div></div>')

        # Top sources
        if source_counts:
            lines.append('<div class="report-section"><h2>活跃数据源 TOP 20</h2><table><tr><th>数据源</th><th>文章数</th></tr>')
            for src, cnt in source_counts:
                lines.append(f'<tr><td>{html.escape(src)}</td><td>{cnt}</td></tr>')
            lines.append('</table></div>')

        # Top keywords
        if top_keywords:
            lines.append(f'<div class="report-section"><h2>热门关键词 TOP 30</h2><div style="display:flex;flex-wrap:wrap;gap:0.3rem;">')
            for kw, cnt in top_keywords:
                lines.append(f'<span style="display:inline-block;background:rgba({t.dashboard_color_primary_rgb},0.1);color:{t.dashboard_color_primary};padding:0.2rem 0.5rem;border-radius:4px;font-size:0.8rem;">{html.escape(kw)} ({cnt})</span>')
            lines.append('</div></div>')

        # Source performance
        if source_perf:
            success_rate = sum(r[1] for r in source_perf) / max(sum(r[2] for r in source_perf), 1) * 100
            lines.append(f'<div class="report-section"><h2>数据源表现（成功率 {success_rate:.1f}%）</h2>')
            lines.append('<table><tr><th>数据源</th><th>成功</th><th>总数</th><th>成功率</th><th>上次采集</th></tr>')
            for src, succ, total_n, last_fetch in source_perf:
                rate = succ / max(total_n, 1) * 100
                color = "#22c55e" if rate >= 80 else "#fde047" if rate >= 50 else "#ef4444"
                lines.append(f'<tr><td>{html.escape(src)}</td><td>{succ}</td><td>{total_n}</td><td style="color:{color};">{rate:.0f}%</td><td>{last_fetch[:10] if last_fetch else "?"}</td></tr>')
            lines.append('</table></div>')

        # Top articles
        if top_articles:
            lines.append('<div class="report-section"><h2>热门文章 TOP 10</h2>')
            for art_id, title, src, relevance in top_articles:
                lines.append(f'<div style="margin-bottom:0.5rem;padding:0.8rem;border-bottom:1px solid #2a3a4a;">')
                lines.append(f'<div style="font-size:0.9rem;"><a href="{prefix}/article?id={art_id}" style="color:#e2e8f0;text-decoration:none;">{html.escape(title[:100])}</a></div>')
                lines.append(f'<div style="color:#64748b;font-size:0.78rem;margin-top:0.2rem;">{html.escape(src)} · 相关度: {relevance}</div>')
                lines.append('</div>')
            lines.append('</div>')

        # Month navigation
        if months:
            lines.append('<div class="report-section"><h2>其他月份</h2><div style="display:flex;flex-wrap:wrap;gap:0.3rem;">')
            for m in months:
                active_str = ' style="font-weight:600;"' if m == month else ""
                lines.append(f'<a href="{prefix}/monthly-report?month={m}"{active_str} style="color:{t.dashboard_color_primary};font-size:0.85rem;padding:0.2rem 0.5rem;">{m}</a>')
            lines.append('</div></div>')

        lines.append(f'<div style="text-align:center;padding:1rem 0;"><a href="{prefix}/" style="color:{t.dashboard_color_primary};font-size:0.85rem;">← 返回首页</a></div>')
        lines.append('</div></body></html>')
        return "\n".join(lines)

    def _handle_export(self, params: dict):
        theme_name = self._theme
        t = THEMES[theme_name]
        days = int(params.get("days", "7"))
        conn = init_db_for_theme(theme_name)
        try:
            articles = get_articles_for_briefing(conn, days=days)
            now_str = datetime.now().strftime("%Y-%m-%d")
            lines = [f"# 简报 — {t.app_name_cn} (最近{days}天)", "", f"生成时间: {now_str}", "", "---", ""]
            for a in articles:
                title = a.get("translated_title") or a["title"]
                source = a.get("source", "")
                url = a.get("url", "")
                kw = a.get("matched_kw", "")
                summary = a.get("translated_summary") or a.get("summary", "")
                lines.append(f"## [{title}]({url})")
                lines.append(f"- **来源**: {source}")
                lines.append(f"- **关键词**: {kw}")
                lines.append(f"- **摘要**: {summary}")
                lines.append("")
            md = "\n".join(lines)
            self.send_response(200)
            self.send_header("Content-Type", "text/markdown; charset=utf-8")
            self.send_header("Content-Disposition",
                             f'attachment; filename="briefing-{theme_name}-{now_str}.md"')
            self.end_headers()
            self.wfile.write(md.encode("utf-8"))
        finally:
            conn.close()

    def _handle_archive(self, params: dict):
        theme_name = self._theme
        t = THEMES[theme_name]
        prefix = self.prefix
        page = int(params.get("page", "1"))
        limit = 50
        offset = (page - 1) * limit
        month = params.get("month", "")
        unread_only = params.get("unread", "") == "1"
        type_filter = params.get("type", "")

        conn = init_db_for_theme(theme_name)
        try:
            months = get_available_months(conn)
            if not month and months:
                month = months[0]
            if month not in months and month:
                months.insert(0, month)

            rows = get_articles_by_month(conn, month, limit=limit, offset=offset,
                                         unread_only=unread_only, type_filter=type_filter)

            html_content = '<div class="container">'

            # Month navigator
            html_content += '<div class="archive-nav">'
            if months:
                html_content += f'<span style="color:#64748b;font-size:0.78rem;margin-right:0.5rem;">归档:</span>'
                for m in months[:24]:
                    active = "active" if m == month else ""
                    url = f"{prefix}/archive?month={m}"
                    html_content += f'<a href="{url}" class="{active}">{m}</a>'
            html_content += '</div>'

            if not rows:
                html_content += '<div class="empty">该月份暂无文章</div>'
            else:
                total = conn.execute(
                    "SELECT COUNT(*) FROM articles WHERE strftime('%Y-%m', published) = ?",
                    (month,),
                ).fetchone()[0]
                html_content += f'<div style="padding:0.5rem 0;color:#64748b;font-size:0.85rem;">{month} — 共 {total} 篇</div>'
                for row in rows:
                    html_content += render_article(row, t, theme_name)

                total_pages = max(1, (total + limit - 1) // limit)
                if total_pages > 1:
                    html_content += '<div class="pagination">'
                    for p in range(max(1, page - 5), min(total_pages, page + 5) + 1):
                        active_cls = "active" if p == page else ""
                        url = f"{prefix}/archive?month={month}&page={p}"
                        html_content += f'<a href="{url}" class="{active_cls}">{p}</a>'
                    html_content += '</div>'

            html_content += '</div>'
            self._send_html(get_header(t, theme_name) + html_content + render_footer(self.prefix))
        finally:
            conn.close()

    # ── Routing ───────────────────────────────────────────────────────

    def _strip_prefix(self, path: str) -> str:
        if path.startswith("/aam"):
            rest = path[4:] or "/"
            if not rest.startswith("/"):
                rest = "/" + rest
            return rest
        return path

    def do_GET(self):
        self._set_theme_from_path(self.path)
        full = self._strip_prefix(self.path)
        parsed = urllib.parse.urlparse(full)
        route = parsed.path
        params = urllib.parse.parse_qs(parsed.query)
        params = {k: v[0] for k, v in params.items()}

        if route == "/":
            if params.get("search") == "1":
                self._handle_search(params)
            else:
                self._handle_page(params)
        elif route == "/article":
            self._handle_article(params)
        elif route == "/mark-read":
            self._handle_mark_read(params)
        elif route == "/sources":
            self._handle_sources(params)
        elif route == "/toggle-star":
            self._handle_toggle_star(params)
        elif route == "/poll-history":
            self._handle_poll_history(params)
        elif route == "/enable-source":
            self._handle_enable_source(params)
        elif route == "/monthly-report":
            self._handle_monthly_report(params)
        elif route == "/export":
            self._handle_export(params)
        elif route == "/archive":
            self._handle_archive(params)
        else:
            t = THEMES[self._theme]
            h = get_header(t, self._theme)
            self._send_html(h + f'<div class="container"><h2 style="color:#475569;">404</h2><a href="/" style="color:{t.dashboard_color_primary};">← 返回首页</a></div>' + render_footer(self.prefix), 404)

    def do_POST(self):
        self._set_theme_from_path(self.path)
        full = self._strip_prefix(self.path)
        parsed = urllib.parse.urlparse(full)
        route = parsed.path

        if route == "/trigger-poll":
            self._handle_trigger_poll()
        else:
            self._send_json({"ok": False, "msg": "unknown endpoint"})
