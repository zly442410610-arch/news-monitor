"""Dashboard HTTP request handler."""
import html
import http.server
import json
import re
import sqlite3
import urllib.parse
from collections import Counter


from datetime import datetime
from pathlib import Path

from briefing import generate_monthly_survey, md_to_html
from monitor import (
    fetch_article_content, get_articles, get_articles_by_month,
    get_articles_for_briefing, get_available_months, get_event_grouped_articles,
    get_keyword_trend, get_top_keywords,
    get_source_status, search_articles, update_article_content,
)
from translator import translate_content, is_predominantly_chinese

from .render import (
    _safe_href,
    format_time_cn, get_css, get_header, render_footer, render_article, render_event_header,
    render_svg_bar_chart,
)
from .state import BASE_DIR, THEMES, log as log
from theme import AAM, NEWS
import config


def _format_content_paragraphs(text: str) -> str:
    """Split article text into paragraphs, wrap each in <p>.

    Double newlines = paragraph boundary.
    Single newlines within a paragraph become <br>.
    """
    paras = re.split(r"\n{2,}", text)
    parts = []
    for p in paras:
        p = p.strip()
        if not p:
            continue
        parts.append(f"<p>{html.escape(p).replace(chr(10), '<br>')}</p>")
    return "\n".join(parts)


# Schema migration done per theme (avoids checking every request)
_schema_initialized: set[str] = set()


def init_db_for_theme(theme_name: str) -> sqlite3.Connection:
    """Initialize theme-specific database.

    Schema creation/migration runs only once per theme per process.
    """
    t = THEMES[theme_name]
    db_path = BASE_DIR / "data" / f"{t.db_name}.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    if theme_name not in _schema_initialized:
        _init_schema(conn)
        _schema_initialized.add(theme_name)

    return conn


def _init_schema(conn: sqlite3.Connection):
    """Run schema creation and migration (once per theme per process)."""
    from schema import ARTICLES_TABLE_DDL, ARTICLES_INDEXES, EXTRA_COLUMNS, METADATA_TABLE_DDLS

    conn.execute(ARTICLES_TABLE_DDL)
    for idx_ddl in ARTICLES_INDEXES:
        conn.execute(idx_ddl)

    for col_name, col_type in EXTRA_COLUMNS:
        try:
            conn.execute(f"ALTER TABLE articles ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            pass
    conn.commit()

    for ddl in METADATA_TABLE_DDLS:
        try:
            conn.execute(ddl)
        except sqlite3.OperationalError:
            pass
    conn.commit()


class DashboardHandler(http.server.BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        log.info(f"{self.client_address[0]} - {fmt % args}")

    FAVICON_SVG = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        '<rect width="64" height="64" rx="12" fill="#1e293b"/>'
        '<text x="32" y="44" font-size="36" font-family="sans-serif" '
        'fill="#38bdf8" text-anchor="middle" font-weight="bold">★</text>'
        '</svg>'
    )

    def _send_html(self, html_content: str, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html_content.encode("utf-8"))

    def _send_svg(self, svg: str):
        self.send_response(200)
        self.send_header("Content-Type", "image/svg+xml")
        self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        self.wfile.write(svg.encode("utf-8"))

    def _send_json(self, data: dict, status=200):
        self.send_response(status)
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
        try:
            page = max(1, int(params.get("page", "1")))
        except (ValueError, TypeError):
            page = 1
        limit = 50
        offset = (page - 1) * limit
        type_filter = params.get("type", "")
        kw_group = params.get("kw", "")
        kw_filter = None
        if kw_group:
            _conn = init_db_for_theme(theme_name)
            try:
                from keywords_db import get_merged_keywords
                merged_kw = get_merged_keywords(_conn, t.keywords)
                if kw_group in merged_kw:
                    kw_filter = merged_kw[kw_group]
            finally:
                _conn.close()
        prefix = self.prefix

        extra_conds = []
        extra_params: list = []
        if type_filter in ("paper", "news", "patent"):
            extra_conds.append("article_type=?")
            extra_params.append(type_filter)
        if kw_filter:
            extra_conds.append("(" + " OR ".join(["matched_kw LIKE ?" for _ in kw_filter]) + ")")
            extra_params.extend([f"%{kw}%" for kw in kw_filter])
        type_cond = (" AND " + " AND ".join(extra_conds)) if extra_conds else ""

        conn = init_db_for_theme(theme_name)
        html_content = ""
        try:
            total = conn.execute(
                "SELECT COUNT(*) FROM articles WHERE 1=1" + type_cond,
                extra_params,
            ).fetchone()[0]
            all_count = total
            total_pages = max(1, (total + limit - 1) // limit)
            last_24h = conn.execute(
                "SELECT COUNT(*) FROM articles WHERE fetched_at > datetime('now', '-1 day')" + type_cond,
                extra_params,
            ).fetchone()[0]

            poll_row = conn.execute(
                "SELECT duration_sec FROM poll_stats ORDER BY id DESC LIMIT 1"
            ).fetchone()
            poll_footer = f'<div class="footer-stat">v{config.VERSION} · <a href="{prefix}/sources">数据源列表</a></div>'
            if poll_row:
                dur = poll_row['duration_sec']
                if dur < 60:
                    dur_str = f"{dur}秒"
                else:
                    dur_str = f"{dur//60}分{dur%60}秒"
                poll_footer = f'<div class="footer-stat">v{config.VERSION} · 上次采集耗时 {dur_str} · <a href="{prefix}/sources">数据源列表</a></div>'

            html_content += f"""
            <div class="stats-bar">
              <div class="stat-card"><span class="num">{all_count}</span><span class="label">总计</span></div>
              <div class="stat-card"><span class="num green">{last_24h}</span><span class="label">最近24h</span></div>
            </div>"""

            # Articles
            html_content += '<div class="container">'
            if total == 0:
                html_content += '<div class="empty">没有匹配的文章</div>'
            elif t.has_event_grouping:
                grouped = get_event_grouped_articles(conn, limit=limit, offset=offset, type_filter=type_filter, kw_filter=kw_filter)
                event_groups = []
                standalone = []
                current_group = None

                for row, is_start in grouped:
                    eg = row['event_group']
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
                        eg_title = first_row['event_title'] or ""
                        html_content += render_event_header(eg_title or "", eg_rows, t)
                        for r in eg_rows:
                            html_content += render_article(r, t, theme_name)
                        html_content += '</div>'
                    else:
                        standalone.append(eg_rows[0])

                for row in standalone:
                    html_content += render_article(row, t, theme_name)
            else:
                rows = get_articles(conn, limit=limit, offset=offset, type_filter=type_filter, kw_filter=kw_filter)
                for row in rows:
                    html_content += render_article(row, t, theme_name)

            # Pagination
            if total_pages > 1:
                html_content += '<div class="pagination">'
                for p in range(max(1, page - 5), min(total_pages, page + 5) + 1):
                    active = "active" if p == page else ""
                    url = f"{prefix}/?page={p}" if prefix else f"/?page={p}"
                    if type_filter:
                        url += f"&type={type_filter}"
                    if kw_group:
                        url += f"&kw={kw_group}"
                    html_content += f'<a href="{url}" class="{active}">{p}</a>'
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
              var activeSet = false;
              links.forEach(function(a) {
                a.classList.remove('active');
                var href = a.getAttribute('href');
                if (href.indexOf('type=') !== -1 && params.get('type') && href.indexOf('type=' + params.get('type')) !== -1) {
                  a.classList.add('active'); activeSet = true;
                }
              });
              if (!activeSet) {
                // Default to "全部" — the first nav link without ? in href
                var allLink = document.querySelector('.header-nav a:not([href*=\"?\"])');
                if (allLink) allLink.classList.add('active');
              }
            }
            setActiveNav();

            function expandSummary(id) {
              var s = document.getElementById('s-' + id);
              var e = document.getElementById('e-' + id);
              if (s) s.classList.remove('collapsed');
              if (e) e.style.display = 'none';
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
        article_id = params.get("id", "")
        if not article_id:
            self._send_html(get_header(t, theme_name) + f'<div class="container"><div class="empty">缺少文章ID</div><a href="{self.prefix}/" style="color:{t.dashboard_color_primary};">← 返回首页</a></div>' + render_footer(self.prefix), 404)
            return

        conn = init_db_for_theme(theme_name)
        try:
            row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
            if not row:
                self._send_html(get_header(t, theme_name) + f'<div class="container"><div class="empty">文章不存在</div><a href="{self.prefix}/" style="color:{t.dashboard_color_primary};">← 返回首页</a></div>' + render_footer(self.prefix), 404)
                return

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
            art_content = row['content'] or ""
            art_article_type = row['article_type'] or "news"

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

            # Content — show translation if available, otherwise original
            content_html = ""
            if art_trans_content:
                content_html = f"""<div class="content-section">
  <h3 class="content-heading">全文翻译</h3>
  <div class="content-body translation">{_format_content_paragraphs(art_trans_content)}</div>
</div>"""
            elif art_content:
                content_html = f"""<div class="content-section">
  <h3 class="content-heading">原文内容</h3>
  <div class="content-body original">{_format_content_paragraphs(art_content)}</div>
</div>"""
            else:
                # Show RSS summary as fallback when no full content
                if art_summary:
                    content_html = f"""<div class="content-section">
  <h3 class="content-heading">内容摘要</h3>
  <div class="content-body">{html.escape(display_summary)}</div>
</div>"""
                snap = self._archive_dir(theme_name) / f"{art_id}.html"
                if snap.exists():
                    raw = snap.read_text("utf-8")
                    m = re.search(r"<pre[^>]*>(.*?)</pre>", raw, re.DOTALL)
                    if m:
                        text = m.group(1).strip()
                        content_html = f"""<div class="content-section">
  <h3 class="content-heading">原文内容</h3>
  <div class="content-body original">{html.escape(text[:5000])}</div>
</div>"""
                else:
                    # Skip live fetch for patent articles — Google Patents is
                    # unreachable from this network (no proxy in dashboard) and
                    # would block the single-threaded server for 10+ seconds.
                    if art_article_type == "patent":
                        pass
                    else:
                        try:
                            live = fetch_article_content(art_url, timeout=10)
                            if live and live.get("text"):
                                text = live["text"]
                                # Save content to DB so subsequent views skip fetch
                                conn.execute("UPDATE articles SET content=? WHERE id=?", (text[:50000], art_id))
                                conn.commit()
                                # Translate and save
                                translated = None
                                if len(text) > 500 and not is_predominantly_chinese(text):
                                    translated = translate_content(text)
                                if translated:
                                    conn.execute("UPDATE articles SET translated_content=? WHERE id=?", (translated, art_id))
                                    conn.commit()
                                    content_html = f"""<div class="content-section">
  <h3 class="content-heading">全文翻译</h3>
  <div class="content-body translation">{_format_content_paragraphs(translated)}</div>
</div>"""
                                else:
                                    content_html = f"""<div class="content-section">
  <h3 class="content-heading">原文内容</h3>
  <div class="content-body original">{_format_content_paragraphs(text)}</div>
</div>"""
                        except Exception:
                            pass

            # Related articles (same event group)
            related_html = ""
            if row["event_group"]:
                related = conn.execute(
                    "SELECT id, title, source, published, translated_title, article_type FROM articles "
                    "WHERE event_group = ? AND id != ? ORDER BY published DESC LIMIT 10",
                    (row["event_group"], article_id),
                ).fetchall()
                if related:
                    art_prefix_rel = "" if theme_name == "news" else "/aam"
                    related_html = '<div class="related-section"><h3 class="content-heading">相关报道</h3>'
                    for r in related:
                        r_title = r["translated_title"] or r["title"]
                        r_type = r["article_type"] or "news"
                        type_labels = {"paper": "论文", "patent": "专利", "news": "新闻"}
                        r_tag = (f'<span class="type-tag {r_type}">{type_labels.get(r_type, r_type)}</span> '
                                 if r_type in ("paper", "patent", "news") else "")
                        r_pub = format_time_cn(r["published"][:10]) if r["published"] else ""
                        related_html += (
                            f'<div class="related-item">'
                            f'<div class="related-title-row">'
                            f'{r_tag}'
                            f'<a href="{art_prefix_rel}/article?id={html.escape(r["id"])}">{html.escape(r_title[:100])}</a>'
                            f'</div>'
                            f'<span class="related-source">{html.escape(r["source"])} · {r_pub}</span>'
                            f'</div>'
                        )
                    related_html += '</div>'

            # Similar articles (based on keyword overlap)
            similar_html = ""
            art_kw_raw = row["matched_kw"] or ""
            if art_kw_raw:
                kws = [kw.strip() for kw in art_kw_raw.split(", ") if kw.strip()]
                if kws:
                    cases = " + ".join(f"(CASE WHEN matched_kw LIKE {html.escape('%' + kw + '%')!r} THEN 1 ELSE 0 END)" for kw in kws)
                    sql = f"SELECT id, title, source, published, translated_title, article_type, relevance, ({cases}) as kw_matches FROM articles WHERE id != ? AND matched_kw != '' ORDER BY kw_matches DESC, relevance DESC LIMIT 8"
                    similar = conn.execute(sql, (article_id,)).fetchall()
                    if similar:
                        art_prefix_sim = "" if theme_name == "news" else "/aam"
                        similar_html = '<div class="related-section"><h3 class="content-heading">相似文章</h3>'
                        for s in similar:
                            s_title = s["translated_title"] or s["title"]
                            s_type = s["article_type"] or "news"
                            type_labels = {"paper": "论文", "patent": "专利", "news": "新闻"}
                            s_tag = (f'<span class="type-tag {s_type}">{type_labels.get(s_type, s_type)}</span> '
                                     if s_type in ("paper", "patent", "news") else "")
                            s_pub = format_time_cn(s["published"][:10]) if s["published"] else ""
                            similar_html += (
                                f'<div class="related-item">'
                                f'<div class="related-title-row">'
                                f'{s_tag}'
                                f'<a href="{art_prefix_sim}/article?id={html.escape(s["id"])}">{html.escape(s_title[:100])}</a>'
                                f'</div>'
                                f'<span class="related-source">{html.escape(s["source"])} · {s_pub} · 匹配 {s["kw_matches"]} 词</span>'
                                f'</div>'
                            )
                        similar_html += '</div>'

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
<a class="theme-badge" href="{('/aam' if theme_name == 'news' else '/')}" style="position:fixed;top:12px;right:12px;z-index:999;display:flex;align-items:center;gap:4px;padding:4px 10px;border-radius:20px;font-size:0.75rem;font-weight:600;text-decoration:none;background:rgba(15,23,42,0.85);backdrop-filter:blur(4px);border:1px solid {t.dashboard_other_theme_color};color:{t.dashboard_other_theme_color};transition:all 0.2s;">{(AAM if theme_name == 'news' else NEWS).app_name_cn} →</a>
<div class="header">
<div class="header-top">
<div>
<h1><a href="{art_prefix}/" style="color:{t.dashboard_color_primary};text-decoration:none;">{t.app_name_cn}</a></h1>
</div>
<div class="header-actions">
<span class="nav-group">
<a href="{art_prefix}/" class="active">全部</a>
<a href="{art_prefix}/?search=1">搜索</a>
<a href="{art_prefix}/?type=paper">论文</a>
<a href="{art_prefix}/?type=news">新闻</a>
<a href="{art_prefix}/?type=patent">专利</a>
</span>
</div>
</div>
</div>
<div class="container" style="max-width:900px;">
<div class="article" style="border-left:3px solid {t.dashboard_color_primary};">

<div class="top-row">
<div class="source">
<span class="source-tag {source_tag_class}">{source_tag}</span>
{html.escape(art_source)} · {art_published}
</div>
<div>
<span class="score {'high' if art_relevance >= 50 else 'med' if art_relevance >= 20 else 'low'}">{art_relevance}</span>
{'<span class="translated-tag">中译</span>' if art_is_translated or art_trans_content else ''}
{'<span class="type-tag paper">论文</span> ' if art_article_type == "paper" else '<span class="type-tag patent">专利</span> ' if art_article_type == "patent" else '<span class="type-tag news">新闻</span> '}
</div>
</div>

<h2 style="color:#e2e8f0;font-size:1.2rem;margin:0.6rem 0 0.2rem;line-height:1.5;">{html.escape(display_title)}</h2>
{orig_line}
{author_line}
{f'<img src="{html.escape(art_image_url)}" alt="" style="max-width:100%;max-height:400px;border-radius:8px;margin:0.8rem 0;border:1px solid #334155;">' if art_image_url else ''}

<div style="margin:0.5rem 0;">
{kw_html}
</div>

{f'<div style="color:#94a3b8;font-size:1rem;line-height:1.7;margin:1rem 0;">{html.escape(display_summary)}</div>' if not (art_trans_content or art_content) else ''}

<div style="margin-top:1.5rem;">
{f'<a href="{html.escape(_safe_href(art_url))}" target="_blank" rel="noopener" style="display:inline-block;background:#1e293b;color:{t.dashboard_color_primary};border:1px solid {t.dashboard_color_primary};padding:0.5rem 1.2rem;border-radius:6px;font-weight:600;text-decoration:none;">查看原文</a>' if _safe_href(art_url) else '<span style="color:#64748b;font-size:0.85rem;">链接不可用</span>'}
<a href="{art_prefix}/" style="margin-left:1rem;color:#94a3b8;">← 返回首页</a>
</div>

</div>
{content_html}
{related_html}
{similar_html}
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
        try:
            page = max(1, int(params.get("page", "1")))
        except (ValueError, TypeError):
            page = 1
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
                total_articles = sum(r['articles_found'] for r in rows)
                avg_duration = sum(r['duration_sec'] for r in rows) // len(rows)
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
                    config_map[cr['source_name']] = {"disabled": cr['disabled'], "consecutive_failures": cr['consecutive_failures']}
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
        """Generate comprehensive monthly research survey report.
        Primary: LLM-generated research survey (研究综述).
        Fallback: stats-based report if LLM fails.
        """
        prefix = self.prefix
        css = get_css(t)

        # ── Primary: LLM research survey ──────────────────────────────
        try:
            year, m = month.split("-")
            articles = get_articles_by_month(conn, month, limit=200)
            articles_dicts = []
            if articles:
                col_names = [c[1] for c in conn.execute("PRAGMA table_info(articles)").fetchall()]
                for row in articles:
                    articles_dicts.append(dict(zip(col_names, row)))

            topic_name = t.app_name_cn.replace("信息采集系统", "").strip()
            survey_md = generate_monthly_survey(articles_dicts, year, m, topic=topic_name, prompt=t.monthly_report_prompt)
            if survey_md:
                survey_body = md_to_html(survey_md)
                return self._wrap_survey_html(survey_body, t, theme_name, prefix, month, months, css, len(articles_dicts))
        except Exception as e:
            log.warning(f"LLM survey generation failed, falling back to stats report: {e}")

        # ── Fallback: stats-based report ──────────────────────────────
        return self._generate_stats_report(conn, t, theme_name, month, months, prefix, css)

    def _wrap_survey_html(self, survey_body: str, t, theme_name, prefix, month, months, css, total_articles):
        """Wrap the LLM-generated survey in a GitBook-style responsive layout."""
        # Build TOC from survey_body headings, and inject anchor IDs
        toc_items = []
        def _heading_replacer(m):
            tag = m.group(1)
            text = m.group(2)
            slug = re.sub(r'[^\w一-鿿]+', '-', text.strip().lower()).strip('-')[:60]
            if not slug:
                slug = f"heading-{len(toc_items)}"
            toc_items.append((len(tag), slug, text.strip()))
            return f'<{tag} id="{slug}">{text}</{tag}>'

        survey_body = re.sub(
            r'<(h[23])>(.*?)</\1>',
            _heading_replacer,
            survey_body,
            flags=re.DOTALL,
        )

        # Build TOC HTML
        toc_html = '<ul class="toc-list">'
        for level, slug, text in toc_items:
            cls = 'toc-h3' if level == 3 else 'toc-h2'
            indent = '&nbsp;&nbsp;' if level == 3 else ''
            toc_html += f'<li class="{cls}"><a href="#{slug}">{indent}{text}</a></li>'
        toc_html += '</ul>'

        # Build month nav links
        nav_links = ''
        if months:
            active_cls = ' class="active"'
            nav_links = '\n    '.join(
                f'<a href="{prefix}/monthly-report?month={m}"{active_cls if m == month else ""}>{m}</a>'
                for m in months
            )

        accent = t.dashboard_color_primary
        accent_rgb = t.dashboard_color_primary_rgb
        today = datetime.now().strftime("%Y-%m-%d")

        return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>月度报告 {month} - {t.app_name_cn}</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
html {{ scroll-behavior:smooth; scroll-padding-top:1rem; }}
body {{ font-family:'Noto Sans CJK SC','PingFang SC','Microsoft YaHei','WenQuanYi Micro Hei',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
       background:#1a2332; color:#e2e8f0; display:flex; min-height:100vh; }}
.toc-sidebar {{ position:fixed; top:0; left:0; width:260px; height:100vh; overflow-y:auto;
                background:#141e2a; border-right:1px solid #2a3a4a; z-index:100;
                padding:1.2rem 0; transition:transform 0.25s ease; }}
.toc-sidebar .toc-title {{ font-size:0.9rem; font-weight:600; color:{accent}; padding:0 1rem 0.8rem;
                           border-bottom:1px solid #2a3a4a; margin-bottom:0.5rem; }}
.toc-sidebar .toc-back {{ display:block; font-size:0.85rem; color:#64748b; padding:0.5rem 1rem 0.2rem;
                           text-decoration:none; }}
.toc-sidebar .toc-back:hover {{ color:{accent}; }}
.toc-list {{ list-style:none; padding:0; margin:0; }}
.toc-list a {{ display:block; font-size:0.88rem; color:#94a3b8; text-decoration:none;
               padding:0.35rem 1rem; line-height:1.5; transition:all 0.15s; border-left:2px solid transparent; word-break:break-all; }}
.toc-list a:hover {{ color:#e2e8f0; background:rgba(255,255,255,0.03); border-left-color:{accent}; }}
.toc-list .toc-h3 a {{ padding-left:1.8rem; font-size:0.85rem; color:#64748b; }}
.toc-list .toc-active a {{ color:{accent}; border-left-color:{accent}; background:rgba({accent_rgb},0.06); font-weight:500; }}
.toc-toggle {{ display:none; position:fixed; top:10px; left:10px; z-index:200;
               width:36px; height:36px; border-radius:8px; border:1px solid #3b4a5a;
               background:#1e2a3a; color:#e2e8f0; font-size:1.2rem; cursor:pointer;
               align-items:center; justify-content:center; }}
.toc-toggle:hover {{ background:#2a3a4a; }}
.toc-overlay {{ display:none; position:fixed; inset:0; background:rgba(0,0,0,0.5); z-index:99; }}
.content {{ flex:1; margin-left:260px; max-width:820px; padding:2.5rem 2.5rem 4rem; min-height:100vh; }}
.content h1 {{ font-size:1.75rem; color:#e2e8f0; margin-bottom:1rem; line-height:1.5; font-weight:700; }}
.content h2 {{ font-size:1.35rem; color:{accent}; margin-top:2.2rem; margin-bottom:0.8rem;
               padding-bottom:0.3rem; border-bottom:1px solid #2a4a6a; font-weight:600; }}
.content h3 {{ font-size:1.15rem; color:#cbd5e1; margin-top:1.5rem; margin-bottom:0.5rem; font-weight:500; }}
.content h4 {{ font-size:1.0rem; color:#94a3b8; margin-top:1rem; margin-bottom:0.4rem; }}
.content p {{ font-size:1.05rem; line-height:1.9; color:#cbd5e1; margin-bottom:1rem; text-align:justify; }}
.content ul, .content ol {{ margin:0.5rem 0 1rem; padding-left:1.5rem; }}
.content li {{ font-size:1.0rem; line-height:1.9; color:#cbd5e1; margin-bottom:0.3rem; }}
.content strong {{ color:#f1f5f9; }}
.content code {{ background:rgba({accent_rgb},0.1); padding:0.1rem 0.4rem; border-radius:4px; font-size:0.95rem; }}
.content hr {{ border:none; border-top:1px solid #2a4a6a; margin:2.5rem 0; }}
.survey-meta {{ font-size:0.9rem; color:#64748b; margin-bottom:1.5rem; padding-bottom:1rem;
                border-bottom:1px solid #2a3a4a; }}
.survey-nav {{ margin-top:2rem; padding-top:1.2rem; border-top:1px solid #2a3a4a;
               display:flex; flex-wrap:wrap; gap:0.5rem; align-items:center; }}
.survey-nav a {{ color:{accent}; font-size:0.9rem; text-decoration:none;
                 padding:0.3rem 0.8rem; border:1px solid {accent}; border-radius:6px;
                 transition:all 0.15s; }}
.survey-nav a:hover {{ background:rgba({accent_rgb},0.1); }}
.survey-nav a.active {{ background:rgba({accent_rgb},0.15); font-weight:600; }}
@media (max-width:768px) {{
    .toc-sidebar {{ transform:translateX(-100%); }}
    .toc-sidebar.open {{ transform:translateX(0); }}
    .toc-toggle {{ display:flex; }}
    .toc-overlay.show {{ display:block; }}
    .content {{ margin-left:0; padding:1rem 1.2rem 2rem; }}
    .content h1 {{ font-size:1.4rem; }}
    .content h2 {{ font-size:1.15rem; }}
    .content p {{ font-size:0.95rem; line-height:1.85; }}
    .content li {{ font-size:0.95rem; }}
    .survey-nav {{ gap:0.4rem; }}
    .survey-nav a {{ font-size:0.85rem; padding:0.25rem 0.6rem; }}
}}
@media (max-width:480px) {{
    .content {{ padding:0.8rem 0.8rem 2rem; }}
    .content h1 {{ font-size:1.25rem; }}
    .content p {{ font-size:0.9rem; }}
}}
</style>
</head>
<body>

<button class="toc-toggle" id="tocToggle" aria-label="目录">☰</button>
<div class="toc-overlay" id="tocOverlay"></div>

<nav class="toc-sidebar" id="tocSidebar">
  <a class="toc-back" href="{prefix}/">← 返回首页</a>
  <div class="toc-title">目录</div>
  {toc_html}
</nav>

<main class="content">
  <div style="margin-bottom:1rem;"><a href="{prefix}/" style="color:{accent};font-size:0.9rem;text-decoration:none;">← 返回首页</a></div>
  <div class="survey-meta">本月收录 {total_articles} 篇 · {month} · {today}</div>
  {survey_body}

  <div class="survey-nav">
    <a href="{prefix}/">← 首页</a>
    {nav_links}
  </div>
</main>

<script>
const s=document.getElementById('tocSidebar'),t=document.getElementById('tocToggle'),o=document.getElementById('tocOverlay');
function c(){{ s.classList.remove('open'); o.classList.remove('show'); }}
t?.addEventListener('click',()=>{{ s.classList.toggle('open'); o.classList.toggle('show'); }});
o?.addEventListener('click',c);
const l=document.querySelectorAll('.toc-list a'),h=[];
l.forEach(a=>{{ const e=document.getElementById(a.getAttribute('href').slice(1)); if(e) h.push({{el:e,link:a}}); }});
if(h.length){{ new IntersectionObserver(e=>{{e.forEach(e=>{{if(e.isIntersecting){{l.forEach(l=>l.parentElement.classList.remove('toc-active'));h.find(h=>h.el===e.target)?.link.parentElement.classList.add('toc-active');}}}});}},{{rootMargin:'-80px 0px -80% 0px'}}).observe(h[0].el);if(h.length>1)for(let i=1;i<h.length;i++){{ if(h[i].el) new IntersectionObserver(e=>{{e.forEach(e=>{{if(e.isIntersecting){{l.forEach(l=>l.parentElement.classList.remove('toc-active'));h.find(h=>h.el===e.target)?.link.parentElement.classList.add('toc-active');}}}});}},{{rootMargin:'-80px 0px -80% 0px'}}).observe(h[i].el); }} }}
l.forEach(a=>a.addEventListener('click',()=>{{if(window.innerWidth<=768)c();}}));
</script>
</body>
</html>'''

    def _generate_stats_report(self, conn, t, theme_name, month, months, prefix, css):
        """Fallback: stats-based monthly report (original version)."""
        total_articles = conn.execute(
            "SELECT COUNT(*) FROM articles WHERE strftime('%Y-%m', published) = ?", (month,)
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
        lines.append(f'<div style="margin-bottom:1rem;"><a href="{prefix}/" style="color:{t.dashboard_color_primary};text-decoration:none;font-size:0.9rem;">← 返回首页</a></div>')

        # Summary cards
        lines.append(f"""
        <div class="stats-bar">
          <div class="stat-card"><span class="num">{total_articles}</span><span class="label">文章总数</span></div>
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
            success_rate = sum(r['succ'] for r in source_perf) / max(sum(r['total'] for r in source_perf), 1) * 100
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

    def _handle_images(self, params: dict):
        """Serve extracted PDF thumbnail images."""
        theme_name = self._theme
        img_dir = BASE_DIR / "snapshots" / theme_name / "images"
        filename = params.get("file", "")
        # Security: only allow alphanumeric, dash, underscore, dot
        if not re.match(r"^[a-zA-Z0-9_\-\.]+$", filename):
            self.send_response(404)
            self.end_headers()
            return
        img_path = img_dir / filename
        if not img_path.exists() or not img_path.is_file():
            self.send_response(404)
            self.end_headers()
            return
        # Only serve image files
        if img_path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
            self.send_response(403)
            self.end_headers()
            return
        content_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }.get(img_path.suffix.lower(), "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        with open(img_path, "rb") as f:
            self.wfile.write(f.read())

    def _handle_archive(self, params: dict):
        theme_name = self._theme
        t = THEMES[theme_name]
        prefix = self.prefix
        try:
            page = max(1, int(params.get("page", "1")))
        except (ValueError, TypeError):
            page = 1
        limit = 50
        offset = (page - 1) * limit
        month = params.get("month", "")
        type_filter = params.get("type", "")

        conn = init_db_for_theme(theme_name)
        try:
            months = get_available_months(conn)
            if not month and months:
                month = months[0]
            if month not in months and month:
                months.insert(0, month)

            rows = get_articles_by_month(conn, month, limit=limit, offset=offset,
                                         type_filter=type_filter)

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

    # ── Content backfill ────────────────────────────────────────────

    def _handle_missing_content(self, params: dict):
        theme_name = self._theme
        t = THEMES[theme_name]
        prefix = self.prefix
        conn = init_db_for_theme(theme_name)
        try:
            total_missing = conn.execute(
                "SELECT COUNT(*) FROM articles WHERE content IS NULL OR content = ''"
            ).fetchone()[0]
            page = max(1, int(params.get("page", "1")))
            limit = 50
            offset = (page - 1) * limit
            rows = conn.execute(
                "SELECT id, title, source, published, url, article_type "
                "FROM articles WHERE content IS NULL OR content = '' "
                "ORDER BY published DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()

            total_pages = max(1, (total_missing + limit - 1) // limit)

            parts = [
                f'<div class="container">',
                f'<h2 style="margin-bottom:1rem;">缺失全文的文章</h2>',
                f'<div class="stats-bar">',
                f'  <div class="stat-card"><span class="num orange">{total_missing}</span><span class="label">待抓取</span></div>',
                f'</div>',
                f'<div style="margin:1rem 0;">',
                f'  <button onclick="backfillAll()" class="btn-primary" style="padding:0.5rem 1.2rem;background:{t.dashboard_color_primary};color:#0f172a;border:none;border-radius:6px;font-weight:600;cursor:pointer;">全部补抓</button>',
                f'  <span id="backfill-status" style="margin-left:1rem;color:#64748b;font-size:0.85rem;"></span>',
                f'</div>',
            ]
            if not rows:
                parts.append('<div class="empty">所有文章已有完整内容 ✓</div>')
            else:
                parts.append('<table style="width:100%;border-collapse:collapse;font-size:0.85rem;">')
                parts.append('<thead><tr style="color:#64748b;border-bottom:1px solid #3b4a5a;">')
                parts.append('<th style="padding:0.5rem;text-align:left;">标题</th>')
                parts.append('<th style="padding:0.5rem;text-align:left;">来源</th>')
                parts.append('<th style="padding:0.5rem;text-align:left;">类型</th>')
                parts.append('<th style="padding:0.5rem;text-align:center;">操作</th>')
                parts.append('</tr></thead><tbody>')
                for row in rows:
                    art_id = row["id"]
                    art_title = html.escape(row["title"][:80])
                    art_source = html.escape(row["source"][:30])
                    art_type = row["article_type"] or "news"
                    parts.append(f"""<tr style="border-bottom:1px solid #2a3a4a;">
                  <td style="padding:0.5rem;color:#e2e8f0;">{art_title}</td>
                  <td style="padding:0.5rem;color:#94a3b8;">{art_source}</td>
                  <td style="padding:0.5rem;"><span class="type-tag {art_type}">{art_type}</span></td>
                  <td style="padding:0.5rem;text-align:center;">
                    <button onclick="fetchOne('{art_id}')" style="padding:0.3rem 0.8rem;background:#1e293b;color:{t.dashboard_color_primary};border:1px solid {t.dashboard_color_primary};border-radius:5px;cursor:pointer;font-size:0.78rem;">补抓</button>
                    <span id="status-{art_id}" style="color:#64748b;font-size:0.75rem;margin-left:0.3rem;"></span>
                  </td>
                </tr>""")
                parts.append('</tbody></table>')
                if total_pages > 1:
                    parts.append('<div class="pagination">')
                    for p in range(1, total_pages + 1):
                        active = "active" if p == page else ""
                        parts.append(f'<a href="{prefix}/missing-content?page={p}" class="{active}">{p}</a>')
                    parts.append('</div>')
            parts.append(f'<div style="text-align:center;padding:1rem 0;"><a href="{prefix}/" style="color:{t.dashboard_color_primary};font-size:0.85rem;">← 返回首页</a></div>')
            parts.append('</div>')
            html_content = "\n".join(parts)

            html_content += """<script>
function fetchOne(id) {
    var el = document.getElementById('status-' + id);
    el.textContent = '抓取中...';
    fetch('/backfill-content-single', {
        method: 'POST',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: 'id=' + encodeURIComponent(id)
    }).then(function(r) { return r.json(); }).then(function(d) {
        if (d.ok) {
            el.textContent = '\\u2713 ' + (d.content_len || 0) + ' \\u5b57\\u7b26';
        } else {
            el.textContent = '\\u00d7 ' + (d.error || '\\u5931\\u8d25');
        }
    }).catch(function(e) {
        el.textContent = '\\u00d7 \\u8bf7\\u6c42\\u5931\\u8d25';
    });
}
function backfillAll() {
    if (!confirm('\\u786e\\u5b9a\\u8981\\u6279\\u91cf\\u8865\\u6293\\u6240\\u6709\\u7f3a\\u5931\\u5168\\u6587\\u7684\\u6587\\u7ae0\\u5417\\uff1f\\u6b64\\u64cd\\u4f5c\\u53ef\\u80fd\\u9700\\u8981\\u8f83\\u957f\\u65f6\\u95f4\\u3002')) return;
    var el = document.getElementById('backfill-status');
    el.textContent = '\\u8865\\u6293\\u4e2d...';
    fetch('/backfill-content', {
        method: 'POST'
    }).then(function(r) { return r.json(); }).then(function(d) {
        if (d.ok) {
            el.textContent = '\\u5b8c\\u6210: \\u6210\\u529f ' + d.succeeded + ', \\u5931\\u8d25 ' + d.failed;
            setTimeout(function() { location.reload(); }, 1500);
        } else {
            el.textContent = '\\u00d7 \\u5931\\u8d25: ' + (d.error || '\\u672a\\u77e5\\u9519\\u8bef');
        }
    }).catch(function(e) {
        el.textContent = '\\u00d7 \\u8bf7\\u6c42\\u5931\\u8d25';
    });
}
</script>"""
            self._send_html(get_header(t, theme_name) + html_content + render_footer(self.prefix))
        finally:
            conn.close()

    def _handle_backfill_content_single(self, params: dict):
        theme_name = self._theme
        article_id = params.get("id", "")
        if not article_id:
            self._send_json({"ok": False, "error": "missing id"})
            return
        conn = init_db_for_theme(theme_name)
        try:
            row = conn.execute(
                "SELECT id, url, title FROM articles WHERE id = ?", (article_id,)
            ).fetchone()
            if not row:
                self._send_json({"ok": False, "error": "article not found"})
                return
            result = fetch_article_content(row["url"], timeout=15)
            if not result or not result.get("text"):
                self._send_json({"ok": False, "error": "fetch failed"})
                return
            text = result["text"]
            update_article_content(conn, article_id, text, title=row["title"])
            self._send_json({"ok": True, "id": article_id, "content_len": len(text)})
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)})
        finally:
            conn.close()

    def _handle_backfill_content(self, params: dict):
        theme_name = self._theme
        conn = init_db_for_theme(theme_name)
        try:
            rows = conn.execute(
                "SELECT id, url, title FROM articles "
                "WHERE content IS NULL OR content = '' "
                "ORDER BY published DESC"
            ).fetchall()
            succeeded = 0
            failed = 0
            for row in rows:
                try:
                    result = fetch_article_content(row["url"], timeout=15)
                    if result and result.get("text"):
                        update_article_content(conn, row["id"], result["text"], title=row["title"])
                        succeeded += 1
                    else:
                        failed += 1
                except Exception:
                    failed += 1
            self._send_json({
                "ok": True,
                "total": len(rows),
                "succeeded": succeeded,
                "failed": failed,
            })
        finally:
            conn.close()

    # ── Keyword management ──────────────────────────────────────────

    def _handle_keywords_page(self, params: dict):
        theme_name = self._theme
        t = THEMES[theme_name]
        prefix = self.prefix
        conn = init_db_for_theme(theme_name)
        try:
            from keywords_db import get_db_keywords, get_merged_keywords
            theme_kw = t.keywords
            db_kw = get_db_keywords(conn)
            merged = get_merged_keywords(conn, theme_kw)

            parts = [
                f'<div class="container" style="max-width:800px;">',
                f'<h2 style="margin-bottom:1rem;">关键词管理</h2>',
            ]

            all_groups = sorted(merged.keys())
            group_options = "".join(
                f'<option value="{html.escape(g)}">{html.escape(g)}</option>'
                for g in all_groups
            )

            parts.append(f"""
            <div style="background:#243447;border:1px solid #3b4a5a;border-radius:8px;padding:1rem;margin-bottom:1.5rem;">
              <h3 style="color:{t.dashboard_color_primary};font-size:0.95rem;margin-bottom:0.8rem;">添加关键词</h3>
              <form action="{prefix}/keywords/add" method="post" style="display:flex;gap:0.5rem;flex-wrap:wrap;align-items:end;">
                <div>
                  <label style="color:#64748b;font-size:0.75rem;display:block;margin-bottom:0.2rem;">分组</label>
                  <select name="group" style="padding:0.4rem 0.6rem;border:1px solid #3b4a5a;border-radius:5px;background:#1e2e40;color:#e2e8f0;font-size:0.85rem;">
                    {group_options}
                    <option value="__new__">+ 新建分组...</option>
                  </select>
                </div>
                <div>
                  <label style="color:#64748b;font-size:0.75rem;display:block;margin-bottom:0.2rem;">新建分组名</label>
                  <input type="text" name="new_group" placeholder="group_name" style="padding:0.4rem 0.6rem;border:1px solid #3b4a5a;border-radius:5px;background:#1e2e40;color:#e2e8f0;font-size:0.85rem;">
                </div>
                <div>
                  <label style="color:#64748b;font-size:0.75rem;display:block;margin-bottom:0.2rem;">关键词</label>
                  <input type="text" name="keyword" required placeholder="关键词文字" style="padding:0.4rem 0.6rem;border:1px solid #3b4a5a;border-radius:5px;background:#1e2e40;color:#e2e8f0;font-size:0.85rem;">
                </div>
                <button type="submit" style="padding:0.4rem 1rem;background:{t.dashboard_color_primary};color:#0f172a;border:none;border-radius:5px;font-weight:600;cursor:pointer;font-size:0.85rem;height:fit-content;">添加</button>
              </form>
            </div>""")

            for group_name in all_groups:
                kws = merged[group_name]
                db_kws_in_group = set(db_kw.get(group_name, []))
                total = len(kws)
                custom_count = sum(1 for kw in kws if kw in db_kws_in_group)
                default_count = total - custom_count

                parts.append(f"""
                <div style="background:#1e2e40;border:1px solid #2a3a4a;border-radius:8px;padding:0.8rem 1rem;margin-bottom:1rem;">
                  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem;">
                    <span style="color:{t.dashboard_color_primary};font-weight:600;font-size:0.9rem;">{html.escape(group_name)}</span>
                    <span style="color:#64748b;font-size:0.78rem;">{default_count} 默认 · {custom_count} 自定义</span>
                  </div>
                  <div style="display:flex;flex-wrap:wrap;gap:0.3rem;">""")

                for kw in kws:
                    is_custom = kw in db_kws_in_group
                    badge = ""
                    delete_btn = ""
                    if is_custom:
                        row = conn.execute(
                            "SELECT id FROM keywords WHERE group_name=? AND keyword=?",
                            (group_name, kw),
                        ).fetchone()
                        if row:
                            delete_btn = f'<a href="{prefix}/keywords/delete?id={row["id"]}" style="color:#ef4444;font-size:0.7rem;margin-left:0.2rem;text-decoration:none;" onclick="return confirm(\'删除此关键词?\')">×</a>'
                    else:
                        badge = ' <span style="font-size:0.6rem;color:#64748b;">[base]</span>'

                    parts.append(f"""
                    <span style="display:inline-flex;align-items:center;background:rgba({t.dashboard_color_primary_rgb},0.1);color:{t.dashboard_color_primary};padding:0.15rem 0.5rem;border-radius:4px;font-size:0.8rem;">
                      {html.escape(kw)}{badge}{delete_btn}
                    </span>""")

                parts.append("""
                  </div>
                </div>""")

            parts.append(f"""
            <div style="margin-top:1.5rem;padding-top:1rem;border-top:1px solid #2a3a4a;">
              <details style="color:#64748b;font-size:0.85rem;">
                <summary style="cursor:pointer;">高级操作</summary>
                <div style="margin-top:0.5rem;display:flex;gap:0.5rem;flex-wrap:wrap;">
                  <form action="{prefix}/keywords/delete-group" method="post" style="display:flex;gap:0.3rem;align-items:center;">
                    <select name="group" style="padding:0.3rem 0.5rem;border:1px solid #3b4a5a;border-radius:4px;background:#1e2e40;color:#e2e8f0;font-size:0.8rem;">
                      {group_options}
                    </select>
                    <button type="submit" style="padding:0.3rem 0.7rem;background:#3b1111;color:#fca5a5;border:1px solid #ef4444;border-radius:4px;cursor:pointer;font-size:0.8rem;" onclick="return confirm(\'删除分组将删除该分组下所有自定义关键词，确认?\')">删除分组</button>
                  </form>
                </div>
              </details>
            </div>""")
            parts.append(f'<div style="text-align:center;padding:1rem 0;"><a href="{prefix}/" style="color:{t.dashboard_color_primary};font-size:0.85rem;">← 返回首页</a></div>')
            parts.append("</div>")
            self._send_html(get_header(t, theme_name) + "\n".join(parts) + render_footer(self.prefix))
        finally:
            conn.close()

    def _handle_keywords_add(self, params: dict):
        theme_name = self._theme
        group = params.get("group", "").strip()
        new_group = params.get("new_group", "").strip()
        keyword = params.get("keyword", "").strip()
        if new_group:
            group = new_group
        if not group or not keyword:
            self._send_json({"ok": False, "error": "group and keyword required"})
            return
        conn = init_db_for_theme(theme_name)
        try:
            from keywords_db import add_keyword
            add_keyword(conn, group, keyword)
            self.send_response(302)
            self.send_header("Location", f"{self.prefix}/keywords")
            self.end_headers()
        finally:
            conn.close()

    def _handle_keywords_delete(self, params: dict):
        theme_name = self._theme
        try:
            kw_id = int(params.get("id", "0"))
        except (ValueError, TypeError):
            kw_id = 0
        if not kw_id:
            self._send_json({"ok": False, "error": "missing id"})
            return
        conn = init_db_for_theme(theme_name)
        try:
            from keywords_db import delete_keyword
            delete_keyword(conn, kw_id)
            self.send_response(302)
            self.send_header("Location", f"{self.prefix}/keywords")
            self.end_headers()
        finally:
            conn.close()

    def _handle_keywords_delete_group(self, params: dict):
        theme_name = self._theme
        group = params.get("group", "").strip()
        if not group:
            self._send_json({"ok": False, "error": "group required"})
            return
        conn = init_db_for_theme(theme_name)
        try:
            from keywords_db import delete_keyword_group
            delete_keyword_group(conn, group)
            self.send_response(302)
            self.send_header("Location", f"{self.prefix}/keywords")
            self.end_headers()
        finally:
            conn.close()

    def _handle_changelog(self):
        try:
            theme_name = self._theme
            t = THEMES[theme_name]
            prefix = self.prefix
            entries_html = ""
            for ver, date, desc in config.CHANGELOG:
                entries_html += f"""
                <div style="background:#1e2e40;border:1px solid #2a3a4a;border-radius:8px;padding:1rem 1.2rem;margin-bottom:0.8rem;">
                  <div style="display:flex;align-items:baseline;gap:0.8rem;margin-bottom:0.5rem;">
                    <span style="color:{t.dashboard_color_primary};font-weight:700;font-size:1rem;">{ver}</span>
                    <span style="color:#64748b;font-size:0.8rem;">{date}</span>
                  </div>
                  <div style="color:#94a3b8;font-size:0.85rem;line-height:1.7;white-space:pre-wrap;">{html.escape(desc)}</div>
                </div>"""
            page_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>更新历史 - {t.dashboard_title}</title>
<style>{get_css(t)}</style></head>
<body>
<div class="header"><div class="header-top"><div><h1>{t.app_name_cn}</h1><div class="subtitle">更新历史</div></div></div></div>
<div class="container" style="max-width:600px;padding-top:1.5rem;">
<div style="margin-bottom:1.5rem;"><a href="{prefix}/" style="color:{t.dashboard_color_primary};text-decoration:none;">← 返回首页</a></div>
<div style="margin-bottom:1rem;color:#64748b;font-size:0.85rem;">当前版本: <strong style="color:#94a3b8;">{config.VERSION}</strong></div>
{entries_html}
</div>
</body>
</html>"""
            self._send_html(page_html)
        except Exception as e:
            log.error(f"Changelog error: {e}")
            self._send_html(f"<h1>Error</h1><p>{str(e)}</p>", 500)

    # ── Trends ─────────────────────────────────────────────────────────

    def _handle_trends(self, params: dict):
        theme_name = self._theme
        t = THEMES[theme_name]
        prefix = self.prefix
        kw = params.get("kw", "").strip()
        days = int(params.get("days", "30"))

        conn = init_db_for_theme(theme_name)
        try:
            from keywords_db import get_merged_keywords
            merged_kw = get_merged_keywords(conn, t.keywords)

            page_html = get_header(t, theme_name)
            page_html += '<div class="container">'

            # Header
            page_html += '<div class="trend-header">'
            page_html += '<h2>关键词趋势</h2>'
            page_html += '<div class="trend-controls">'
            # Date range selector
            page_html += '<div class="trend-days">'
            for d, label in [("7", "7天"), ("30", "30天"), ("90", "90天")]:
                cls = "active" if str(days) == d else ""
                page_html += f'<a class="{cls}" href="{prefix}/trends?days={d}&kw={urllib.parse.quote(kw)}">{label}</a>'
            page_html += '</div>'
            page_html += '</div>'  # trend-controls
            page_html += '</div>'  # trend-header

            # Keyword group/keyword selector
            page_html += '<div class="trend-controls" style="margin-bottom:1rem;">'
            page_html += f'<form action="{prefix}/trends" method="get" style="display:flex;gap:0.5rem;flex-wrap:wrap;align-items:center;">'
            page_html += f'<input type="hidden" name="days" value="{days}">'
            # Keyword group dropdown
            page_html += '<select name="group" onchange="this.form.submit()">'
            page_html += '<option value="">-- 选择关键词组 --</option>'
            sel_group = params.get("group", "")
            for gname in sorted(merged_kw.keys()):
                gkw_count = len(merged_kw[gname])
                sel = ' selected' if gname == sel_group else ''
                page_html += f'<option value="{html.escape(gname)}"{sel}>{html.escape(gname)} ({gkw_count})</option>'
            page_html += '</select>'
            # Keyword dropdown (populated when group is selected)
            if sel_group and sel_group in merged_kw:
                page_html += '<select name="kw" onchange="this.form.submit()">'
                page_html += '<option value="">-- 选择关键词 --</option>'
                for k in merged_kw[sel_group]:
                    sel = ' selected' if k == kw else ''
                    page_html += f'<option value="{html.escape(k)}"{sel}>{html.escape(k)}</option>'
                page_html += '</select>'
            page_html += '</form>'
            page_html += '</div>'

            if kw:
                data = get_keyword_trend(conn, kw, days)
                total = sum(d["cnt"] for d in data)
                page_html += '<div class="trend-chart-box">'
                page_html += f'<h3>{html.escape(kw)} <span class="trend-count">共 {total} 篇</span></h3>'
                page_html += render_svg_bar_chart(data, bar_color=t.dashboard_color_primary)
                page_html += '</div>'
            else:
                top_kw = get_top_keywords(conn, days)
                if top_kw:
                    page_html += f'<p style="color:#64748b;margin-bottom:1rem;">热门关键词 TOP {len(top_kw)}</p>'
                    for kword, cnt in top_kw:
                        data = get_keyword_trend(conn, kword, days)
                        page_html += '<div class="trend-chart-box">'
                        page_html += f'<h3>{html.escape(kword)} <span class="trend-count">共 {cnt} 篇</span></h3>'
                        page_html += render_svg_bar_chart(data, width=600, height=180, bar_color=t.dashboard_color_primary)
                        page_html += '</div>'
                else:
                    page_html += '<div class="trend-empty">所选时间范围内无数据</div>'

            page_html += '</div>'
            page_html += render_footer(prefix)
            self._send_html(page_html)
        finally:
            conn.close()

    # ── AI Q&A ─────────────────────────────────────────────────────────

    @staticmethod
    def _format_answer_html(text: str) -> str:
        """Convert LLM markdown-style answer to safe HTML."""
        text = html.escape(text)
        # Citation links: [1] → <sup class="qa-cite"><a href="#source-1">[1]</a></sup>
        text = re.sub(r'\[(\d+)\]', r'<sup class="qa-cite"><a href="#source-\1">[\1]</a></sup>', text)
        # Bold
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        # Italic
        text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
        # Paragraphs
        paras = re.split(r'\n{2,}', text)
        return "\n".join(f"<p>{p.replace(chr(10), '<br>')}</p>" for p in paras if p.strip())

    def _handle_ask(self, params: dict):
        theme_name = self._theme
        t = THEMES[theme_name]
        prefix = self.prefix
        question = params.get("q", "").strip()

        page_html = get_header(t, theme_name)
        page_html += f'<div class="container" style="max-width:800px;">'
        page_html += '<h2 style="margin-bottom:1rem;">AI 问答</h2>'
        page_html += '<p style="color:#64748b;font-size:0.85rem;margin-bottom:1.5rem;">基于已采集的文章，回答技术相关问题</p>'

        # Search form
        page_html += f'<div class="qa-form">'
        page_html += f'<form action="{prefix}/ask" method="get" style="display:flex;gap:0.5rem;width:100%;">'
        q_val = html.escape(question)
        page_html += f'<input type="text" name="q" placeholder="输入你的问题..." value="{q_val}">'
        page_html += '<button type="submit">提问</button>'
        page_html += '</form></div>'

        if question:
            import time as _time
            from llm_client import create_completion

            page_html += '<div id="qa-result">'
            page_html += '<div class="qa-loading" id="qa-loading">正在分析问题并检索相关文章</div>'
            page_html += '</div>'

            conn = init_db_for_theme(theme_name)
            try:
                t0 = _time.time()
                rows, total = search_articles(conn, question, limit=15, offset=0)
                search_time = _time.time() - t0

                if not rows:
                    page_html += '<div class="qa-answer"><div class="qa-empty">未找到相关文章，请尝试换个问题。</div></div>'
                else:
                    # Build context from articles
                    context_parts = []
                    sources = []
                    for i, row in enumerate(rows, 1):
                        art_title = row["translated_title"] or row["title"] or ""
                        art_summary = (row["translated_summary"] or row["summary"] or "")[:300]
                        art_content = (row["translated_content"] or row["content"] or "")[:1500]
                        context_parts.append(
                            f"[{i}] Title: {art_title}\n"
                            f"    Source: {row.get('source', '')}\n"
                            f"    Published: {(row.get('published') or '')[:10]}\n"
                            f"    Summary: {art_summary}\n"
                            f"    Content: {art_content}"
                        )
                        sources.append({
                            "index": i, "id": row["id"],
                            "title": art_title,
                            "url": row.get("url", ""),
                            "source": row.get("source", ""),
                        })
                    context = "\n\n".join(context_parts)

                    # LLM call
                    system_prompt = (
                        "你是一个航天/国防技术分析师。请根据检索到的文章回答用户问题。\n"
                        "要求：\n"
                        "1. 使用中文回答\n"
                        "2. 用 [1], [2] 等标注信息来源\n"
                        "3. 如果文章中没有相关信息，请明确说明\n"
                        "4. 回答要具体、技术导向\n"
                        f"{'关注固体火箭发动机、冲压发动机、超燃冲压发动机、爆震发动机等技术领域。' if theme_name == 'news' else '关注空空导弹、导引头、制导系统、战斗部等技术领域。'}"
                    )
                    user_prompt = f"请根据以下检索到的文章，回答用户的问题。\n\n问题: {question}\n\n相关文章:\n{context}"

                    t1 = _time.time()
                    try:
                        answer = create_completion(
                            model=config.LLM_MODEL,
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt},
                            ],
                            max_tokens=2000,
                        )
                    except Exception:
                        answer = ""
                    llm_time = _time.time() - t1

                    page_html += '<div class="qa-answer">'
                    page_html += '<div class="qa-meta">'
                    page_html += f'<span>搜索到 {total} 篇相关文章 ({search_time:.1f}s)</span>'
                    page_html += f'<span>生成回答 ({llm_time:.1f}s)</span>'
                    page_html += '</div>'

                    if answer:
                        answer_html = self._format_answer_html(answer)
                        page_html += f'<div class="qa-content">{answer_html}</div>'
                    else:
                        page_html += '<div class="qa-empty">LLM 暂时不可用，请稍后再试。</div>'

                    page_html += '</div>'  # qa-answer

                    # Sources
                    if sources:
                        page_html += '<div class="qa-sources"><h3>参考来源</h3>'
                        for s in sources:
                            display_title = s["title"][:100] or "(无标题)"
                            page_html += (
                                f'<div class="qa-source-item">'
                                f'<span class="qa-source-index" id="source-{s["index"]}">[{s["index"]}]</span>'
                                f'<a href="{prefix}/article?id={html.escape(s["id"])}">{html.escape(display_title)}</a>'
                                f'<span class="qa-source-name">{html.escape(s["source"])}</span>'
                                f'</div>'
                            )
                        page_html += '</div>'
            finally:
                conn.close()

        # Back link
        page_html += f'<div style="text-align:center;padding:1rem 0;"><a href="{prefix}/" style="color:{t.dashboard_color_primary};">← 返回首页</a></div>'
        page_html += '</div>'
        page_html += render_footer(prefix)
        self._send_html(page_html)

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

        if route == "/favicon.ico":
            self._send_svg(self.FAVICON_SVG)
            return
        if route == "/":
            if params.get("search") == "1":
                self._handle_search(params)
            else:
                self._handle_page(params)
        elif route == "/article":
            self._handle_article(params)
        elif route == "/sources":
            self._handle_sources(params)
        elif route == "/poll-history":
            self._handle_poll_history(params)
        elif route == "/enable-source":
            self._handle_enable_source(params)
        elif route == "/monthly-report":
            self._handle_monthly_report(params)
        elif route == "/changelog":
            self._handle_changelog()
        elif route.startswith("/images/"):
            params["file"] = route[len("/images/"):]
            self._handle_images(params)
        elif route == "/archive":
            self._handle_archive(params)
        elif route == "/missing-content":
            self._handle_missing_content(params)
        elif route == "/keywords":
            self._handle_keywords_page(params)
        elif route == "/keywords/delete":
            self._handle_keywords_delete(params)
        elif route == "/trends":
            self._handle_trends(params)
        elif route == "/ask":
            self._handle_ask(params)
        else:
            t = THEMES[self._theme]
            h = get_header(t, self._theme)
            self._send_html(h + f'<div class="container"><h2 style="color:#475569;">404</h2><a href="/" style="color:{t.dashboard_color_primary};">← 返回首页</a></div>' + render_footer(self.prefix), 404)

    def do_POST(self):
        self._set_theme_from_path(self.path)
        full = self._strip_prefix(self.path)
        parsed = urllib.parse.urlparse(full)
        route = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8", errors="replace")
        form_params = urllib.parse.parse_qs(body)
        params = {k: v[0] for k, v in form_params.items()}

        if route == "/backfill-content":
            self._handle_backfill_content(params)
        elif route == "/backfill-content-single":
            self._handle_backfill_content_single(params)
        elif route == "/keywords/add":
            self._handle_keywords_add(params)
        elif route == "/keywords/delete-group":
            self._handle_keywords_delete_group(params)
        else:
            self._send_json({"ok": False, "error": "route not found"}, 404)
