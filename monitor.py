#!/usr/bin/env python3
"""
News Monitor - Core Engine
Fetches, filters, translates, archives, and notifies about news articles.
"""
import difflib
import hashlib
import html
import logging
import os
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import feedparser
import requests
from bs4 import BeautifulSoup

import config

# Domains that require proxy (GFW-blocked from China)
PROXY = os.environ.get("HTTP_PROXY", "http://127.0.0.1:7890")
NEEDS_PROXY_DOMAINS = {
    "bbc.com", "bbci.co.uk", "bbc.co.uk",
    "hnrss.org", "news.ycombinator.com", "ycombinator.com",
    "reuters.com", "reutersmedia.net",
    "news.google.com", "google.com",
    "missilethreat.csis.org",
    "csis.org",
    "overtdefense.com",
    "defence-blog.com",
    "defenceaviation.com",
    "defencetalk.com",
    "news.usni.org",
    "usni.org",
    "tandfonline.com",
    "arc.aiaa.org",
    "sciencedirect.com",
    "springer.com",
    "aiaa.org",
    "export.arxiv.org",
    "arxv.org",
    "nature.com",
    "esa.int",
    "lockheedmartin.com",
    "freepatentsonline.com",
    "gov.uk",
    "tass.com",
    "spacenews.com",
    "spacewatch.global",
}


def _needs_proxy(url: str) -> bool:
    from urllib.parse import urlparse
    host = urlparse(url).hostname or ""
    return any(host == d or host.endswith("." + d) for d in NEEDS_PROXY_DOMAINS)


def _validate_url(url: str) -> bool:
    """SSRF guard: only allow http/https, block private/internal IPs."""
    from urllib.parse import urlparse
    import ipaddress
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = (parsed.hostname or "").lower()
        if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1", "255.255.255.255", "fe80::1"):
            return False
        if host.endswith(".local") or host.endswith(".internal"):
            return False
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
                return False
        except ValueError:
            pass
        return True
    except Exception:
        return False


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(config.LOGGER_NAME)

# ── Date Parsing ──────────────────────────────────────────────────────────

_RSS_DATE_PATTERNS = [
    "%a, %d %b %Y %H:%M:%S %z",
    "%a, %d %b %Y %H:%M:%S %Z",
    "%d %b %Y %H:%M:%S %z",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%d",
]

# Timezone abbreviations that %Z can't reliably parse; strip them and add +0000
_TZ_RE = re.compile(r"\s+(EDT|EST|GMT|BST|CEST|CET|EEST|EET|WEST|WET|MST|PDT|PST)\b")
_START_DT = datetime.strptime(config.COLLECT_START_DATE, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _published_after_cutoff(published_str: str) -> bool:
    """Check if an article's published date is on or after COLLECT_START_DATE."""
    if not published_str:
        return True  # keep articles with unknown dates
    dt = _parse_date(published_str)
    if dt is None:
        return True
    return dt >= _START_DT


def _parse_date(date_str: str) -> datetime | None:
    """Try to parse a date string into a timezone-aware datetime."""
    if not date_str:
        return None
    text = date_str.strip()
    # Strip unreliable timezone abbreviations so %z/%Z patterns can match
    text = _TZ_RE.sub(" +0000", text)
    for pattern in _RSS_DATE_PATTERNS:
        try:
            dt = datetime.strptime(text, pattern)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt
    except (ValueError, TypeError):
        pass
    return None


def _normalize_date(date_str: str) -> str:
    """Parse a date string and return ISO 8601 (UTC), or empty string on failure."""
    dt = _parse_date(date_str)
    if dt is None:
        return date_str[:19] if date_str else ""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def article_type(source: str, url: str, author: str) -> str:
    """Classify article as 'paper' or 'news' based on source name and URL."""
    src_lower = source.lower()
    url_lower = url.lower()

    # ── Academic sources → paper ────────────────────────────────────────
    # Known academic publishers, journals, and preprint servers
    academic_markers = [
        "springer", "arxiv", "ieee", "sciencedirect", "elsevier", "nature.com",
        "mdpi", "tandfonline", "wiley", "sagepub", "acm.org",
        "aiaa", "jstor", "cambridge.org", "oxford academic",
        "cnki", "researchgate", "semanticscholar",
        "iopscience", "iop.org", "royalsociety", "science.org",
        "cell.com", "bmj.com", "nejm", "ama-assn",
        # Common journal name patterns
        "acta astronautica", "aerospace sci", "combustion and flame",
        "combustion sci", "chinese j. aeronautics", "defence technology",
        "propulsion & power", "propulsion and power",
        "journal of propulsion", "journal of guidance",
        "progress in aerospace", "annual review of",
    ]
    for m in academic_markers:
        if m in src_lower:
            return "paper"

    # Academic URL patterns
    url_paper = [
        "doi.org/", "arxiv.org/abs", "ieeexplore", "sciencedirect.com/science",
        "link.springer.com", "mdpi.com/", "tandfonline.com/doi",
    ]
    for p in url_paper:
        if p in url_lower:
            return "paper"

    # ── News sources → news ────────────────────────────────────────────
    news_markers = [
        # International defense / space news
        "defense news", "spacenews", "spaceflight now", "space.com",
        "nasa spaceflight", "european defence review", "the defense post",
        "breaking defense", "national defense mag", "the war zone",
        "the aviationist", "air & space forces", "defenceweb",
        "defense one", "military times", "janes", "shephard",
        "lockheed martin", "esa space engineering", "spacewatch global",
        "interesting engineering", "ars technica", "universe today",
        "jaxa", "european spaceflight",
        # Chinese news sources
        "央视新闻", "参考消息", "环球网", "中国新闻网",
        "bbc中文", "bbc news", "联合早报",
        "知乎", "hacker news",
    ]
    for m in news_markers:
        if m in src_lower:
            return "news"

    # ── Default ────────────────────────────────────────────────────────
    return "news"


# ── Database ──────────────────────────────────────────────────────────────


def init_db():
    """Initialize SQLite database and create tables if needed."""
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(config.DB_PATH))
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
    # Migrate old schema if needed (add columns that may not exist)
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

    # One-shot migration: normalize existing dates for correct sorting
    try:
        rows = conn.execute("SELECT id, published FROM articles").fetchall()
        changed = 0
        for rid, rpub in rows:
            normalized = _normalize_date(rpub)
            # Also handle dates truncated by a previous broken migration run
            if normalized == rpub and rpub and rpub[0:3] in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"):
                guess = rpub[:17].strip() + " 00:00:00 +0000"
                if _parse_date(guess):
                    normalized = _normalize_date(guess)
            if normalized and normalized != rpub:
                conn.execute("UPDATE articles SET published = ? WHERE id = ?", (normalized, rid))
                changed += 1
        if changed:
            conn.commit()
            log.info(f"Migrated {changed} article dates to ISO format")
    except sqlite3.OperationalError:
        pass  # table doesn't exist yet (first run)

    # poll_stats + source_stats tables
    for ddl in [
        """CREATE TABLE IF NOT EXISTS poll_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            duration_sec INTEGER NOT NULL,
            articles_found INTEGER NOT NULL,
            sources_count INTEGER NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS source_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_name TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            success INTEGER NOT NULL DEFAULT 1,
            articles_found INTEGER NOT NULL DEFAULT 0,
            error_msg TEXT DEFAULT ''
        )""",
        """CREATE TABLE IF NOT EXISTS source_config (
            source_name TEXT PRIMARY KEY,
            consecutive_failures INTEGER NOT NULL DEFAULT 0,
            disabled INTEGER NOT NULL DEFAULT 0,
            last_success_at TEXT DEFAULT '',
            last_error TEXT DEFAULT ''
        )""",
    ]:
        try:
            conn.execute(ddl)
        except sqlite3.OperationalError:
            pass
    conn.commit()

    # FTS5 full-text search
    try:
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
                title, summary, content, translated_title, translated_summary, translated_content,
                content=articles, content_rowid=rowid,
                tokenize='unicode61'
            )
        """)
        for trigger_ddl in [
            "CREATE TRIGGER IF NOT EXISTS articles_ai AFTER INSERT ON articles BEGIN "
            "INSERT INTO articles_fts(rowid, title, summary, content, translated_title, translated_summary, translated_content) "
            "VALUES (new.rowid, new.title, new.summary, new.content, new.translated_title, new.translated_summary, new.translated_content); END;",
            "CREATE TRIGGER IF NOT EXISTS articles_ad AFTER DELETE ON articles BEGIN "
            "INSERT INTO articles_fts(articles_fts, rowid, title, summary, content, translated_title, translated_summary, translated_content) "
            "VALUES ('delete', old.rowid, old.title, old.summary, old.content, old.translated_title, old.translated_summary, old.translated_content); END;",
            "CREATE TRIGGER IF NOT EXISTS articles_au AFTER UPDATE ON articles BEGIN "
            "INSERT INTO articles_fts(articles_fts, rowid, title, summary, content, translated_title, translated_summary, translated_content) "
            "VALUES ('delete', old.rowid, old.title, old.summary, old.content, old.translated_title, old.translated_summary, old.translated_content); "
            "INSERT INTO articles_fts(rowid, title, summary, content, translated_title, translated_summary, translated_content) "
            "VALUES (new.rowid, new.title, new.summary, new.content, new.translated_title, new.translated_summary, new.translated_content); END;",
        ]:
            conn.execute(trigger_ddl)

        # One-time rebuild for existing rows
        existing = conn.execute("SELECT COUNT(*) FROM articles_fts").fetchone()[0]
        total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        if existing < total:
            # Drop triggers before rebuild to avoid constraint errors during sync
            for _t in ["articles_au", "articles_ai", "articles_ad"]:
                try:
                    conn.execute(f"DROP TRIGGER IF EXISTS {_t}")
                except Exception:
                    pass
            conn.execute("INSERT INTO articles_fts(articles_fts) VALUES('rebuild')")
            # Recreate triggers
            for _td in [
                "CREATE TRIGGER IF NOT EXISTS articles_ai AFTER INSERT ON articles BEGIN "
                "INSERT INTO articles_fts(rowid, title, summary, content, translated_title, translated_summary, translated_content) "
                "VALUES (new.rowid, new.title, new.summary, new.content, new.translated_title, new.translated_summary, new.translated_content); END;",
                "CREATE TRIGGER IF NOT EXISTS articles_ad AFTER DELETE ON articles BEGIN "
                "INSERT INTO articles_fts(articles_fts, rowid, title, summary, content, translated_title, translated_summary, translated_content) "
                "VALUES ('delete', old.rowid, old.title, old.summary, old.content, old.translated_title, old.translated_summary, old.translated_content); END;",
                "CREATE TRIGGER IF NOT EXISTS articles_au AFTER UPDATE ON articles BEGIN "
                "INSERT INTO articles_fts(articles_fts, rowid, title, summary, content, translated_title, translated_summary, translated_content) "
                "VALUES ('delete', old.rowid, old.title, old.summary, old.content, old.translated_title, old.translated_summary, old.translated_content); "
                "INSERT INTO articles_fts(rowid, title, summary, content, translated_title, translated_summary, translated_content) "
                "VALUES (new.rowid, new.title, new.summary, new.content, new.translated_title, new.translated_summary, new.translated_content); END;",
            ]:
                conn.execute(_td)
    except Exception as e:
        log.warning(f"FTS5 not available, falling back to LIKE search: {e}")

    return conn


def article_exists(conn: sqlite3.Connection, article_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM articles WHERE id = ?", (article_id,)
    ).fetchone() is not None


def save_article(conn: sqlite3.Connection, article: dict) -> bool:
    """Save article to database. Returns True if new (inserted, not ignored)."""
    published = _normalize_date(article.get("published", ""))
    try:
        before = conn.total_changes
        conn.execute("""
            INSERT OR IGNORE INTO articles
                (id, title, url, source, published, fetched_at, summary,
                 matched_kw, relevance, translated_title, translated_summary, is_translated,
                 author, affiliation, event_group, event_title, translated_content, image_url,
                 content, article_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            article["id"],
            article["title"],
            article["url"],
            article["source"],
            published,
            article["fetched_at"],
            article.get("summary", "")[:2000],
            article.get("matched_kw", ""),
            article.get("relevance", 0),
            article.get("translated_title", ""),
            article.get("translated_summary", ""),
            1 if article.get("translated_title") else 0,
            article.get("author", ""),
            article.get("affiliation", ""),
            article.get("event_group", ""),
            article.get("event_title", ""),
            article.get("translated_content", ""),
            article.get("image_url", ""),
            article.get("content", "")[:50000],
            article.get("article_type", ""),
        ))
        conn.commit()
        return conn.total_changes > before
    except Exception as e:
        log.error(f"DB save error: {e}")
        return False


def get_articles(conn: sqlite3.Connection, limit=50, offset=0, unread_only=False, type_filter="", starred_only=False):
    query = "SELECT * FROM articles WHERE 1=1"
    params: list = []
    if unread_only:
        query += " AND is_read = 0"
    if starred_only:
        query += " AND is_starred = 1"
    if type_filter in ("paper", "news"):
        query += " AND article_type = ?"
        params.append(type_filter)
    query += " ORDER BY published DESC, relevance DESC LIMIT ? OFFSET ?"
    return conn.execute(query, (*params, limit, offset)).fetchall()


def mark_read(conn: sqlite3.Connection, article_id: str):
    conn.execute("UPDATE articles SET is_read = 1 WHERE id = ?", (article_id,))
    conn.commit()


def search_articles(conn: sqlite3.Connection, keyword: str, limit=50, offset=0):
    """FTS5 full-text search with LIKE fallback. Returns (rows, total_count)."""
    has_cjk = bool(re.search(r"[一-鿿㐀-䶿]", keyword))
    if not has_cjk:
        safe_kw = keyword.replace('"', '""')
        try:
            rows = conn.execute(
                "SELECT a.* FROM articles a "
                "JOIN articles_fts fts ON a.rowid = fts.rowid "
                "WHERE articles_fts MATCH ? "
                "ORDER BY rank LIMIT ? OFFSET ?",
                (f'"{safe_kw}"', limit, offset),
            ).fetchall()
            total = conn.execute(
                "SELECT COUNT(*) FROM articles_fts WHERE articles_fts MATCH ?",
                (f'"{safe_kw}"',),
            ).fetchone()[0]
            return rows, total
        except Exception:
            pass

    # Fallback: LIKE search (also used for CJK queries since unicode61
    # tokenizer can't handle Chinese multi-character phrases)
    rows = conn.execute(
        "SELECT * FROM articles WHERE title LIKE ? OR summary LIKE ? "
        "OR content LIKE ? OR translated_title LIKE ? "
        "OR translated_summary LIKE ? OR translated_content LIKE ? "
        "ORDER BY published DESC, relevance DESC LIMIT ? OFFSET ?",
        (f"%{keyword}%",) * 6 + (limit, offset),
    ).fetchall()
    total = conn.execute(
        "SELECT COUNT(*) FROM articles WHERE title LIKE ? OR summary LIKE ? "
        "OR content LIKE ? OR translated_title LIKE ? "
        "OR translated_summary LIKE ? OR translated_content LIKE ?",
        (f"%{keyword}%",) * 6,
    ).fetchone()[0]
    return rows, total


def get_articles_for_briefing(conn: sqlite3.Connection, days=7) -> list[dict]:
    """Get articles from the last N days for weekly briefing."""
    cursor = conn.execute(
        "SELECT * FROM articles WHERE fetched_at > datetime('now', ? || ' days') "
        "ORDER BY relevance DESC, published DESC",
        (f"-{days}",),
    )
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in rows]


def get_source_status(conn: sqlite3.Connection) -> list[dict]:
    """Return latest fetch status per RSS source."""
    cursor = conn.execute("""
        SELECT s.source_name, s.success, s.articles_found, s.error_msg, s.fetched_at
        FROM source_stats s
        WHERE s.id IN (SELECT MAX(id) FROM source_stats GROUP BY source_name)
        ORDER BY s.source_name
    """)
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_articles_by_month(conn: sqlite3.Connection, year_month: str,
                          limit=50, offset=0, unread_only=False,
                          type_filter="", starred_only=False):
    """Get articles for a specific year-month (format: '2025-03')."""
    query = "SELECT * FROM articles WHERE strftime('%Y-%m', published) = ?"
    params: list = [year_month]
    if unread_only:
        query += " AND is_read = 0"
    if starred_only:
        query += " AND is_starred = 1"
    if type_filter in ("paper", "news"):
        query += " AND article_type = ?"
        params.append(type_filter)
    query += " ORDER BY published DESC, relevance DESC LIMIT ? OFFSET ?"
    return conn.execute(query, (*params, limit, offset)).fetchall()


def get_available_months(conn: sqlite3.Connection) -> list[str]:
    """Return sorted list of year-month strings that have articles."""
    rows = conn.execute(
        "SELECT DISTINCT strftime('%Y-%m', published) AS ym FROM articles "
        "WHERE published != '' AND published IS NOT NULL "
        "ORDER BY ym DESC"
    ).fetchall()
    return [r[0] for r in rows]


# ── Article ID ────────────────────────────────────────────────────────────


def make_article_id(url: str, title: str) -> str:
    raw = f"{url}#{title[:100].lower().strip()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


# ── Event Grouping ──────────────────────────────────────────────────────────


def _normalize_title(title: str) -> str:
    """Normalize title for similarity comparison."""
    t = title.lower().strip()
    t = t.rstrip(".。!！?？,:：;；·")
    for prefix in ["breaking: ", "update: ", "新闻：", "快讯：", "最新：", "重磅："]:
        if t.startswith(prefix):
            t = t[len(prefix):]
            break
    return t


def _title_similarity(t1: str, t2: str) -> float:
    n1 = _normalize_title(t1)
    n2 = _normalize_title(t2)
    return difflib.SequenceMatcher(None, n1, n2).ratio()


def find_event_group(conn: sqlite3.Connection, title: str,
                     published: str) -> tuple[str, str]:
    """Find an existing event group for this article, or create a new one.

    Returns (event_group_id, event_title).
    """
    recent = conn.execute(
        "SELECT event_group, event_title, title FROM articles "
        "WHERE event_group != '' "
        "AND published > datetime('now', '-14 days') "
        "ORDER BY published DESC"
    ).fetchall()

    best_match = None
    best_score = 0.0

    for eg_id, eg_title, existing_title in recent:
        score = _title_similarity(title, existing_title)
        if score > best_score:
            best_score = score
            best_match = (eg_id, eg_title or existing_title)

    if best_match and best_score >= 0.55:
        return best_match

    new_id = hashlib.sha256(
        _normalize_title(title).encode()
    ).hexdigest()[:16]
    return (new_id, title)


def get_event_grouped_articles(conn: sqlite3.Connection,
                               limit=50, offset=0, unread_only=False, type_filter="", starred_only=False):
    """Return articles ordered by event_group (grouped together, most recent first).

    Returns list of (row, is_group_start) tuples where is_group_start is True
    when a new event group begins.
    """
    query = "SELECT * FROM articles WHERE 1=1"
    params: list = []
    if unread_only:
        query += " AND is_read = 0"
    if starred_only:
        query += " AND is_starred = 1"
    if type_filter in ("paper", "news"):
        query += " AND article_type = ?"
        params.append(type_filter)
    query += (" ORDER BY "
              "CASE WHEN event_group != '' THEN event_group ELSE id END DESC, "
              "published DESC, relevance DESC "
              "LIMIT ? OFFSET ?")
    rows = conn.execute(query, (*params, limit, offset)).fetchall()

    result = []
    last_group = None
    for row in rows:
        eg = row[16] if len(row) > 16 else ""
        is_start = (eg != "" and eg != last_group)
        result.append((row, is_start))
        if eg:
            last_group = eg
    return result


# ── RSS Fetching ──────────────────────────────────────────────────────────


def fetch_rss(url: str, timeout=30) -> list[dict]:
    """Fetch RSS feed and return raw entries."""
    entries = []
    try:
        # Fetch via requests (with proxy if needed), then parse with feedparser
        proxies = None
        if _needs_proxy(url):
            proxies = {"http": PROXY, "https": PROXY}
        ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        resp = requests.get(url, proxies=proxies, timeout=timeout,
                            headers={"User-Agent": ua})
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
        if feed.bozo and not feed.entries:
            log.warning(f"Feed parse error for {url}: {feed.bozo_exception}")
            return entries
        for entry in feed.entries:
            if len(entries) >= 30:
                break
            author = ""
            if hasattr(entry, "author") and entry.author:
                author = entry.author.strip()
            elif hasattr(entry, "authors") and entry.authors:
                author = ", ".join(
                    a.get("name", "") for a in entry.authors if a.get("name")
                )
            e = {
                "title": (entry.get("title") or "").strip(),
                "url": (entry.get("link") or "").strip(),
                "summary": (entry.get("summary") or entry.get("description") or "").strip(),
                "published": entry.get("published") or entry.get("updated", ""),
                "source": url,
                "author": author,
            }
            if e["summary"]:
                e["summary"] = BeautifulSoup(e["summary"], "lxml").get_text(
                    separator=" ", strip=True
                )[:2000]
            entries.append(e)
        log.info(f"Fetched {len(entries)} entries from RSS: {url[:60]}...")
    except Exception as e:
        log.error(f"RSS fetch error for {url}: {e}")
    return entries


# ── Full Article Content ──────────────────────────────────────────────────


def _is_anti_bot_page(html: str) -> bool:
    """Detect if the page is an anti-bot / CAPTCHA challenge."""
    if len(html) < 5000:
        keywords = [
            "captcha", "安全验证", "verify", "bot check",
            "just a moment", "enable javascript", "请开启javascript",
            "cf-challenge", "challenge-platform", "checking your browser",
        ]
        text_lower = BeautifulSoup(html, "lxml").get_text(separator=" ", strip=True)[:300].lower()
        return any(kw in text_lower for kw in keywords)
    return False


def _extract_with_readability(html: str) -> str:
    """Extract article content using Mozilla's Readability algorithm."""
    try:
        from readability import Document
        doc = Document(html)
        summary_html = doc.summary()
        soup = BeautifulSoup(summary_html, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside",
                          "iframe", "noscript", "form", "button", "svg",
                          "figure", "figcaption"]):
            tag.decompose()
        # Remove elements with common junk classes/ids
        for el in soup.find_all(class_=re.compile(
                r"(related|recommend|suggest|widget|ad-|advertisement|sponsor|social|share|comment|"
                r"sidebar|footer|header|nav|cookie|popup|modal|overlay|subscribe|newsletter|"
                r"promo|partner|banner|disclaimer)", re.I)):
            el.decompose()
        for el in soup.find_all(id=re.compile(
                r"(related|recommend|suggest|widget|ad-|advertisement|sponsor|social|share|comment|"
                r"sidebar|footer|header|nav|cookie|popup|modal|overlay|subscribe|newsletter)", re.I)):
            el.decompose()
        text = soup.get_text(separator="\n", strip=True)
        text = _clean_extracted_text(text)
        return text
    except Exception as e:
        log.debug(f"Readability extraction failed: {e}")
        return ""


def _extract_largest_cluster(html: str, min_len=200) -> str:
    """Fallback: find the largest cluster of paragraphs/text blocks."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside",
                      "iframe", "noscript", "form", "button", "svg",
                      "figure", "figcaption"]):
        tag.decompose()
    # Remove known junk elements by class/id
    for el in soup.find_all(class_=re.compile(
            r"(related|recommend|suggest|widget|ad-|advertisement|sponsor|social|share|comment|"
            r"sidebar|footer|header|nav|cookie|popup|modal|overlay|subscribe|newsletter|"
            r"promo|partner|banner|disclaimer)", re.I)):
        el.decompose()
    for el in soup.find_all(id=re.compile(
            r"(related|recommend|suggest|widget|ad-|advertisement|sponsor|social|share|comment|"
            r"sidebar|footer|header|nav|cookie|popup|modal|overlay|subscribe|newsletter)", re.I)):
        el.decompose()

    # Score elements and pick the most article-like one
    candidates = []
    for el in soup.find_all(["article", "main", "div", "section", "pre", "td",
                              "blockquote", "li", "p"]):
        el_text = el.get_text(separator="\n", strip=True)
        el_len = len(el_text)
        if el_len > min_len:
            # Penalise elements containing junk indicators in their own text
            lower = el_text.lower()
            if any(kw in lower for kw in [
                "related articles", "you may also like", "recommended for you",
                "subscribe to", "newsletter", "follow us", "share this",
                "click here", "advertisement", "sponsored content",
            ]):
                el_len = int(el_len * 0.5)
            candidates.append((el_len, el_text))

    if not candidates:
        body = soup.find("body")
        if body:
            return _clean_extracted_text(body.get_text(separator="\n", strip=True)[:8000])
        return ""

    candidates.sort(reverse=True)
    best_len, best_text = candidates[0]

    if len(candidates) > 1 and candidates[1][0] > best_len * 0.5:
        best_text = best_text + "\n\n" + candidates[1][1]

    return _clean_extracted_text(best_text[:8000])


# ── Junk patterns for cleaning extracted text ──────────────────────────────

_JUNK_PATTERNS = [
    # Social / share
    r"^(share|tweet|pin|like|follow|subscribe|comment|reply)\b",
    r"^(facebook|twitter|linkedin|reddit|whatsapp|telegram|weibo|wechat)\b",
    r"follow us on",
    r"^@\w+\s*$",  # bare social handles
    # Ads / sponsored
    r"^(advertisement|sponsored|promoted|ad\b)",
    r"click here (to|for)",
    r"^(read more|view more|see more|show more)",
    # Related content
    r"^(related|recommended|suggested|more from|more on)\b",
    r"you may also (like|enjoy|be interested)",
    r"^(popular|trending|most read|top stories)",
    # Newsletters / subscribe
    r"(subscribe|newsletter|sign.?up|register)",
    r"^enter your (email|address)",
    # Cookie / consent
    r"(cookie|privacy|gdpr|consent)",
    # Comments
    r"^(leave a (reply|comment)|add a comment|join the discussion)",
    r"(comments?( are)? (closed|disabled))",
    # Pagination within articles
    r"^(page \d+ of \d+|<\s*prev|\d+\s*/\s*\d+)",
    # Empty / trivial
    r"^\s*$",
    r"^[-–—=*•·]{3,}$",
    r"^\d+\s*$",
    # Readability leftover (image captions, byline remnants)
    r"^(image|photo|picture|credit|source|via|hat tip):",
    r"^(ap\s*[-–—]|reuters|afp|getty)",
]


def _clean_extracted_text(text: str) -> str:
    """Remove junk lines from extracted article text."""
    lines = text.split("\n")
    clean = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Skip lines matching junk patterns
        if any(re.search(p, stripped, re.I) for p in _JUNK_PATTERNS):
            continue
        # Skip single-symbol/emoji lines
        if len(stripped) <= 2:
            continue
        # Skip lines that are just numbers (page numbers, etc.)
        if re.match(r"^[\d\s,.%\-–—/\[\]()]+$", stripped):
            continue
        clean.append(stripped)
    return "\n".join(clean)


def fetch_article_content(url: str, timeout=15) -> Optional[dict]:
    """Fetch full article HTML, extract text using multiple strategies.

    Tries, in order:
      1. Readability algorithm (Mozilla Reader Mode)
      2. Largest paragraph cluster heuristic
    Falls back gracefully for anti-bot / blocked pages.
    """
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]
    if not _validate_url(url):
        log.debug(f"URL blocked by SSRF guard: {url[:80]}")
        return None

    for ua in user_agents:
        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
        }
        try:
            proxies = None
            if _needs_proxy(url):
                proxies = {"http": PROXY, "https": PROXY}
            r = requests.get(url, headers=headers, proxies=proxies, timeout=timeout, allow_redirects=False)
            # Check redirect target if redirected
            if r.is_redirect or r.is_permanent_redirect:
                redirect_url = r.headers.get("Location", "")
                if redirect_url and not _validate_url(redirect_url):
                    log.debug(f"Redirect blocked by SSRF guard: {redirect_url[:80]}")
                    return None
            r.raise_for_status()
            content_type = r.headers.get("content-type", "")
            if "html" not in content_type.lower():
                return None
            raw_html = r.text

            if _is_anti_bot_page(raw_html):
                log.debug(f"Anti-bot page detected for {url}")
                continue

            soup = BeautifulSoup(raw_html, "lxml")
            author = ""
            affiliation = ""
            image_url = ""

            # Extract og:image for article thumbnail
            og_image = soup.find("meta", attrs={"property": "og:image"}) or soup.find("meta", attrs={"name": "og:image"})
            if og_image and og_image.get("content"):
                url_candidate = og_image["content"].strip()
                if not re.search(r"(logo|avatar|favicon|banner)", url_candidate, re.I):
                    image_url = url_candidate
            if not image_url:
                # Collect all candidate images and score them, pick the best
                content_areas = soup.find_all(["article", "main", "div", "section"],
                                               class_=re.compile(r"(content|post|article|entry|main|text|body)", re.I))
                if not content_areas:
                    content_areas = [soup]
                candidates = []
                for area in content_areas:
                    for img in area.find_all("img", src=re.compile(r"https?://")):
                        src = img.get("src", "").strip()
                        alt = img.get("alt", "") or ""
                        if not src or src.endswith((".svg", ".gif")):
                            continue
                        if re.search(r"(logo|avatar|favicon|banner|icon|badge)", src, re.I):
                            continue
                        if re.search(r"(logo|avatar|favicon|banner|icon|badge)", alt, re.I):
                            continue
                        # Extract width/height from attributes or inline style
                        w = img.get("width")
                        h = img.get("height")
                        style = img.get("style", "") or ""
                        if not w or not w.isdigit():
                            mw = re.search(r"width\s*:\s*(\d+)", style)
                            w = mw.group(1) if mw else "0"
                        if not h or not h.isdigit():
                            mh = re.search(r"height\s*:\s*(\d+)", style)
                            h = mh.group(1) if mh else "0"
                        w_int = int(w) if w and w.isdigit() else 0
                        h_int = int(h) if h and h.isdigit() else 0
                        # If no explicit dimensions, try to extract from URL
                        # (e.g. "w/500", "width/800", "thumbnail/90x90")
                        if w_int == 0:
                            mw_url = re.search(r"[/_]w[/_](\d{3,4})([/_]|$)", src)
                            if not mw_url:
                                mw_url = re.search(r"[?&]width[/=](\d{3,4})", src)
                            if mw_url:
                                w_int = int(mw_url.group(1))
                                # Infer height from thumbnail patterns
                                mh_url = re.search(r"thumbnail[/_](\d+)x(\d+)", src)
                                if mh_url:
                                    h_int = int(mh_url.group(2))
                        # Skip tiny images and avatars
                        if re.search(r"(avatar|default_user_pic|default_avatar)", src, re.I):
                            continue
                        if w_int < 100 and w_int != 0:
                            continue
                        # Score: prefer wider, landscape images with meaningful alt text
                        score = w_int if w_int > 0 else 100  # base score for unknown-width images
                        if h_int > 0 and w_int > h_int:
                            score += 50  # landscape bonus
                        if len(alt) > 10:
                            score += 30  # descriptive alt text
                        # Penalize GIFs — often decorative/irrelevant
                        if ".gif" in src:
                            score -= 80
                        # Slight bonus for images appearing earlier in the page
                        score += max(0, 10 - len(candidates))
                        candidates.append((score, src))
                if candidates:
                    candidates.sort(key=lambda x: -x[0])
                    image_url = candidates[0][1]

            meta_authors = soup.find_all("meta", attrs={"name": re.compile(r"author|citation_author", re.I)})
            if meta_authors:
                author = "; ".join(m.get("content", "") for m in meta_authors if m.get("content"))
            if not affiliation:
                meta_affils = soup.find_all("meta", attrs={"name": re.compile(r"citation_author_institution|citation_author_affiliation", re.I)})
                if meta_affils:
                    affiliation = "; ".join(m.get("content", "") for m in meta_affils if m.get("content"))

            if not author:
                for cls in ["author", "authors", "byline", "article-author"]:
                    el = soup.find(class_=re.compile(cls, re.I))
                    if el:
                        author = el.get_text(separator=", ", strip=True)[:200]
                        break

            text = _extract_with_readability(raw_html)
            if len(text) < 300:
                text = _extract_largest_cluster(raw_html)

            return {
                "text": text[:8000],
                "author": author,
                "affiliation": affiliation,
                "image_url": image_url,
            }
        except requests.RequestException as e:
            log.debug(f"Content fetch failed for {url} (UA: {ua[:30]}...): {e}")
            continue

    log.debug(f"All UAs failed for {url}")
    return None


# ── Keyword Filtering ────────────────────────────────────────────────────


def keyword_match(text: str) -> list[str]:
    """Check if text matches any keywords. Returns matched keywords."""
    text_lower = text.lower()
    matched = []
    for kw in config.ALL_KEYWORDS:
        if kw.lower() in text_lower:
            matched.append(kw)
    return matched


def relevance_score(matched: list[str], title: str, summary: str) -> int:
    """Score article relevance 0-100 based on where keywords hit."""
    score = 0
    for kw in matched:
        short_kw = len(kw.split()) <= 3
        in_title = kw.lower() in title.lower()
        in_summary = kw.lower() in summary.lower()
        if in_title:
            score += 25 if short_kw else 20
        elif in_summary:
            score += 15 if short_kw else 10
        else:
            score += 5
    has_cjk = bool(re.search(r"[一-鿿]", f"{title} {summary}"))
    if has_cjk:
        score = int(score * 1.3)
    return min(score, 100)


# ── LLM Filtering ────────────────────────────────────────────────────────


def _get_llm_text_block(resp) -> str:
    """Extract text from Anthropic response, handling thinking blocks."""
    for block in resp.content:
        if hasattr(block, "text"):
            return block.text.strip()
    return ""


def llm_filter(article: dict) -> bool:
    """Use LLM to determine if article is relevant. Returns True if relevant."""
    if not config.USE_LLM_FILTER or not config.LLM_API_KEY:
        return True

    prompt = config.LLM_FILTER_PROMPT.format(
        title=article["title"],
        summary=article.get("summary", "")[:500],
    )

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=config.LLM_API_KEY)
        resp = client.messages.create(
            model=config.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
        )
        answer = _get_llm_text_block(resp).upper()
        log.info(f"LLM filter for '{article['title'][:50]}...': {answer}")
        return answer == "YES"
    except Exception as e:
        log.warning(f"LLM filter error (defaulting to accept): {e}")
        return True


# ── Translation ───────────────────────────────────────────────────────────


def translate_article(article: dict) -> dict:
    """Translate article to Chinese. Returns article dict with translation fields."""
    from translator import translate_article as do_translate
    from translator import translate_content as do_translate_content
    from translator import contains_chinese
    if not config.TRANSLATE_TO_CHINESE:
        return article

    result = do_translate(article["title"], article.get("summary", ""))
    if result:
        article["translated_title"] = result.get("title", article["title"])
        article["translated_summary"] = result.get("summary", article.get("summary", ""))
    # Translate full content if available and not already Chinese
    content = article.get("content", "")
    if content and len(content) > 500 and not contains_chinese(content):
        translated = do_translate_content(content)
        if translated:
            article["translated_content"] = translated
    return article


# ── Archive Snapshot ──────────────────────────────────────────────────────


def save_snapshot(article_id: str, content: str) -> Optional[Path]:
    """Save full article content to disk."""
    if not content:
        return None
    config.ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    path = config.ARCHIVE_DIR / f"{article_id}.html"
    page = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Archived Article</title></head>
<body>
<pre style="white-space:pre-wrap;font-family:sans-serif;line-height:1.6;">
{html.escape(content)}
</pre>
</body>
</html>"""
    path.write_text(page, encoding="utf-8")
    return path


# ── Main Polling Logic ────────────────────────────────────────────────────


def poll_once(conn: sqlite3.Connection, dry_run=False, skip_llm=False) -> list[dict]:
    """Run one polling cycle. Returns list of new articles found."""
    new_articles = []
    total_keyword_matches = 0

    # Parallel RSS fetching
    source_entries: list[tuple[str, list[dict]]] = []
    all_source_names = set(config.RSS_SOURCES.keys())
    fetched_names: set[str] = set()
    source_errors: list[tuple[str, str]] = []

    # Skip disabled sources
    disabled_sources: set[str] = set()
    try:
        dr = conn.execute("SELECT source_name FROM source_config WHERE disabled=1").fetchall()
        disabled_sources = {r[0] for r in dr}
        if disabled_sources:
            log.info(f"Skipping {len(disabled_sources)} disabled source(s): {', '.join(sorted(disabled_sources))[:200]}")
    except Exception:
        pass

    with ThreadPoolExecutor(max_workers=3) as pool:
        fut_map = {pool.submit(fetch_rss, url): name for name, url in config.RSS_SOURCES.items() if name not in disabled_sources}
        for fut in as_completed(fut_map, timeout=300):
            name = fut_map[fut]
            try:
                entries = fut.result(timeout=30)
                source_entries.append((name, entries))
                fetched_names.add(name)
            except Exception as e:
                log.warning(f"RSS fetch failed for {name}, retrying once: {e}")
                try:
                    url = config.RSS_SOURCES.get(name)
                    entries = fetch_rss(url)
                    source_entries.append((name, entries))
                    fetched_names.add(name)
                    log.info(f"Retry succeeded for {name}")
                except Exception as e2:
                    log.error(f"RSS fetch failed for {name} (after retry): {e2}")
                    source_errors.append((name, str(e2)[:200]))

    # Mark sources that timed out or never returned
    now_iso = datetime.now(timezone.utc).isoformat()
    for name in all_source_names - fetched_names:
        source_errors.append((name, "timeout or no response"))

    # Persist source stats
    try:
        conn.executemany(
            "INSERT INTO source_stats (source_name, fetched_at, success, articles_found, error_msg) "
            "VALUES (?, ?, ?, ?, ?)",
            [(name, now_iso, 0, 0, err) for name, err in source_errors]
            + [(name, now_iso, 1, len(entries), "")
               for name, entries in source_entries],
        )

        # Update source_config (consecutive failure tracking)
        for name, err in source_errors:
            conn.execute("""
                INSERT INTO source_config (source_name, consecutive_failures, disabled, last_error)
                VALUES (?, 1, 0, ?)
                ON CONFLICT(source_name) DO UPDATE SET
                    consecutive_failures = consecutive_failures + 1,
                    disabled = CASE WHEN consecutive_failures + 1 >= 3 THEN 1 ELSE 0 END,
                    last_error = excluded.last_error
            """, (name, err[:200]))
        for name, entries in source_entries:
            conn.execute("""
                INSERT INTO source_config (source_name, consecutive_failures, disabled, last_success_at)
                VALUES (?, 0, 0, ?)
                ON CONFLICT(source_name) DO UPDATE SET
                    consecutive_failures = 0, disabled = 0,
                    last_success_at = excluded.last_success_at, last_error = ''
            """, (name, now_iso))
        conn.commit()
    except Exception as e:
        log.error(f"Failed to save source stats: {e}")

    seen_titles: list[tuple[str, str]] = []

    for source_name, raw_entries in source_entries:
        for entry in raw_entries:
            if not entry["title"] or not entry["url"]:
                continue
            if not _validate_url(entry["url"]):
                log.debug(f"Article URL blocked by SSRF guard: {entry['url'][:80]}")
                continue

            article_id = make_article_id(entry["url"], entry["title"])

            # Skip if already in DB (by URL-based ID)
            if article_exists(conn, article_id):
                continue

            # Date filter: skip articles published before COLLECT_START_DATE
            if not _published_after_cutoff(entry.get("published", "")):
                log.debug(f"Before cutoff, skipping: {entry['title'][:60]}...")
                continue

            # Title-based dedup: check against DB (fetched in last 7 days) AND current batch
            recent = conn.execute(
                "SELECT title, source FROM articles WHERE fetched_at > datetime('now', '-7 days')"
            ).fetchall()
            all_titles_with_src = [(t[0], t[1]) for t in recent] + seen_titles
            is_dupe = False
            for t, src in all_titles_with_src:
                sim = _title_similarity(entry["title"], t)
                threshold = 0.55 if src == source_name else 0.60
                if sim > threshold:
                    log.info(f"Title similar ({sim:.2f}), skipping: {entry['title'][:60]}...")
                    is_dupe = True
                    break
            if is_dupe:
                continue

            # First pass: keyword filter
            matched = keyword_match(f"{entry['title']} {entry['summary']}")
            if not matched:
                continue
            total_keyword_matches += 1

            # Exclusion filter: reject non-technical content (calls for papers, etc.)
            text = f"{entry['title']} {entry['summary']}".lower()
            if any(p.lower() in text for p in config.EXCLUDE_PATTERNS):
                log.info(f"Excluded by pattern: {entry['title'][:60]}...")
                continue

            # Full content fetch
            result = fetch_article_content(entry["url"])
            content = result["text"] if result else ""
            page_author = result["author"] if result and result.get("author") else ""
            page_affil = result["affiliation"] if result and result.get("affiliation") else ""

            effective_author = entry.get("author", "") or page_author

            # Second pass: LLM filter (if enabled)
            article_data = {**entry, "content": content or ""}
            if not skip_llm and not llm_filter(article_data):
                log.info(f"LLM rejected: {entry['title'][:60]}...")
                continue

            score = relevance_score(matched, entry["title"], entry["summary"])

            if score < config.MIN_RELEVANCE_SCORE:
                log.debug(f"Score too low ({score}): {entry['title'][:60]}...")
                continue

            article = {
                "id": article_id,
                "title": entry["title"],
                "url": entry["url"],
                "source": source_name,
                "published": entry.get("published", ""),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "summary": entry.get("summary", ""),
                "matched_kw": ", ".join(matched),
                "relevance": score,
                "content": content,
                "author": effective_author,
                "affiliation": page_affil,
                "image_url": result["image_url"] if result else "",
                "translated_title": "",
                "translated_summary": "",
                "translated_content": "",
                "article_type": article_type(source_name, entry["url"], effective_author),
            }

            # Translate to Chinese
            if not dry_run and config.TRANSLATE_TO_CHINESE:
                article = translate_article(article)
                from translator import contains_chinese
                if article and not article.get("translated_title") and contains_chinese(article.get("title", "")):
                    article["translated_title"] = article["title"]
                    article["translated_summary"] = article.get("summary", "")

            if not dry_run:
                # Assign or create event group before saving (if theme supports it)
                if config.HAS_EVENT_GROUPING:
                    eg_id, eg_title = find_event_group(
                        conn, article["title"], article.get("published", "")
                    )
                    article["event_group"] = eg_id
                    article["event_title"] = eg_title

                if save_article(conn, article):
                    if content:
                        save_snapshot(article_id, content)
                    seen_titles.append((article["title"], source_name))
                    new_articles.append(article)
                    display_title = (
                        article.get("translated_title") or article["title"]
                    )[:70]
                    log.info(
                        f"[{source_name}] New: {display_title}... "
                        f"(score={score}, kw={', '.join(matched[:3])})"
                    )

    log.info(f"Keyword matches: {total_keyword_matches}, LLM-accepted: {len(new_articles)}")
    return new_articles


# Keywords suggesting the author field contains embedded affiliation data
_AFFILIATION_KEYWORDS = [
    "department", "university", "institute", "laboratory", "lab", "college",
    "school of", "faculty of", "centre of", "center for", "research center",
    "corp", "inc", "ltd", "aerospace", "technologies", "limited",
]

# Known journalist sources → use publication name as affiliation
_JOURNALIST_SOURCES = {
    "edr magazine": "European Defence Review / EDR Magazine",
    "european defence review": "European Defence Review / EDR Magazine",
    "spaceflight now": "Spaceflight Now",
    "the war zone": "The War Zone",
    "realcleardefense": "RealClearDefense",
    "defense news": "Defense News",
    "breaking defense": "Breaking Defense",
    "janes": "Janes",
}


def _parse_embedded_affiliation(author_field: str) -> str | None:
    """Check if the author field already has affiliation data embedded.
    Some RSS feeds concatenate author names + department + institution."""
    words = author_field.split()
    # If the field is very long (>10 words), it likely includes affiliation
    if len(words) < 8:
        return None
    # Look for affiliation indicator keywords in the tail of the string
    lower = author_field.lower()
    for kw in _AFFILIATION_KEYWORDS:
        idx = lower.find(kw)
        if idx != -1:
            return author_field[idx:].rstrip(";., ")
    return None


def _source_based_affiliation(source: str) -> str | None:
    """Return affiliation based on known journalist sources."""
    source_lower = source.lower()
    for key, affil in _JOURNALIST_SOURCES.items():
        if key in source_lower:
            return affil
    return None


def backfill_affiliations(dry_run=False):
    """Backfill missing author affiliations using multiple strategies:
    1. Parse embedded affiliation from author field
    2. Source-based inference for journalists
    3. Re-fetch article HTML for citation meta tags
    4. DuckDuckGo web search + LLM reasoning
    5. LLM inference as final fallback
    """
    from collections import OrderedDict

    conn = init_db()
    try:
        rows = conn.execute(
            "SELECT id, author, title, source, url FROM articles "
            "WHERE author != '' AND author IS NOT NULL "
            "AND (affiliation IS NULL OR affiliation = '')"
        ).fetchall()
        log.info(f"Found {len(rows)} articles with author but no affiliation")

        # Group by normalized author name
        author_groups: dict[str, list[tuple[str, str, str, str, str]]] = OrderedDict()
        for rid, author, title, source, url in rows:
            norm = author.split(";")[0].split(",")[0].strip().lower()
            if norm not in author_groups:
                author_groups[norm] = []
            author_groups[norm].append((rid, author, title, source, url))

        total_updated = 0

        def _update_author_articles(author_str: str, affiliation: str) -> int:
            """Update all articles matching the exact author string."""
            conn.execute(
                "UPDATE articles SET affiliation = ? WHERE author = ? AND (affiliation IS NULL OR affiliation = '')",
                (affiliation, author_str)
            )
            conn.commit()
            return conn.execute(
                "SELECT COUNT(*) FROM articles WHERE author = ? AND affiliation = ?",
                (author_str, affiliation)
            ).fetchone()[0]

        # ── Strategy 1: Parse embedded affiliations ───────────────────
        log.info("Strategy 1: Parsing embedded affiliations from author field...")
        for norm, articles in list(author_groups.items()):
            orig_author = articles[0][1]
            embedded = _parse_embedded_affiliation(orig_author)
            if embedded:
                count = _update_author_articles(orig_author, embedded)
                total_updated += count
                log.info(f"  [embedded] {orig_author[:30]} → {embedded[:40]} ({count} rows)")
                del author_groups[norm]

        # ── Strategy 2: Source-based inference for journalists ────────
        log.info("Strategy 2: Source-based inference...")
        for norm, articles in list(author_groups.items()):
            orig_author = articles[0][1]
            source = articles[0][3]
            affil = _source_based_affiliation(source)
            if affil:
                count = _update_author_articles(orig_author, affil)
                total_updated += count
                log.info(f"  [source] {orig_author[:30]} → {affil[:40]} ({count} rows)")
                del author_groups[norm]

        # ── Strategy 3: Re-fetch HTML for citation meta tags ──────────
        log.info("Strategy 3: Re-fetching article HTML for citation meta tags...")
        for norm, articles in list(author_groups.items()):
            orig_author = articles[0][1]
            first_rid, _, _, _, url = articles[0]
            try:
                proxies = None
                if _needs_proxy(url):
                    proxies = {"http": PROXY, "https": PROXY}
                ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
                resp = requests.get(url, proxies=proxies, timeout=15, headers={"User-Agent": ua})
                if resp.status_code == 200 and "html" in resp.headers.get("content-type", "").lower():
                    soup = BeautifulSoup(resp.text, "lxml")
                    meta_affils = soup.find_all(
                        "meta",
                        attrs={"name": re.compile(r"citation_author_institution|citation_author_affiliation", re.I)}
                    )
                    if meta_affils:
                        affil = "; ".join(m.get("content", "") for m in meta_affils if m.get("content"))
                        if affil:
                            count = _update_author_articles(orig_author, affil)
                            total_updated += count
                            log.info(f"  [refetch] {orig_author[:30]} → {affil[:40]} ({count} rows)")
                            del author_groups[norm]
            except Exception:
                continue

        # ── Strategy 4: Web search via DuckDuckGo ─────────────────────
        log.info("Strategy 4: Web search for remaining authors...")
        for norm, articles in list(author_groups.items()):
            orig_author = articles[0][1]
            sample_title = articles[0][2]
            sample_source = articles[0][3]
            try:
                from duckduckgo_search import DDGS
                query = f'"{orig_author.split(";")[0].strip()[:30]}" {sample_source.split("-")[0].strip()[:20]} affiliation'
                with DDGS(proxy="http://127.0.0.1:7890", timeout=10) as ddgs:
                    results = list(ddgs.text(query, max_results=5))
                if results:
                    snippets = "\n".join(
                        f"- {r['body'][:200]}" for r in results if r.get("body")
                    )
                    if snippets:
                        prompt = (
                            f"Based on these search results, identify the institutional affiliation "
                            f"(university, research institute, or company) of this author.\n\n"
                            f"Author: {orig_author}\n"
                            f"Article: {sample_title}\n"
                            f"Source: {sample_source}\n\n"
                            f"Search snippets:\n{snippets}\n\n"
                            f"Rules:\n"
                            f"- Reply with JUST the institution name, nothing else.\n"
                            f"- If the search snippets mention where the author works, extract it.\n"
                            f"- For Chinese co-authors (semicolon-separated), give the first author's institution.\n"
                            f"- If uncertain, reply with 'UNKNOWN'.\n"
                        )
                        try:
                            import anthropic
                            client = anthropic.Anthropic(api_key=config.LLM_API_KEY)
                            resp = client.messages.create(
                                model=config.LLM_MODEL,
                                messages=[{"role": "user", "content": prompt}],
                                max_tokens=60,
                            )
                            answer = "".join(
                                b.text for b in resp.content if hasattr(b, "text")
                            ).strip()
                            if answer and answer.upper() != "UNKNOWN" and len(answer) < 120:
                                count = _update_author_articles(orig_author, answer)
                                total_updated += count
                                log.info(f"  [web+llm] {orig_author[:30]} → {answer[:40]} ({count} rows)")
                                del author_groups[norm]
                        except Exception:
                            pass
            except Exception:
                continue

        # ── Strategy 5: Final LLM inference fallback ──────────────────
        remaining = list(author_groups.items())
        if remaining:
            log.info(f"Strategy 5: LLM inference for {len(remaining)} remaining authors...")
            for idx, (norm, articles) in enumerate(remaining):
                orig_author = articles[0][1]
                sample_title = articles[0][2]
                sample_source = articles[0][3]

                if dry_run:
                    print(f"  [{idx+1}/{len(remaining)}] {orig_author[:30]} ({len(articles)} articles)")
                    continue

                prompt = (
                    f"You are a research librarian. Given the author name and one of their article titles below, "
                    f"determine their institutional affiliation (university, research institute, company, or news organization).\n\n"
                    f"Author: {orig_author}\n"
                    f"Sample article title: {sample_title}\n"
                    f"Source publication: {sample_source}\n\n"
                    f"Rules:\n"
                    f"- For Chinese authors with semicolon-separated names, treat each as co-authors "
                    f"and return the affiliation shared by the first author.\n"
                    f"- For defense journalists, use their known news organization affiliation.\n"
                    f"- For academic authors, use their university or research institute.\n"
                    f"- If you're confident, reply with JUST the institution name, nothing else.\n"
                    f"- If unsure, reply with 'UNKNOWN'.\n"
                    f"- Do NOT make up affiliations."
                )
                try:
                    import anthropic
                    client = anthropic.Anthropic(api_key=config.LLM_API_KEY)
                    resp = client.messages.create(
                        model=config.LLM_MODEL,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=60,
                    )
                    answer = "".join(b.text for b in resp.content if hasattr(b, "text")).strip()
                    if answer and answer.upper() != "UNKNOWN" and len(answer) < 200:
                        count = _update_author_articles(orig_author, answer)
                        total_updated += count
                        log.info(f"  [llm] {orig_author[:30]} → {answer[:40]} ({count} rows)")
                    else:
                        log.info(f"  [llm] {orig_author[:30]} → UNKNOWN (skipped)")
                except Exception as e:
                    log.warning(f"  [llm] {orig_author[:30]} → error: {e}")

        log.info(f"Backfill complete. Total updated: {total_updated}")
    finally:
        conn.close()


def cleanup_snapshots(days=30):
    """Delete snapshot HTML files older than `days` days."""
    archive = config.ARCHIVE_DIR
    if not archive.exists():
        return
    cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
    removed = 0
    for path in archive.iterdir():
        if path.suffix == ".html" and path.stat().st_mtime < cutoff:
            path.unlink()
            removed += 1
    if removed:
        log.info(f"Cleaned {removed} old snapshots from {archive}")


def run(dry_run=False, skip_llm=False):
    """Run the full monitor cycle."""
    t_start = datetime.now(timezone.utc)
    log.info("=" * 60)
    log.info(f"{config.APP_NAME} - Starting poll cycle")
    log.info(f"Keywords: {len(config.ALL_KEYWORDS)} active")
    log.info(f"Sources: {len(config.RSS_SOURCES)} feeds")
    if config.USE_LLM_FILTER and config.LLM_API_KEY:
        log.info(f"LLM filter: enabled ({config.LLM_MODEL})")
    if config.TRANSLATE_TO_CHINESE:
        log.info("Translation: enabled (→中文)")
    log.info("=" * 60)

    conn = init_db()
    try:
        new_articles = poll_once(conn, dry_run=dry_run, skip_llm=skip_llm)
        t_end = datetime.now(timezone.utc)
        duration_sec = int((t_end - t_start).total_seconds())

        log.info(f"Cycle complete. Found {len(new_articles)} new articles in {duration_sec}s.")

        # Save poll stats
        if not dry_run:
            try:
                conn.execute("""CREATE TABLE IF NOT EXISTS poll_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    duration_sec INTEGER NOT NULL,
                    articles_found INTEGER NOT NULL,
                    sources_count INTEGER NOT NULL
                )""")
                conn.execute(
                    "INSERT INTO poll_stats (started_at, duration_sec, articles_found, sources_count) VALUES (?, ?, ?, ?)",
                    (t_start.isoformat(), duration_sec, len(new_articles), len(config.RSS_SOURCES)),
                )
                conn.commit()
            except Exception as e:
                log.debug(f"Failed to save poll stats: {e}")

        if new_articles and not dry_run:
            from notifier import notify_all
            for article in new_articles:
                notify_all(article)

        cleanup_snapshots(days=30)
        return new_articles
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    dry_run = "--dry-run" in sys.argv
    skip_llm = "--skip-llm" in sys.argv
    run(dry_run=dry_run, skip_llm=skip_llm)
