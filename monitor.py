#!/usr/bin/env python3
"""
News Monitor - Core Engine
Fetches, filters, translates, archives, and notifies about news articles.
"""
import difflib
import hashlib
import html
import json
import logging
import os
import re
import sqlite3
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import feedparser
import requests
from bs4 import BeautifulSoup

import config
from googlenewsdecoder import gnewsdecoder

# Domains that require proxy (GFW-blocked from China)
PROXY = os.environ.get("HTTP_PROXY", "http://127.0.0.1:7890")
_PROXY_AVAILABLE = None


def _redact_proxy() -> str:
    """Return proxy URL with credentials redacted for safe logging."""
    from urllib.parse import urlparse
    parsed = urlparse(PROXY)
    if parsed.password:
        return f"{parsed.scheme}://{parsed.username}:****@{parsed.hostname}:{parsed.port}"
    return PROXY


def _check_proxy() -> bool:
    """Check if proxy is reachable via TCP connect (not HTTP GET — proxies
    reject plain GET to the proxy port with 400)."""
    global _PROXY_AVAILABLE
    if _PROXY_AVAILABLE is not None:
        return _PROXY_AVAILABLE
    try:
        from urllib.parse import urlparse
        import socket
        parsed = urlparse(PROXY)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 7890
        sock = socket.create_connection((host, port), timeout=3)
        sock.close()
        _PROXY_AVAILABLE = True
    except Exception:
        _PROXY_AVAILABLE = False
        log.warning(f"Proxy {_redact_proxy()} unreachable — remote RSS sources will be skipped")
    return _PROXY_AVAILABLE

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
    # Sites commonly blocked from China — add proactively
    "indiatimes.com",
    "timesofindia.com",
    "defensenews.com",
    "nationalinterest.org",
    "twz.com", "thewarzone.com",
    "military.com",
    "stripes.com",
    "airandspaceforces.com",
    "breakingdefense.com",
    "19fortyfive.com",
    "atlanticcouncil.org",
    "businessinsider.com",
    "eurasiantimes.com",
    "thediplomat.com",
    "warontherocks.com",
    "l3harris.com",
    "rtx.com",
    "orbitaltoday.com",
    "aerospacemanufacturinganddesign.com",
    "shephardmedia.com",
    "sandboxx.us",
    "zona-militar.com",
    "janes.com",
    "defenceconnect.com.au",
    # News aggregators and financial news
    "marketscreener.com",
    "finance.yahoo.com",
    "yahoo.com",
    "defence-industry.eu",
    "defence-industry-europe.com",
    "defenceindustryeu.com",
    "spacewar.com",
    "militaryleak.com",
    "navalnews.com",
    "armyrecognition.com",
    "european-defence.com",
    "euro-sd.com",
    "edrmagazine.eu",
    "asianmilitaryreview.com",
    "asiapacificdefencereporter.com",
    "defenceconnect.com",
    "ukdefencejournal.org.uk",
    "defenceview.in",
    "thedefensepost.com",
    "defensebrief.com",
    "aerospacetestinginternational.com",
    "spaceref.com",
    "spaceflightnow.com",
    "nasaspaceflight.com",
    "space.com",
    "aerospacemanufacturinganddesign.com",
    "aviationweek.com",
    "flightglobal.com",
    "ainonline.com",
    "janes.com",
    "shephardmedia.com",
    "twz.com", "thewarzone.com",
    "defensenews.com", "breakingdefense.com",
}


def _needs_proxy(url: str) -> bool:
    from urllib.parse import urlparse
    if not _check_proxy():
        return False
    host = urlparse(url).hostname or ""
    return any(host == d or host.endswith("." + d) for d in NEEDS_PROXY_DOMAINS)


def _validate_url(url: str) -> bool:
    """SSRF guard: only allow http/https, block private/internal IPs and internal DNS."""
    from urllib.parse import urlparse
    import ipaddress
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = (parsed.hostname or "").lower().strip()

        # Block by exact internal hostnames
        _blocked_hosts = {
            "localhost", "127.0.0.1", "0.0.0.0", "::1",
            "255.255.255.255", "fe80::1",
            "[::1]", "[::]", "127.1",
        }
        if host in _blocked_hosts:
            return False

        # Block by DNS suffix
        if host.endswith(".local") or host.endswith(".internal"):
            return False
        if host.endswith(".localhost") or host.endswith(".lan"):
            return False

        # Block internal IP ranges
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
                return False
            # 198.18.0.0/15 is used for benchmarking, also block
            if isinstance(ip, ipaddress.IPv4Address) and 0xc6120000 <= int(ip) < 0xc6140000:
                return False
        except ValueError:
            pass  # host is a DNS name, not an IP — OK

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

# Timezone abbreviations that %Z can't reliably parse; map to correct offsets
_TZ_MAP = {
    "EDT": "-0400", "EST": "-0500",
    "PDT": "-0700", "PST": "-0800",
    "MST": "-0700",
    "GMT": "+0000", "UTC": "+0000", "WET": "+0000",
    "BST": "+0100", "WEST": "+0100", "CEST": "+0200",
    "CET": "+0100", "EET": "+0200", "EEST": "+0300",
}
_TZ_RE = re.compile(r"\s+(" + "|".join(_TZ_MAP) + r")\b")
try:
    _START_DT = datetime.strptime(config.COLLECT_START_DATE, "%Y-%m-%d").replace(tzinfo=timezone.utc)
except (ValueError, TypeError):
    log.warning("Invalid COLLECT_START_DATE=%r, falling back to 2024-01-01", config.COLLECT_START_DATE)
    _START_DT = datetime(2024, 1, 1, tzinfo=timezone.utc)

# ── Google News URL decoder ────────────────────────────────────────────

_GNEWS_CACHE: dict[str, str] = {}  # Google News URL -> real URL
_GNEWS_LOCK = threading.Lock()


def decode_google_news_url(url: str) -> str:
    """Decode Google News redirect URL to real article URL using googlenewsdecoder.

    Returns the decoded URL on success, or the original URL on failure.
    Results are cached in-memory to avoid repeated network calls.
    """
    if "news.google.com" not in url or "/articles/" not in url:
        return url
    with _GNEWS_LOCK:
        cached = _GNEWS_CACHE.get(url)
        if cached:
            return cached
    try:
        proxy = PROXY if _needs_proxy(url) else None
        result = gnewsdecoder(url, interval=0, proxy=proxy)
        if result and result.get("status") and result.get("decoded_url"):
            decoded = result["decoded_url"]
            with _GNEWS_LOCK:
                _GNEWS_CACHE[url] = decoded
            log.info(f"Decoded Google News URL: {decoded[:80]}...")
            return decoded
    except Exception as e:
        log.debug(f"Google News decode failed: {e}")
    return url


def _decode_google_news_batch(urls: list[str], delay=0.5) -> dict[str, str]:
    """Decode multiple Google News URLs with random delays between requests."""
    import random
    import time
    result = {}
    for url in urls:
        decoded = decode_google_news_url(url)
        if decoded != url:
            result[url] = decoded
        time.sleep(random.uniform(delay * 0.5, delay * 1.5))
    return result


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
    text = _TZ_RE.sub(lambda m: " " + _TZ_MAP[m.group(1)], text)
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
        return date_str[:19].replace("T", " ") if date_str else ""
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

    # ── Patent sources ────────────────────────────────────────────────
    patent_markers = [
        "fpo patents", "freepatentsonline",
        "free patents online",
        "google patents", "patentsview",
        "uspto patent",
    ]
    for m in patent_markers:
        if m in src_lower:
            return "patent"

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

    from schema import (
        ARTICLES_TABLE_DDL, ARTICLES_INDEXES, EXTRA_COLUMNS,
        METADATA_TABLE_DDLS, FTS5_DDL, FTS_TRIGGER_DDLS,
    )

    conn.execute(ARTICLES_TABLE_DDL)
    for ddl in METADATA_TABLE_DDLS:
        try:
            conn.execute(ddl)
        except Exception:
            pass
    conn.commit()
    for idx_ddl in ARTICLES_INDEXES:
        conn.execute(idx_ddl)

    # column add migration
    for col_name, col_type in EXTRA_COLUMNS:
        try:
            conn.execute(f"SELECT {col_name} FROM articles LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute(f"ALTER TABLE articles ADD COLUMN {col_name} {col_type}")
    conn.commit()

    # One-shot migration: normalize existing dates for correct sorting
    try:
        rows = conn.execute("SELECT id, published FROM articles").fetchall()
        changed = 0
        for rid, rpub in rows:
            normalized = _normalize_date(rpub)
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
        pass

    for ddl in METADATA_TABLE_DDLS:
        try:
            conn.execute(ddl)
        except sqlite3.OperationalError:
            pass
    conn.commit()

    # FTS5 full-text search
    try:
        conn.execute(FTS5_DDL)

        # Migration: check if FTS table is missing author/affiliation columns
        # (FTS5 virtual tables don't support ALTER TABLE, so drop+recreate + manual repopulate)
        _fts_cols = [d[1] for d in conn.execute("PRAGMA table_info(articles_fts)").fetchall()]
        _needs_rebuild = "author" not in _fts_cols or "affiliation" not in _fts_cols

        for trigger_ddl in FTS_TRIGGER_DDLS:
            conn.execute(trigger_ddl)

        existing = conn.execute("SELECT COUNT(*) FROM articles_fts").fetchone()[0]
        total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        if _needs_rebuild or existing < total:
            for _t in ["articles_au", "articles_ai", "articles_ad"]:
                try:
                    conn.execute(f"DROP TRIGGER IF EXISTS {_t}")
                except Exception:
                    pass
            conn.execute("DROP TABLE IF EXISTS articles_fts")
            conn.execute(FTS5_DDL)
            # Manual INSERT (rebuild via INSERT INTO ... VALUES('rebuild') doesn't
            # correctly index external content tables with newly added columns)
            conn.execute("""
                INSERT INTO articles_fts(rowid, title, summary, content,
                    translated_title, translated_summary, translated_content,
                    author, affiliation)
                SELECT rowid, title, summary, content,
                    translated_title, translated_summary, translated_content,
                    author, affiliation
                FROM articles
            """)
            for trigger_ddl in FTS_TRIGGER_DDLS:
                conn.execute(trigger_ddl)
            log.info(f"FTS5: rebuilt with author/affiliation ({total} rows)")
    except Exception as e:
        log.warning(f"FTS5 not available, falling back to LIKE search: {e}")

    return conn


def article_exists(conn: sqlite3.Connection, article_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM articles WHERE id = ?", (article_id,)
    ).fetchone() is not None


def clean_content(text: str) -> str:
    """Clean article content: remove encoding artifacts, normalize punctuation,
    apply Chinese standard formatting (first-line indent 2 chars per paragraph)."""
    if not text:
        return ""

    # 1. Remove control characters (keep \n, \r, \t)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
    # Remove C1 control characters (U+0080-U+009F, encoding artifacts)
    text = re.sub(r'[\x80-\x9f]', '', text)
    # Remove BOM and zero-width chars
    text = re.sub(r'[﻿​‌‍⁠⁡⁢⁣⁤]', '', text)
    # Remove U+00AD (soft hyphen)
    text = re.sub(r'\xad', '', text)
    # U+00A0 non-breaking space → regular space
    text = text.replace('\xa0', ' ')

    # 2. Normalize Unicode: decompose ligatures (ﬁ→fi, ﬂ→fl, ﬀ→ff, ﬃ→ffi)
    import unicodedata
    text = unicodedata.normalize('NFKD', text)

    # 3. Remove non-CJK non-ASCII characters that are encoding garbage:
    #    Keep: CJK (U+4E00-U+9FFF), ASCII (U+0020-U+007E),
    #          CJK punctuation (U+3000-U+303F), fullwidth (U+FF00-U+FFEF),
    #          common symbols: ° ± × ÷ → ← ↑ ↓ ⇒ ⇔ ∈ ∉ ∪ ∩ ⊆ ⊇ ≥ ≤ ∑ ∫ √ ∞
    #    Remove: Tamil, Telugu, Syriac, Odia, mathematical alphanumerics, etc.
    def _is_keep_char(c):
        cp = ord(c)
        if cp < 0x80:
            return True  # ASCII
        if 0x4E00 <= cp <= 0x9FFF:
            return True  # CJK
        if 0x3000 <= cp <= 0x303F:
            return True  # CJK punctuation
        if 0xFF00 <= cp <= 0xFFEF:
            return True  # Fullwidth forms
        if cp in (0x00B0, 0x00B1, 0x00D7, 0x00F7):  # ° ± × ÷
            return True
        if 0x2000 <= cp <= 0x206F:
            return True  # General punctuation (smart quotes, dashes, etc.)
        if 0x2100 <= cp <= 0x214F:
            return True  # Letterlike symbols
        if 0x2190 <= cp <= 0x21FF:
            return True  # Arrows
        if 0x2200 <= cp <= 0x22FF:
            return True  # Mathematical operators
        if 0x0391 <= cp <= 0x03C9:
            return True  # Greek (α, β, γ, etc.)
        if 0x0400 <= cp <= 0x04FF:
            return True  # Cyrillic
        return False
    text = ''.join(c for c in text if _is_keep_char(c))

    # 4. Normalize smart quotes and dashes to ASCII-friendly forms
    #    (keep — for Chinese text, but normalize '' to ASCII)
    text = text.replace('‘', "'").replace('’', "'")
    text = text.replace('“', '"').replace('”', '"')
    text = text.replace('–', '-')  # en-dash → hyphen
    # — (em-dash) is legitimate in Chinese, keep it
    text = text.replace('…', '…')  # ellipsis, keep one form

    # 5. Collapse multiple spaces/tabs into single space
    text = re.sub(r'[ \t]+', ' ', text)

    # 6. Remove intra-line spaces between CJK characters (PDF extraction artifacts).
    #    PDF-to-text conversion often inserts spaces between CJK glyphs that should
    #    be adjacent (e.g. "海 上" → "海上", "巡 航" → "巡航").
    text = re.sub(r'(?<=[一-鿿㐀-䶿]) (?=[一-鿿㐀-䶿])', '', text)
    text = re.sub(r'(?<=[一-鿿㐀-䶿]) (?=[，。；：、？！…—～）】〕》》）」])', '', text)
    text = re.sub(r'(?<=[，。；：、？！…—～（【《〔]) (?=[一-鿿㐀-䶿])', '', text)

    # 7. Clean up blank lines: remove lines with only whitespace,
    #    collapse 3+ consecutive newlines to 2
    text = re.sub(r'\n\s*\n', '\n\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)

    # 8. Remove leading/trailing whitespace per line, but keep paragraph breaks
    lines = text.split('\n')
    lines = [l.strip() for l in lines]
    text = '\n'.join(lines)

    # 9. Chinese formatting: first-line indent 2 chars for each paragraph
    #    Only indent paragraphs that contain CJK characters (Chinese text)
    def _indent_paragraph(p):
        p = p.strip()
        if not p:
            return p
        # Check if paragraph contains CJK
        if re.search(r'[一-鿿]', p):
            return '　　' + p
        return p

    # Split into paragraphs (separated by blank lines)
    paragraphs = re.split(r'(\n\n)', text)
    for i in range(0, len(paragraphs), 2):
        paragraphs[i] = _indent_paragraph(paragraphs[i])
    text = ''.join(paragraphs)

    return text.strip()


def _translate_content_auto(content: str, title: str = "") -> str:
    """Translate non-Chinese content to Chinese. Returns empty string if not needed."""
    if not content:
        return ""
    from translator import is_predominantly_chinese, translate_content
    if not is_predominantly_chinese(content):
        try:
            translated = translate_content(content[:6000])
            if translated:
                return translated
        except Exception:
            pass
    return ""


def update_article_content(conn: sqlite3.Connection, article_id: str, content: str, title: str = "",
                           images: list[str] | None = None) -> None:
    """Update article content, clean formatting, auto-translate if non-Chinese."""
    content = clean_content(content)
    translated = _translate_content_auto(content, title)
    images_json = json.dumps(images) if images else ""
    conn.execute(
        "UPDATE articles SET content = ?, translated_content = ?, content_images = ? WHERE id = ?",
        (content[:50000], translated, images_json, article_id)
    )
    conn.commit()
    if translated:
        log.info(f"Content translated for {title[:50]}")


def save_article(conn: sqlite3.Connection, article: dict) -> bool:
    """Save article to database. Returns True if new (inserted, not ignored).

    Auto-translates non-Chinese content on save.
    """
    # Auto-translate non-Chinese content
    content = article.get("content", "")[:50000]
    content = clean_content(content)
    article["content"] = content
    if content and not article.get("translated_content"):
        translated = _translate_content_auto(content, article.get("title", ""))
        if translated:
            article["translated_content"] = translated

    published = _normalize_date(article.get("published", ""))
    try:
        before = conn.total_changes
        conn.execute("""
            INSERT OR IGNORE INTO articles
                (id, title, url, source, published, fetched_at, summary,
                 matched_kw, relevance, translated_title, translated_summary, is_translated,
                 author, affiliation, event_group, event_title, translated_content, image_url,
                 content, article_type, content_images)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            article.get("content_images", ""),
        ))
        return conn.total_changes > before
    except Exception as e:
        log.error(f"DB save error: {e}")
        return False


def get_articles(conn: sqlite3.Connection, limit=50, offset=0, type_filter="", kw_filter=None, time_filter=""):
    query = "SELECT * FROM articles WHERE 1=1"
    params: list = []
    if type_filter in ("paper", "news", "patent"):
        query += " AND article_type = ?"
        params.append(type_filter)
    if kw_filter:
        conds = " OR ".join(["matched_kw LIKE ?" for _ in kw_filter])
        query += f" AND ({conds})"
        params.extend([f"%{kw}%" for kw in kw_filter])
    if time_filter == "24h":
        query += " AND replace(substr(fetched_at, 1, 19), 'T', ' ') > datetime('now', '-1 day')"
    query += " ORDER BY published DESC, relevance DESC LIMIT ? OFFSET ?"
    return conn.execute(query, (*params, limit, offset)).fetchall()


def get_keyword_trend(conn, keyword, days=30):
    """Return daily article count for a keyword over last N days."""
    rows = conn.execute(
        "SELECT DATE(published) as day, COUNT(*) as cnt FROM articles "
        "WHERE published >= datetime('now', ? || ' days') "
        "AND matched_kw LIKE ? GROUP BY day ORDER BY day",
        (f"-{days}", f"%{keyword}%"),
    ).fetchall()
    return [{"day": r[0], "cnt": r[1]} for r in rows]


def get_top_keywords(conn, days=30, limit=5):
    """Return most frequently occurring keywords over last N days."""
    rows = conn.execute(
        "SELECT matched_kw FROM articles "
        "WHERE published >= datetime('now', ? || ' days') "
        "AND matched_kw != ''",
        (f"-{days}",),
    ).fetchall()
    counter = Counter()
    for (kw_str,) in rows:
        for kw in kw_str.split(", "):
            kw = kw.strip()
            if kw:
                counter[kw] += 1
    return counter.most_common(limit)


def search_articles(conn: sqlite3.Connection, keyword: str, limit=50, offset=0):
    """FTS5 full-text search with LIKE fallback. Returns (rows, total_count)."""
    has_cjk = bool(re.search(r"[一-鿿㐀-䶿]", keyword))
    if not has_cjk:
        # Sanitize for FTS5: strip special operators that break quoted match
        safe = re.sub(r'[+\-*()~^]', '', keyword)
        safe = safe.replace('"', '""').replace("'", "''")
        safe = safe.replace(" AND ", " ").replace(" OR ", " ").replace(" NOT ", " ")
        safe = safe.strip()
        if not safe:
            safe = keyword.replace('"', '""')
        try:
            rows = conn.execute(
                "SELECT a.* FROM articles a "
                "JOIN articles_fts fts ON a.rowid = fts.rowid "
                "WHERE articles_fts MATCH ? "
                "ORDER BY rank LIMIT ? OFFSET ?",
                (f'"{safe}"', limit, offset),
            ).fetchall()
            total = conn.execute(
                "SELECT COUNT(*) FROM articles_fts WHERE articles_fts MATCH ?",
                (f'"{safe}"',),
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
        "OR author LIKE ? OR affiliation LIKE ? "
        "ORDER BY published DESC, relevance DESC LIMIT ? OFFSET ?",
        (f"%{keyword}%",) * 8 + (limit, offset),
    ).fetchall()
    total = conn.execute(
        "SELECT COUNT(*) FROM articles WHERE title LIKE ? OR summary LIKE ? "
        "OR content LIKE ? OR translated_title LIKE ? "
        "OR translated_summary LIKE ? OR translated_content LIKE ? "
        "OR author LIKE ? OR affiliation LIKE ?",
        (f"%{keyword}%",) * 8,
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
                          limit=50, offset=0,
                          type_filter="", kw_filter=None):
    """Get articles for a specific year-month (format: '2025-03').
    Uses range query on published to leverage the published index.
    """
    # Convert "2025-03" to "2025-03-01" / "2025-04-01" range
    try:
        parts = year_month.split("-")
        start_date = f"{parts[0]}-{parts[1]}-01"
        y, m = int(parts[0]), int(parts[1])
        if m == 12:
            end_date = f"{y + 1}-01-01"
        else:
            end_date = f"{y:04d}-{m + 1:02d}-01"
    except (IndexError, ValueError):
        start_date = year_month
        end_date = "9999-12-31"

    query = "SELECT * FROM articles WHERE published >= ? AND published < ?"
    params: list = [start_date, end_date]
    if type_filter in ("paper", "news", "patent"):
        query += " AND article_type = ?"
        params.append(type_filter)
    if kw_filter:
        conds = " OR ".join(["matched_kw LIKE ?" for _ in kw_filter])
        query += f" AND ({conds})"
        params.extend([f"%{kw}%" for kw in kw_filter])
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


def _normalize_url(url: str) -> str:
    """Normalize URL for dedup: strip tracking params, trailing slashes, protocol."""
    from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
    try:
        parsed = urlparse(url)
        # Strip common tracking parameters
        track_params = {"utm_source", "utm_medium", "utm_campaign", "utm_term",
                        "utm_content", "fbclid", "gclid", "ref", "source",
                        "mc_cid", "mc_eid", "pk_source", "pk_medium", "pk_campaign"}
        qs = parse_qs(parsed.query, keep_blank_values=True)
        clean_qs = {k: v for k, v in qs.items() if k not in track_params}
        clean_query = urlencode(clean_qs, doseq=True) if clean_qs else ""
        cleaned = parsed._replace(query=clean_query)
        result = urlunparse(cleaned)
        # Strip trailing slash
        if result.endswith("/"):
            result = result[:-1]
        return result.lower()
    except Exception:
        return url.lower().rstrip("/")


def _normalize_title(title: str) -> str:
    """Normalize title for similarity comparison."""
    t = title.lower().strip()
    t = t.rstrip(".。!！?？,:：;；·\"'”’")
    for prefix in [
        "breaking: ", "breaking news: ", "update: ", "updated: ",
        "新闻：", "快讯：", "最新：", "重磅：", "独家：", "首发：",
        "exclusive: ", "just in: ", "developing: ",
        "watch: ", "video: ", "photos: ",
    ]:
        if t.startswith(prefix):
            t = t[len(prefix):]
            break
    t = re.sub(r'\s+', ' ', t)
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
                               limit=50, offset=0,
                               type_filter="", kw_filter=None, time_filter=""):
    """Return articles ordered by event_group (grouped together, most recent first).

    Returns list of (row, is_group_start) tuples where is_group_start is True
    when a new event group begins.
    """
    query = "SELECT * FROM articles WHERE 1=1"
    params: list = []
    if type_filter in ("paper", "news", "patent"):
        query += " AND article_type = ?"
        params.append(type_filter)
    if kw_filter:
        conds = " OR ".join(["matched_kw LIKE ?" for _ in kw_filter])
        query += f" AND ({conds})"
        params.extend([f"%{kw}%" for kw in kw_filter])
    if time_filter == "24h":
        query += " AND replace(substr(fetched_at, 1, 19), 'T', ' ') > datetime('now', '-1 day')"
    query += " ORDER BY published DESC, relevance DESC LIMIT ? OFFSET ?"
    rows = conn.execute(query, (*params, limit, offset)).fetchall()

    result = []
    last_group = None
    for row in rows:
        eg = row['event_group']
        is_start = (eg != "" and eg != last_group)
        result.append((row, is_start))
        if eg:
            last_group = eg
    return result


# ── RSS Fetching ──────────────────────────────────────────────────────────


def _fetch_rss_relaxed(url: str, timeout=30) -> Optional[requests.Response]:
    """Retry RSS fetch with relaxed SSL settings (for older servers)."""
    try:
        ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        # Try with SSL verification first
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": ua},
                            verify=True)
        resp.raise_for_status()
        return resp
    except Exception:
        pass
    # Fallback: disable SSL verification (some RSS servers have expired certs)
    try:
        ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": ua},
                            verify=False)
        resp.raise_for_status()
        return resp
    except Exception:
        return None


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
    except Exception as first_err:
        # Retry with relaxed SSL for servers with older TLS
        relaxed = _fetch_rss_relaxed(url, timeout=timeout)
        if relaxed is not None:
            resp = relaxed
        else:
            log.error(f"RSS fetch error for {url}: {first_err}")
            return entries

    try:
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
            # Decode Google News redirect URLs on arrival
            if "news.google.com" in e["url"]:
                e["url"] = decode_google_news_url(e["url"])
            if e["summary"]:
                e["summary"] = BeautifulSoup(e["summary"], "lxml").get_text(
                    separator=" ", strip=True
                )[:2000]
            entries.append(e)
        log.info(f"Fetched {len(entries)} entries from RSS: {url[:60]}...")
    except Exception as e:
        log.error(f"RSS parse error for {url}: {e}")
    return entries


# ── Full Article Content ──────────────────────────────────────────────────


def _is_anti_bot_page(html: str) -> bool:
    """Detect if the page is an anti-bot / CAPTCHA challenge."""
    keywords = [
        "captcha", "安全验证", "verify", "bot check",
        "just a moment", "enable javascript", "请开启javascript",
        "cf-challenge", "challenge-platform", "checking your browser",
    ]
    text_lower = BeautifulSoup(html, "lxml").get_text(separator=" ", strip=True)[:300].lower()
    return any(kw in text_lower for kw in keywords)


def _extract_with_css_selector(soup, css_selector: str, remove_selectors: list[str] = None) -> str:
    """Extract content by CSS selector. Returns text or empty string."""
    try:
        if remove_selectors:
            for sel in remove_selectors:
                for el in soup.select(sel):
                    el.decompose()
        el = soup.select_one(css_selector)
        if el:
            text = el.get_text(separator="\n", strip=True)
            return clean_content(text)
    except Exception:
        pass
    return ""


_SELECTORS_LOCK = threading.Lock()


def load_source_selectors() -> dict[str, dict]:
    """Load per-source CSS selectors from JSON file."""
    import json
    path = config.SOURCE_SELECTORS_PATH
    try:
        with _SELECTORS_LOCK:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning(f"Failed to load source selectors: {e}")
    return {}


def save_source_selectors(selectors: dict[str, dict]):
    """Save per-source CSS selectors to JSON file."""
    import json
    path = config.SOURCE_SELECTORS_PATH
    try:
        with _SELECTORS_LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(selectors, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        log.warning(f"Failed to save source selectors: {e}")


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
    # Defense Daily / sidebar sections — common in Readability extractions
    r"^(force multiplier|defense watch|congress updates|job feed)\b",
    r"^(trending|popular|most read|latest news)\s*$",
    r"^post a (job|resume)\b",
    r"^\d{1,2}\s*(min|hour|day|week|month)s?\s+(ago|read)",
    r"^(software|senior|principal|lead|staff)\s+\w+\s+(engineer|analyst|scientist|manager|developer|administrator)",
]


def _clean_extracted_text(text: str) -> str:
    """Remove junk lines from extracted article text."""
    if not text:
        return ""

    # ── Pre-processing: truncate at paywall/subscriber-only markers ──
    paywall_markers = [
        "subscriber-only content", "subscriber only content",
        "please log in below", "log in to read more",
        "subscribe to read more", "already a subscriber",
        "this is a subscriber-only", "sign in to your account",
        "to continue reading",
    ]
    text_lower = text.lower()
    first_paywall = None
    for marker in paywall_markers:
        idx = text_lower.find(marker)
        if idx != -1:
            if first_paywall is None or idx < first_paywall:
                first_paywall = idx
    if first_paywall is not None and first_paywall > 100:
        text = text[:first_paywall].rstrip()

    # ── Remove duplicated content blocks (e.g. PDF page headers) ──
    lines = text.split("\n")
    # Skip repeated 3-line blocks instead of truncating at the first repeat.
    # This handles PDF page headers that repeat on every page while preserving
    # all unique content.
    seen_blocks: set[str] = set()
    dedup_lines = []
    i = 0
    while i < len(lines):
        block_key = "\n".join(lines[i:i+3]) if i + 3 <= len(lines) else ""
        if block_key and len(block_key) > 30:
            if block_key in seen_blocks:
                i += 3  # skip repeated block (likely a page header)
                continue
            seen_blocks.add(block_key)
        dedup_lines.append(lines[i])
        i += 1
    lines = dedup_lines

    # ── Line-by-line filtering ──
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


def _extract_pdf_text_with_layout(doc) -> str:
    """Extract PDF text with paragraph reconstruction using text position data.

    Uses page.get_text('dict') to obtain per-character bounding boxes, then
    groups spans into visual lines by y-proximity and joins lines into paragraphs
    based on vertical gap size. This preserves paragraph structure lost by basic
    page.get_text() (which only inserts \\n per line).

    Returns plain text with \\n\\n paragraph breaks.
    """
    paragraphs = []
    for page in doc:
        tp = page.get_text("dict")
        # Collect all text blocks (type 0), extract lines with bbox y1
        raw_lines: list[tuple[float, str]] = []
        for block in tp.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans = [s for s in line.get("spans", []) if s.get("text", "").strip()]
                if not spans:
                    continue
                # Sort spans left-to-right
                spans.sort(key=lambda s: s["bbox"][0])
                text = "".join(s["text"] for s in spans)
                # Use average of y0 and y1 as line position
                y = (line["bbox"][1] + line["bbox"][3]) / 2
                raw_lines.append((y, text))

        if not raw_lines:
            continue

        # Sort lines top-to-bottom by y position
        raw_lines.sort(key=lambda x: x[0])

        # Group into paragraphs by vertical gap
        para_lines: list[list[str]] = [[raw_lines[0][1]]]
        for i in range(1, len(raw_lines)):
            prev_y, prev_text = raw_lines[i - 1]
            cur_y, cur_text = raw_lines[i]
            gap = cur_y - prev_y
            prev_height = 0
            # Estimate previous line height from surrounding lines
            if i >= 2:
                prev_height = prev_y - raw_lines[i - 2][0]
            elif i + 1 < len(raw_lines):
                prev_height = raw_lines[i + 1][0] - cur_y
            if prev_height <= 0:
                prev_height = 14  # default ~12pt

            # Large gap → new paragraph
            if gap > prev_height * 1.8:
                para_lines.append([cur_text])
            else:
                para_lines[-1].append(cur_text)

        # Build page output
        for pl in para_lines:
            paragraphs.append("\n".join(pl))

    return "\n\n".join(paragraphs)


def _extract_arxiv_pdf(url: str, timeout=30) -> Optional[str]:
    """Download arXiv PDF and extract text using PyMuPDF.

    Returns extracted text (first 10000 chars), or None on failure.
    """
    pdf_url = _arxiv_abs_to_pdf(url)
    if not pdf_url:
        return None

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    try:
        r = requests.get(pdf_url, headers=headers, timeout=timeout)
        r.raise_for_status()
        import fitz  # PyMuPDF
        doc = fitz.open(stream=r.content, filetype="pdf")
        text = _extract_pdf_text_with_layout(doc)
        doc.close()
        if len(text.strip()) > 500:
            return _clean_extracted_text(text[:10000])
    except Exception as e:
        log.debug(f"arXiv PDF extraction failed for {pdf_url}: {e}")
    return None


def _extract_with_jina(url: str, timeout=30) -> Optional[str]:
    """Extract article content using Jina AI Reader service.

    Calls https://r.jina.ai/<original-url> which returns clean markdown.
    Works well for JS-heavy sites and anti-bot pages.
    """
    jina_url = f"https://r.jina.ai/{url}"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; NewsMonitor/1.0)",
        "Accept": "text/plain",
    }
    try:
        proxies = {"http": PROXY, "https": PROXY}
        r = requests.get(jina_url, headers=headers, proxies=proxies, timeout=timeout)
        r.raise_for_status()
        text = r.text.strip()
        if len(text) > 200:
            log.debug(f"Jina AI Reader extracted {len(text)} chars from {url[:60]}")
            return text
    except Exception as e:
        log.debug(f"Jina AI Reader failed for {url[:60]}: {e}")
    return None


def _extract_pdf_generic(url: str, timeout=30) -> Optional[str]:
    """Extract text from any PDF URL using PyMuPDF."""
    import fitz
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    try:
        proxies = None
        if _needs_proxy(url):
            proxies = {"http": PROXY, "https": PROXY}
        r = requests.get(url, headers=headers, proxies=proxies, timeout=timeout)
        r.raise_for_status()
        doc = fitz.open(stream=r.content, filetype="pdf")
        text = _extract_pdf_text_with_layout(doc)
        doc.close()
        cleaned = _clean_extracted_text(text)
        cleaned = clean_content(cleaned)
        if len(cleaned.strip()) > 200:
            log.debug(f"PDF extracted {len(cleaned)} chars from {url[:60]}")
            return cleaned[:30000]
    except Exception as e:
        log.debug(f"PDF extraction failed for {url[:60]}: {e}")
    return None


def _arxiv_abs_to_pdf(url: str) -> Optional[str]:
    """Convert arxiv.org abs URL to PDF download URL."""
    if "arxiv.org" not in url.lower():
        return None
    pdf_url = url.replace("/abs/", "/pdf/")
    if not pdf_url.endswith(".pdf"):
        pdf_url += ".pdf"
    return pdf_url


def _extract_arxiv_image(url: str, timeout=30) -> Optional[bytes]:
    """Download arXiv PDF, render first page as PNG.

    Returns PNG bytes, or None on failure.
    """
    pdf_url = _arxiv_abs_to_pdf(url)
    if not pdf_url:
        return None

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    try:
        r = requests.get(pdf_url, headers=headers, timeout=timeout)
        r.raise_for_status()
        import fitz  # PyMuPDF
        doc = fitz.open(stream=r.content, filetype="pdf")
        page = doc[0]
        pix = page.get_pixmap(dpi=150)
        img_bytes = pix.tobytes("png")
        doc.close()
        if len(img_bytes) > 1000:
            return img_bytes
    except Exception as e:
        log.debug(f"arXiv image extraction failed for {pdf_url}: {e}")
    return None


# ── DOI / Unpaywall ──────────────────────────────────────────────────


def _extract_doi_from_url(url: str) -> str | None:
    """Extract DOI from common URL patterns.

    Handles:
      - link.springer.com/article/10.1007/...
      - doi.org/10.1007/...
      - dx.doi.org/10.1007/...
      - ieeexplore.ieee.org/document/... (no standard DOI, skip)
    """
    # DOI pattern: 10.x/x (anything after /10. until end or ?#)
    m = re.search(r"(10\.\d{4,}/[^\"'\s?#]+)", url, re.I)
    if m:
        doi = m.group(1).rstrip(".")
        return doi
    return None


def _extract_doi_from_soup(soup: BeautifulSoup) -> str | None:
    """Extract DOI from HTML meta tags and JSON-LD."""
    # 1. citation_doi meta tag (standard in academic journals)
    for meta in soup.find_all("meta", attrs={"name": re.compile(r"citation_doi", re.I)}):
        content = (meta.get("content") or "").strip()
        if content:
            return content

    # 2. DC.identifier DOI
    for meta in soup.find_all("meta", attrs={"name": re.compile(r"dc\.identifier", re.I)}):
        content = (meta.get("content") or "").strip()
        if content.lower().startswith("doi:"):
            return content[4:].strip()
        if content.startswith("10."):
            return content

    # 3. JSON-LD
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            import json
            data = json.loads(script.string) if script.string else {}
            items = []
            if isinstance(data, list):
                items = data
            elif "@graph" in data:
                items = data["@graph"]
            else:
                items = [data]
            for item in items:
                if isinstance(item, dict):
                    doi = item.get("doi") or ""
                    if doi:
                        return doi
                    sid = item.get("sameAs") or ""
                    if isinstance(sid, str) and "doi.org/" in sid:
                        m = re.search(r"10\.\d{4,}/[^\"'\s?#]+", sid)
                        if m:
                            return m.group(1)
        except Exception:
            continue

    return None


def _fetch_by_doi(doi: str, timeout=30) -> str | None:
    """Fetch full text via Unpaywall API.

    Calls https://api.unpaywall.org/v2/{DOI}?email=...
    If an OA version is found, downloads the PDF and extracts text with PyMuPDF.
    Returns extracted text (first 10000 chars), or None on failure.
    """
    email = config.UNPAYWALL_EMAIL
    if not email:
        log.debug("UNPAYWALL_EMAIL not configured, skipping Unpaywall lookup")
        return None

    try:
        # Step 1: Query Unpaywall API
        api_url = f"https://api.unpaywall.org/v2/{doi}?email={email}"
        log.debug(f"Unpaywall lookup: {doi}")
        r = requests.get(api_url, timeout=timeout)
        if r.status_code == 404:
            log.debug(f"Unpaywall: no record for DOI {doi}")
            return None
        r.raise_for_status()
        data = r.json()

        if not data.get("is_oa"):
            log.debug(f"Unpaywall: DOI {doi} is not open access")
            return None

        # Step 2: Find best OA PDF URL
        best_loc = data.get("best_oa_location") or data.get("oa_locations", [{}])[0]
        if not best_loc:
            return None

        pdf_url = best_loc.get("url_for_pdf")
        if not pdf_url:
            # Fall back to landing page URL — some repositories serve HTML
            landing = best_loc.get("url_for_landing_page")
            if landing and landing.lower().endswith(".pdf"):
                pdf_url = landing

        if not pdf_url:
            log.debug(f"Unpaywall: no PDF URL found for DOI {doi}")
            return None

        # Step 3: Download and extract PDF text
        log.debug(f"Unpaywall: downloading PDF from {pdf_url[:80]}")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        pdf_data = None
        try:
            pdf_r = requests.get(pdf_url, headers=headers, timeout=timeout, allow_redirects=True)
            pdf_r.raise_for_status()
            content_type = pdf_r.headers.get("content-type", "")
            if "pdf" in content_type.lower() or pdf_r.url.lower().endswith(".pdf"):
                pdf_data = pdf_r.content
        except Exception:
            pass

        # Retry with cloudscraper if direct download failed (bypasses Cloudflare/Akamai)
        if not pdf_data:
            try:
                import cloudscraper
                scraper = cloudscraper.create_scraper(
                    interpreter="nodejs",
                    browser={"browser": "chrome", "platform": "windows", "desktop": True},
                )
                cs_r = scraper.get(pdf_url, timeout=timeout, allow_redirects=True)
                cs_r.raise_for_status()
                if "pdf" in cs_r.headers.get("content-type", "").lower() or cs_r.url.lower().endswith(".pdf"):
                    pdf_data = cs_r.content
            except Exception:
                pass

        if not pdf_data:
            log.debug(f"Unpaywall: failed to download PDF for DOI {doi}")
            return None

        import fitz
        doc = fitz.open(stream=pdf_r.content, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        doc.close()

        cleaned = _clean_extracted_text(text)
        if len(cleaned.strip()) > 200:
            log.info(f"Unpaywall: extracted {len(cleaned)} chars from DOI {doi}")
            return cleaned[:10000]

    except Exception as e:
        log.debug(f"Unpaywall fetch failed for DOI {doi}: {e}")

    return None


def _extract_academic_meta(soup: BeautifulSoup) -> str:
    """Extract abstract from academic meta tags, JSON-LD, and common HTML patterns.

    Tries, in order:
      1. <meta name="citation_abstract" content="...">
      2. <meta name="dc.description" / dcterms.abstract / description>
      3. <meta property="og:description" / twitter:description>
      4. JSON-LD @type ScholarlyArticle / Article description
      5. <div class="abstract" / <section class="abstract"> / itemprop="abstract"
      6. <blockquote class="abstract"> (arXiv-style abstract blocks)
      7. Publisher-specific heuristics (ScienceDirect, Taylor & Francis, etc.)
    """
    # 1. Standard citation_abstract meta tag
    for meta in soup.find_all("meta", attrs={"name": re.compile(r"citation_abstract", re.I)}):
        content = (meta.get("content") or "").strip()
        if len(content) > 100:
            return content

    # 2. Dublin Core & standard meta description
    for meta in soup.find_all("meta", attrs={"name": re.compile(r"dc\.description|dcterms\.abstract|description", re.I)}):
        content = (meta.get("content") or "").strip()
        if len(content) > 200:
            return content

    # 3. OpenGraph / Twitter card descriptions
    for meta in soup.find_all("meta", attrs={"property": re.compile(r"og:description|twitter:description", re.I)}):
        content = (meta.get("content") or "").strip()
        if len(content) > 100:
            return content

    # 4. JSON-LD structured data (ScholarlyArticle, Article, etc.)
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            import json
            data = json.loads(script.string) if script.string else {}
            items = []
            if isinstance(data, list):
                items = data
            elif "@graph" in data:
                items = data["@graph"]
            else:
                items = [data]
            for item in items:
                if isinstance(item, dict):
                    atype = item.get("@type", "")
                    if isinstance(atype, str):
                        atypes = [atype]
                    elif isinstance(atype, list):
                        atypes = atype
                    else:
                        atypes = []
                    if any("ScholarlyArticle" in t or "Article" in t or "Paper" in t for t in atypes):
                        desc = item.get("description") or item.get("abstract") or ""
                        if isinstance(desc, str) and len(desc) > 100:
                            return desc
                        if isinstance(desc, list):
                            desc = " ".join(desc)
                            if len(desc) > 100:
                                return desc
        except Exception:
            continue

    # 5. Common abstract HTML elements (by class, itemprop)
    for selector in [
        {"class": re.compile(r"abstract", re.I)},
        {"itemprop": re.compile(r"(abstract|description)", re.I)},
    ]:
        for el in soup.find_all(["div", "section", "p"], attrs=selector):
            text = el.get_text(separator=" ", strip=True)
            if len(text) > 100:
                return text

    # 6. arXiv-style abstract blockquote
    abstract_el = soup.find("blockquote", class_=re.compile(r"abstract", re.I))
    if abstract_el:
        text = abstract_el.get_text(separator=" ", strip=True)
        if len(text) > 100:
            return text

    # 7. Publisher-specific: ScienceDirect (hidden abstract div in JS payload)
    #    Some publishers store the abstract in a <script> data-* attribute
    for script in soup.find_all("script"):
        src_text = script.string or ""
        m = re.search(r'"abstract"\s*:\s*"([^"]{100,})"', src_text)
        if m:
            text = m.group(1).replace("\\n", " ").replace("\\t", " ")
            if len(text) > 100:
                return text

    return ""


def _extract_publisher_abstract(soup: BeautifulSoup, url: str) -> str:
    """Extract abstract text from known paywalled publisher sites.

    These sites serve abstract content in publisher-specific HTML structures
    even when the full article is behind a paywall.
    """
    domain = url.lower()

    # ScienceDirect: abstract is in a structured div
    if "sciencedirect.com" in domain:
        for el in soup.find_all(["div", "section"], class_=re.compile(r"abstract", re.I)):
            text = el.get_text(separator=" ", strip=True)
            if len(text) > 150:
                return text
        # Also check for data-abstract attribute
        for el in soup.find_all(attrs={"data-abstract": True}):
            text = el.get("data-abstract", "").strip()
            if len(text) > 150:
                return text

    # Taylor & Francis Online
    if "tandfonline.com" in domain:
        for cls in ["hlFld-Abstract", "abstract", "abstractSection"]:
            for el in soup.find_all(class_=re.compile(cls, re.I)):
                text = el.get_text(separator=" ", strip=True)
                if len(text) > 150:
                    return text

    # Springer Link
    if "springer.com" in domain or "springerlink" in domain:
        for el in soup.find_all("section", class_=re.compile(r"Abstract|abstract", re.I)):
            text = el.get_text(separator=" ", strip=True)
            if len(text) > 150:
                return text
        for el in soup.find_all("div", id=re.compile(r"abstract|Abs", re.I)):
            text = el.get_text(separator=" ", strip=True)
            if len(text) > 150:
                return text

    # AIAA/ARC (arc.aiaa.org)
    if "arc.aiaa.org" in domain:
        for el in soup.find_all(["div", "section"], class_=re.compile(r"abstract", re.I)):
            text = el.get_text(separator=" ", strip=True)
            if len(text) > 150:
                return text
        # AIAA often embeds abstract in meta but with extra wrapping
        for el in soup.find_all("div", class_=re.compile(r"abstract|Abstract", re.I)):
            for p in el.find_all("p"):
                text = p.get_text(strip=True)
                if len(text) > 150:
                    return text

    # Cambridge Core
    if "cambridge.org" in domain:
        for el in soup.find_all(["div", "section"], class_=re.compile(r"abstract", re.I)):
            text = el.get_text(separator=" ", strip=True)
            if len(text) > 150:
                return text

    return ""


def _extract_academic_meta_enriched(soup: BeautifulSoup) -> str:
    """Build a richer abstract text by combining all available metadata.

    For paywalled articles, the meta tags often contain:
      - citation_title, citation_author, citation_journal_title
      - citation_volume, citation_issue, citation_year
      - citation_abstract (the actual abstract text)

    Returns a formatted string with metadata header + abstract body,
    or empty string if no substantial abstract found.
    """
    # Collect metadata fields
    title = ""
    author = ""
    journal = ""
    doi = ""
    vol = ""
    year = ""
    abstract = ""

    for meta in soup.find_all("meta"):
        name = (meta.get("name") or "").lower()
        prop = (meta.get("property") or "").lower()
        content = (meta.get("content") or "").strip()
        if not content:
            continue
        if name == "citation_title" or prop == "og:title":
            title = content
        elif name == "citation_author":
            author = (author + "; " + content) if author else content
        elif name == "citation_journal_title":
            journal = content
        elif name == "citation_volume":
            vol = content
        elif name == "citation_publication_date":
            year = content[:4]
        elif name == "citation_doi":
            doi = content
        elif name == "citation_abstract" and len(content) > 100:
            abstract = content

    if not abstract:
        # Try other abstract sources
        abstract = _extract_academic_meta(soup)
        if not abstract or len(abstract) < 100:
            return ""

    # Build header
    parts = []
    if title:
        parts.append(f"标题: {title}")
    if author:
        parts.append(f"作者: {author}")
    if journal:
        jinfo = journal
        if vol:
            jinfo += f", 卷{vol}"
        if year:
            jinfo += f", {year}"
        parts.append(f"期刊: {jinfo}")
    if doi:
        parts.append(f"DOI: {doi}")
    parts.append("")
    parts.append(f"摘要: {abstract}")

    return "\n".join(parts)


# ── CrossRef abstract fallback for paywalled articles ──────────────


def _fetch_abstract_via_crossref(doi: str) -> str | None:
    """Fetch abstract text from CrossRef API for a given DOI.

    CrossRef often indexes abstracts even for paywalled articles.
    Returns formatted text with metadata + abstract, or None.
    """
    import re as _re
    try:
        import requests as _requests
        r = _requests.get(f"https://api.crossref.org/works/{doi}", timeout=15)
        if r.status_code != 200:
            return None
        msg = r.json().get("message", {})
        abstract = msg.get("abstract", "")
        if not abstract:
            return None
        abstract_clean = _re.sub(r"<[^>]+>", "", abstract)
        if len(abstract_clean) < 100:
            return None

        # Build enriched text with metadata
        title = (msg.get("title", [""])[0] or "")
        authors = msg.get("author", [])
        author_str = "; ".join(
            f'{a.get("given","")} {a.get("family","")}' for a in authors[:5]
        )
        journal = (msg.get("container-title", [""])[0] or "")
        year = ""
        for date_field in ("published-print", "published-online", "published"):
            dp = msg.get(date_field, {})
            parts = dp.get("date-parts", [[]])[0]
            if parts and parts[0]:
                year = str(parts[0])
                break

        parts = []
        if title:
            parts.append(f"标题: {title}")
        if author_str:
            parts.append(f"作者: {author_str}")
        if journal:
            jinfo = journal
            if year:
                jinfo += f", {year}"
            parts.append(f"期刊: {jinfo}")
        parts.append(f"DOI: {doi}")
        parts.append("")
        parts.append(f"摘要: {abstract_clean}")

        text = "\n".join(parts)
        log.info(f"CrossRef: got {len(text)} chars for DOI {doi}")
        return text[:30000]

    except Exception as e:
        log.debug(f"CrossRef fetch failed for DOI {doi}: {e}")
        return None


def _clean_google_patent_text(text: str) -> str:
    """Remove metadata noise from Google Patents extracted text.

    Google Patents pages embed publication metadata, classification
    hierarchies, landscape tags, and legal events inside the description
    and claims sections, which pollutes the extracted text. This function
    strips the metadata prefix and legal-events suffix, then filters
    remaining noise lines.
    """
    if not text:
        return text

    lines = text.split("\n")

    # Detect whether the patent's substantive language uses CJK/Korean/Japanese
    # characters, to apply appropriate boundary detection.
    _has_cjk = re.compile(r"[一-鿿㐀-䶿가-힯぀-ゟ゠-ヿ]")

    # ── Phase 1: find content boundaries ──────────────────────────────
    # Before the first substantial CJK/Korean paragraph is all metadata
    # (patent numbers, classifications, landscape tags).
    content_start = 0
    for i, line in enumerate(lines):
        if _has_cjk.search(line):
            content_start = i
            break
        # Fallback: start from the description label
        s = line.strip()
        if s == "Description" or s.startswith("Description "):
            content_start = i + 1
            break

    # Post-claims bibliographic sections — once encountered, everything
    # after is citations / legal status / metadata, never substantive.
    _bib_markers = re.compile(
        r"^(?:"
        r"Priority Applications.*"
        r"|Applications Claiming Priority.*"
        r"|Publications.*"
        r"|Family Applications.*"
        r"|Country Status.*"
        r"|Family$"
        r"|Family Cites Families.*"
        r"|Patent Citations.*"
        r"|Citations.*"
        r"|Also Published As"
        r"|Similar Documents"
        r"|Legal Events"
        r")$"
    )
    content_end = len(lines)
    for i, line in enumerate(lines):
        s = line.strip()
        if _bib_markers.match(s):
            content_end = i
            break

    relevant = lines[content_start:content_end]

    # ── Phase 2: filter noise lines within the content ────────────────
    _noise_line = re.compile(
        r"^(?:"
        r"CN\s*\d+[\.\d]*\s*[A-Z]*"
        r"|CN\s+\d+"
        r"|\d{4}-\d{2}-\d{2}"
        r"|[12]\d{3}"                         # year (2000-2999)
        r"|[A-Z]{2}\d{5,}(?:[A-Z]\d*)?"       # foreign patent numbers
        r"|WO\d{5,}[A-Z]\d*"
        r"|[A-Z]\d{0,4}"
        r"|[a-z-]{1,6}"
        r"|[()—;,.*\-/]{1,5}"
        r"|patent/.*"
        r"|ID=\d+"
        r")$"
    )
    _allcaps_section = re.compile(r"^[A-Z][A-Z &,;/\\\-]{5,}$")

    meta_labels = {
        "Info", "Publication number", "Authority", "Prior art keywords",
        "Prior art date", "Application number", "Other languages",
        "Other versions", "Inventor", "Current Assignee", "Original Assignee",
        "Priority date", "Filing date", "Publication date", "Status",
        "Links", "Espacenet", "Global Dossier", "Discuss", "Classifications",
        "Landscapes", "Active", "Critical", "AREA",
        "Legal Events", "Date", "Code", "Title", "Description", "Abstract",
        "Anticipated expiration", "Publication Number", "Filing Date",
        "Application Number", "Priority Date", "Country", "Link",
        "Assignee", "Also Published As", "Similar Documents",
        "Publication",
    }

    _author_line = re.compile(r"^[A-Z][a-z]+(?:\s+et\s+al\.?)?$")
    _cited_by = re.compile(r"^\*\s+Cited by")
    _pending_or_pub = re.compile(r"^(?:Pending|Publication)$")

    cleaned: list[str] = []
    for line in relevant:
        s = line.strip()
        if not s:
            continue
        if _has_cjk.search(s):
            cleaned.append(line)
            continue
        # Non-CJK noise checks
        if s in meta_labels:
            continue
        if _author_line.match(s):
            continue
        if _cited_by.match(s):
            continue
        if _pending_or_pub.match(s):
            continue
        if (s.startswith("The legal status") or s.startswith("The listed assignees")
                or s.startswith("The priority date") or s.startswith("Publication of")
                or s.startswith("Application filed by") or s.startswith("Priority to")
                or s.startswith("Entry into force") or s == "Patent grant"
                or s.startswith("legal-status")):
            continue
        if _allcaps_section.match(s):
            continue
        if _noise_line.match(s):
            continue
        # Keep English text (claims, equations)
        cleaned.append(line)

    return "\n".join(cleaned)


def _extract_google_patent(soup: BeautifulSoup) -> tuple[str, str, str]:
    """Extract content from a Google Patents page.

    Returns (patent_text, abstract_text, author).
    Google Patents pages have well-structured <section> elements with
    itemprop attributes: abstract, description, claims.
    """
    sections = {}
    for s in soup.find_all("section"):
        itemprop = s.get("itemprop", "")
        if itemprop in ("abstract", "description", "claims"):
            text = s.get_text(separator="\n", strip=True)
            sections[itemprop] = text

    abstract = sections.get("abstract", "")
    description = sections.get("description", "")
    claims = sections.get("claims", "")

    # Build combined patent text, then strip metadata noise
    parts = []
    if description:
        parts.append(description)
    if claims:
        parts.append("Claims:\n" + claims)
    combined = _clean_google_patent_text("\n\n".join(parts))

    # Extract inventor/author from metadata section
    author = ""
    meta_section = soup.find("section", itemprop="metadata")
    if not meta_section:
        meta_section = soup.find("section", itemprop="application")
    if meta_section:
        inventor = meta_section.find("dd", itemprop="inventor")
        if inventor:
            author = inventor.get_text(strip=True)
        if not author:
            assignee = meta_section.find("dd", itemprop="assignee")
            if assignee:
                author = assignee.get_text(strip=True)

    return combined, abstract, author


def _fetch_via_cloudscraper(url: str, timeout=15) -> Optional[dict]:
    """Try fetching via cloudscraper to bypass Cloudflare anti-bot pages."""
    try:
        import cloudscraper
        scraper = cloudscraper.create_scraper(
            interpreter="nodejs",
            browser={"browser": "chrome", "platform": "windows", "desktop": True},
        )
        proxies = None
        if _needs_proxy(url):
            proxies = {"http": PROXY, "https": PROXY}
        r = scraper.get(url, timeout=timeout, proxies=proxies, allow_redirects=True)
        r.raise_for_status()
        if "html" not in r.headers.get("content-type", "").lower():
            return None

        from readability import Document
        doc = Document(r.text)
        text = doc.summary()
        soup = BeautifulSoup(text, "lxml")
        text = soup.get_text(separator="\n", strip=True)
        text = re.sub(r'\n{3,}', '\n\n', text)
        if len(text) >= 200:
            # Also try to extract author/affiliation from original page
            orig_soup = BeautifulSoup(r.text, "lxml")
            author = ""
            affiliation = ""
            meta_authors = orig_soup.find_all("meta", attrs={"name": re.compile(r"author|citation_author", re.I)})
            if meta_authors:
                author = "; ".join(m.get("content", "") for m in meta_authors if m.get("content"))
            return {"text": text[:8000], "author": author, "affiliation": affiliation,
                    "image_url": "", "images": []}
    except Exception as e:
        log.debug(f"Cloudscraper failed for {url[:60]}: {e}")
    return None


def _fetch_from_archive(url: str, timeout=10) -> Optional[dict]:
    """Try to fetch article text from archive.today or Google cache as fallback."""
    text = None

    # 1. Try Google cache first (faster, more likely to have full text)
    cache_url = f"https://webcache.googleusercontent.com/search?q=cache:{url}"
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        r = requests.get(cache_url, headers=headers, timeout=timeout, allow_redirects=True)
        r.raise_for_status()
        if "html" in r.headers.get("content-type", "").lower():
            raw = r.text
            # Google cache wraps content in <pre> or <div id="google-cache-hdr">
            soup = BeautifulSoup(raw, "lxml")
            # Remove the cache header banner
            for div in soup.find_all(id="google-cache-hdr"):
                div.decompose()
            for div in soup.find_all(class_=re.compile(r"cache|header", re.I)):
                div.decompose()
            text = soup.get_text(separator="\n", strip=True)
            text = re.sub(r'\n{3,}', '\n\n', text)
            if len(text) >= 200:
                log.debug(f"Google cache: {len(text)} chars for {url[:60]}")
                return {"text": text[:8000], "author": "", "affiliation": "",
                        "image_url": "", "images": []}
    except Exception:
        pass

    # 2. Try archive.today
    for archive_domain in ("archive.is", "archive.ph", "archive.fo", "archive.vn"):
        archive_url = f"https://{archive_domain}/{url}"
        try:
            r = requests.get(archive_url, headers=headers, timeout=timeout, allow_redirects=True)
            r.raise_for_status()
            if "html" in r.headers.get("content-type", "").lower():
                soup = BeautifulSoup(r.text, "lxml")
                # Remove header/footer/nav elements
                for el in soup.find_all(["header", "footer", "nav"]):
                    el.decompose()
                for el in soup.find_all(class_=re.compile(r"header|footer|nav|menu|toolbar", re.I)):
                    el.decompose()
                text = soup.get_text(separator="\n", strip=True)
                text = re.sub(r'\n{3,}', '\n\n', text)
                if len(text) >= 200:
                    log.debug(f"Archive {archive_domain}: {len(text)} chars for {url[:60]}")
                    return {"text": text[:8000], "author": "", "affiliation": "",
                            "image_url": "", "images": []}
        except Exception:
            continue

    return None


def _proxy_cnki_url(url: str) -> tuple[str, dict]:
    """Rewrite CNKI URL through library proxy if configured.
    Returns (proxied_url, extra_cookies_dict) or (original_url, {}).
    """
    if not config.CNKI_PROXY_TOKEN:
        return url, {}
    for domain in ("kns.cnki.net", "www.cnki.net", "navi.cnki.net"):
        marker = f"https://{domain}"
        if marker in url:
            path = url[len(marker):]
            proxied = f"{config.CNKI_PROXY_BASE}/{config.CNKI_PROXY_TOKEN}{path}"
            if "uniplatform=" not in proxied:
                sep = "&" if "?" in proxied else "?"
                proxied += f"{sep}uniplatform=NZKPT"
            log.debug(f"CNKI proxy: {url[:60]} → {proxied[:80]}...")
            cookies = {}
            if config.CNKI_PROXY_COOKIE:
                cookies["JSESSIONID-UMS-ycfw.library.hb.cn"] = config.CNKI_PROXY_COOKIE
            return proxied, cookies
    return url, {}


def fetch_article_content(url: str, timeout=15, css_selector: str = "",
                          remove_selectors: list[str] = None,
                          strategy: str = "auto") -> Optional[dict]:
    """Fetch full article HTML, extract text using multiple strategies.

    Strategy (per-source override):
      "auto"        — try all methods in order (default)
      "css"         — CSS selector only
      "jina"        — Jina AI Reader only
      "readability" — Readability only

    Extraction order (auto mode):
      0. PDF URL → generic PDF extraction
      1. CSS selector (if provided)
      2. Jina AI Reader
      3. Readability algorithm (Mozilla Reader Mode)
      4. Largest paragraph cluster heuristic
      5. Academic meta tags (citation_abstract, JSON-LD, arXiv blockquote)
      6. arXiv PDF (for arxiv.org URLs only)
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

    # Rewrite CNKI URLs through library proxy if token is configured
    url, extra_cookies = _proxy_cnki_url(url)

    for ua in user_agents:
        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
        }
        try:
            proxies = None
            use_proxy = _needs_proxy(url)
            if use_proxy:
                proxies = {"http": PROXY, "https": PROXY}
            req_kw = {"headers": headers, "proxies": proxies, "timeout": timeout, "allow_redirects": True}
            if extra_cookies:
                req_kw["cookies"] = extra_cookies
            try:
                r = requests.get(url, **req_kw)
            except requests.exceptions.ConnectionError:
                # Direct connection failed — retry with proxy if not already using one
                if not use_proxy and _check_proxy():
                    log.debug(f"Direct failed, retry via proxy: {url[:80]}")
                    proxies = {"http": PROXY, "https": PROXY}
                    r = requests.get(url, headers=headers, proxies=proxies, timeout=timeout, allow_redirects=True)
                else:
                    raise
            try:
                r.raise_for_status()
            except requests.exceptions.HTTPError:
                # HTTP error (e.g. 403) — retry with proxy if not already using one
                if not use_proxy and _check_proxy():
                    log.debug(f"HTTP error {r.status_code}, retry via proxy: {url[:80]}")
                    proxies = {"http": PROXY, "https": PROXY}
                    r = requests.get(url, headers=headers, proxies=proxies, timeout=timeout, allow_redirects=True)
                    r.raise_for_status()
                else:
                    raise
            content_type = r.headers.get("content-type", "")
            if "html" not in content_type.lower():
                continue
            # Fix encoding: some servers (e.g. Google Patents) serve UTF-8
            # content without declaring charset in HTTP headers, and requests
            # defaults to ISO-8859-1 per RFC, producing mojibake for CJK text.
            if r.encoding and r.encoding.lower() in ("iso-8859-1", "latin-1"):
                # Check HTML <meta charset> from raw bytes (more reliable than chardet for CJK)
                meta_charset = re.search(
                    rb'<meta[^>]+charset=["\']?([^"\'>\s/]+)',
                    r.content[:5000], re.I
                )
                if meta_charset:
                    detected = meta_charset.group(1).decode('ascii', errors='ignore').lower()
                    if detected in ('utf-8', 'utf8', 'utf-8'):
                        r.encoding = 'utf-8'
                    elif detected in ('euc-kr', 'cp949', 'korean'):
                        r.encoding = 'cp949'
                    elif detected:
                        r.encoding = detected
                elif r.apparent_encoding:
                    r.encoding = r.apparent_encoding
            raw_html = r.text

            if _is_anti_bot_page(raw_html):
                log.debug(f"Anti-bot page detected for {url}")
                continue

            soup = BeautifulSoup(raw_html, "lxml")
            author = ""
            affiliation = ""
            image_url = ""
            images = []

            # Extract og:image / twitter:image as fallback thumbnail
            og_image_url = None
            for meta_name in ["og:image", "twitter:image", "image"]:
                og_image = (soup.find("meta", attrs={"property": meta_name})
                            or soup.find("meta", attrs={"name": meta_name})
                            or soup.find("meta", attrs={"itemprop": meta_name}))
                if og_image and og_image.get("content"):
                    url_candidate = og_image["content"].strip()
                    if url_candidate:
                        og_path = url_candidate.split("?")[0].lower()
                        if not re.search(r"(logo|avatar|favicon|banner|icon|badge|default|placeholder)", og_path):
                            og_image_url = url_candidate
                            break

            # Always score images from content area for best selection + gallery
            content_areas = soup.find_all(["article", "main", "div", "section"],
                                           class_=re.compile(r"(content|post|article|entry|main|text|body)", re.I))
            if not content_areas:
                content_areas = [soup]
            candidates = []
            for area in content_areas:
                for img in area.find_all("img"):
                    src = img.get("src", "").strip()
                    if not src:
                        src = img.get("data-src", "").strip()
                    if not src:
                        src = img.get("data-lazy-src", "").strip()
                    if not src:
                        src = img.get("data-original", "").strip()
                    if src and not src.startswith(("http://", "https://", "//")):
                        from urllib.parse import urljoin
                        src = urljoin(url, src)
                    elif src.startswith("//"):
                        src = "https:" + src
                    alt = img.get("alt", "") or ""
                    # Skip: empty/relative/data-uri/svg
                    if not src or src.startswith("data:") or src.endswith((".svg", ".gif")):
                        continue
                    # Skip: fake image paths that look like base64 (no extension, long alphanumeric)
                    last_seg = src.rstrip("/").rsplit("/", 1)[-1] if "/" in src else src
                    if "." not in last_seg and len(last_seg) > 40 and re.search(r"[A-Za-z0-9+/=]{40,}", last_seg):
                        continue
                    # Skip: known junk patterns in URL
                    if re.search(r"(logo|avatar|favicon|banner|icon|badge|sprite|shu\.png|Round\.webp|pixel|tracking|spacer|blank|default_pic|signup|subscribe|newsletter|baner|circle-avatar|qrcode|qr_code)", src, re.I):
                        continue
                    if re.search(r"(logo|avatar|favicon|banner|icon|badge)", alt, re.I):
                        continue
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
                    if w_int == 0:
                        mw_url = re.search(r"[/_]w[/_](\d{3,4})([/_]|$)", src)
                        if not mw_url:
                            mw_url = re.search(r"[?&]width[/=](\d{3,4})", src)
                        if mw_url:
                            w_int = int(mw_url.group(1))
                            mh_url = re.search(r"thumbnail[/_](\d+)x(\d+)", src)
                            if mh_url:
                                h_int = int(mh_url.group(2))
                    # Skip: known junk, avatars, too-small, likely ads
                    if re.search(r"(avatar|default_user_pic|default_avatar|gravatar)", src, re.I):
                        continue
                    if w_int < 120 and w_int != 0:
                        continue
                    if h_int < 50 and h_int != 0:
                        continue
                    # Filter common ad dimensions (300x250, 300x600, 336x280, etc.)
                    if h_int > 0 and w_int > 0 and (w_int / h_int) > 3.5:
                        continue  # extremely wide-narrow = likely banner
                    score = w_int if w_int > 0 else 100
                    if h_int > 0 and w_int > h_int:
                        score += 50
                    if len(alt) > 10:
                        score += 30
                    if ".gif" in src:
                        score -= 80
                    score += max(0, 10 - len(candidates))
                    candidates.append((score, src))
            # Deduplicate by URL (keep highest score for each URL)
            if candidates:
                seen = {}
                for score, img_url in candidates:
                    if img_url not in seen or score > seen[img_url][0]:
                        seen[img_url] = (score, img_url)
                candidates = list(seen.values())
                candidates.sort(key=lambda x: -x[0])
                image_url = candidates[0][1]
                images = [img_url for score, img_url in candidates if score >= 80][:9]
                # If og:image exists and isn't already in our list, prepend as thumbnail
                if og_image_url and og_image_url not in images:
                    image_url = og_image_url
            elif og_image_url:
                image_url = og_image_url
                images = [og_image_url]
            else:
                image_url = ""
                images = []

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

            # ── Content extraction ──
            text = ""

            # 0. PDF URL → generic PDF extraction
            if url.lower().endswith(".pdf"):
                pdf_text = _extract_pdf_generic(url)
                if pdf_text:
                    text = pdf_text

            # 1. CSS selector (per-source config)
            if not text and strategy in ("auto", "css") and css_selector:
                selector_text = _extract_with_css_selector(soup, css_selector, remove_selectors)
                if len(selector_text) >= 200:
                    text = selector_text

            # 2. Jina AI Reader
            if not text and strategy in ("auto", "jina"):
                jina_text = _extract_with_jina(url, timeout=timeout)
                if jina_text:
                    text = jina_text

            # 3. Readability
            if not text and strategy in ("auto", "readability"):
                text = _extract_with_readability(raw_html)

            # 4–7. Fallback chain (auto only)
            if strategy == "auto":
                if len(text) < 300:
                    text = _extract_largest_cluster(raw_html)
                if len(text) < 300:
                    text = _extract_academic_meta_enriched(soup)
                if len(text) < 300:
                    text = _extract_publisher_abstract(soup, url)
                if len(text) < 300:
                    doi = _extract_doi_from_url(url) or _extract_doi_from_soup(soup)
                    if doi:
                        text = _fetch_by_doi(doi)
                if len(text) < 300 and doi:
                    crossref_text = _fetch_abstract_via_crossref(doi)
                    if crossref_text:
                        text = crossref_text
                if len(text) < 300 and "arxiv.org" in url.lower():
                    pdf_text = _extract_arxiv_pdf(url)
                    if pdf_text:
                        text = pdf_text

            # Google Patents: override with structured extraction
            if "patents.google.com" in url.lower():
                patent_text, patent_abstract, patent_author = _extract_google_patent(soup)
                if patent_text:
                    # Quality check: detect garbled content. Korean/Chinese/Russian
                    # patents must contain some non-ASCII characters. If the text
                    # is pure ASCII with stunted word fragments (avg len < 2.5),
                    # it's likely JS-rendered content that wasn't captured properly.
                    non_ascii = sum(1 for c in patent_text if ord(c) > 127)
                    non_ascii_ratio = non_ascii / max(len(patent_text), 1)
                    words = patent_text.split()
                    fragments = sum(1 for w in words if len(w) <= 2) if words else 0
                    frag_ratio = fragments / len(words) if words else 1.0
                    # Garbled if ALL of: pure ASCII + high fragment ratio (short
                    # stubs from JS-rendered Korean/Chinese/Japanese text)
                    is_garbled = non_ascii_ratio < 0.01 and frag_ratio > 0.5
                    if is_garbled:
                        log.debug(f"Patent text garbled (non-ascii={non_ascii_ratio:.1%}, frag_ratio={frag_ratio:.1%}), falling back to abstract")
                        if patent_abstract and len(patent_abstract) > 100:
                            text = patent_abstract[:8000]
                    else:
                        text = patent_text[:8000]
                        summary = patent_abstract or text[:500]
                        if patent_author:
                            author = patent_author

            return {
                "text": text[:8000],
                "author": author,
                "affiliation": affiliation,
                "image_url": image_url,
                "images": images,
            }
        except requests.RequestException as e:
            log.debug(f"Content fetch failed for {url} (UA: {ua[:30]}...): {e}")
            continue

    # Fallback 1: cloudscraper — bypasses Cloudflare anti-bot pages
    if strategy == "auto":
        cs_result = _fetch_via_cloudscraper(url, timeout=timeout)
        if cs_result and cs_result.get("text"):
            log.info(f"Cloudscraper OK: {len(cs_result['text'])} chars from {url[:80]}")
            return cs_result

    # Fallback 2: Jina AI Reader (bypasses Cloudflare/Anti-bot via external API)
    if strategy in ("auto", "jina"):
        jina_text = _extract_with_jina(url, timeout=timeout)
        if jina_text:
            jina_images = re.findall(r'!\[.*?\]\((.+?)\)', jina_text)
            jina_images = list(dict.fromkeys(jina_images))
            jina_image_url = jina_images[0] if jina_images else ""
            log.info(f"Jina fallback: extracted {len(jina_text)} chars, {len(jina_images)} images")
            return {
                "text": jina_text[:8000],
                "author": "",
                "affiliation": "",
                "image_url": jina_image_url,
                "images": jina_images[:9],
            }

    # Fallback 3: archive.today / Google cache
    if strategy == "auto":
        archive_result = _fetch_from_archive(url, timeout=timeout)
        if archive_result and archive_result.get("text"):
            log.info(f"Archive fallback OK: {len(archive_result['text'])} chars from {url[:80]}")
            return archive_result

    # Fallback 4: DOI → Unpaywall (for paywalled academic sites)
    if strategy == "auto":
        doi = _extract_doi_from_url(url)
        if not doi:
            log.debug("DOI fallback: no DOI in URL, trying to fetch page first")
            try:
                r = requests.get(url, timeout=timeout,
                                 headers={"User-Agent": "Mozilla/5.0"},
                                 allow_redirects=True)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, "lxml")
                    doi = _extract_doi_from_soup(soup)
            except Exception:
                pass
        if doi:
            log.info(f"DOI fallback: trying Unpaywall for {doi}")
            text = _fetch_by_doi(doi)
            if text:
                return {"text": text[:8000], "author": "", "affiliation": "",
                        "image_url": "", "images": []}
            log.info(f"DOI fallback: Unpaywall failed, trying CrossRef for {doi}")
            text = _fetch_abstract_via_crossref(doi)
            if text:
                return {"text": text[:8000], "author": "", "affiliation": "",
                        "image_url": "", "images": []}

    log.debug(f"All UAs failed for {url}")
    return None


# ── Keyword Filtering ────────────────────────────────────────────────────


def _kw_match(kw_lower: str, text_lower: str) -> bool:
    """Match a single keyword against text.

    Short keywords (<=3 ASCII chars) use regex word-boundary matching
    to avoid false positives like "RDE" matching "border" or "hardened".
    Longer keywords use simple substring matching as before.
    """
    if len(kw_lower) <= 3:
        return bool(re.search(r'\b' + re.escape(kw_lower) + r'\b', text_lower))
    return kw_lower in text_lower


def keyword_match(text: str, keywords: Optional[list[str]] = None) -> list[str]:
    """Check if text matches any keywords. Returns matched keywords.

    Supports AND-keywords: "3D打印&&火箭" matches only when both
    terms appear in the text (separator: &&).

    Short keywords (<=3 ASCII chars) use word-boundary matching to
    prevent false positives from substring matches (e.g. "RDE" won't
    match "border" or "hardened").

    When keywords is None, uses config.ALL_KEYWORDS (the default).
    Pass a custom list to use DB-merged keywords at runtime.
    """
    kw_list = config.ALL_KEYWORDS if keywords is None else keywords
    text_lower = text.lower()
    matched = []
    for kw in kw_list:
        if "&&" in kw:
            parts = [p.strip().lower() for p in kw.split("&&")]
            if all(_kw_match(p, text_lower) for p in parts):
                matched.append(kw)
        else:
            if _kw_match(kw.lower(), text_lower):
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


def llm_filter(article: dict) -> bool:
    """Use LLM to determine if article is relevant. Returns True if relevant."""
    if not config.USE_LLM_FILTER or not config.LLM_API_KEY:
        return True

    prompt = config.LLM_FILTER_PROMPT.format(
        title=article["title"].replace("{", "{{").replace("}", "}}"),
        summary=(article.get("summary", "")[:500]).replace("{", "{{").replace("}", "}}"),
    )

    try:
        from llm_client import create_completion
        answer = create_completion(
            model=config.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
        ).strip().upper()
        log.info(f"LLM filter for '{article['title'][:50]}...': {answer or '(empty — accepting by default)'}")
        if not answer:
            return True  # empty response = API unavailable → accept
        return answer == "YES"
    except Exception as e:
        log.warning(f"LLM filter error (defaulting to accept): {e}")
        return True


# ── Translation ───────────────────────────────────────────────────────────


def translate_article(article: dict) -> dict:
    """Translate article to Chinese. Returns article dict with translation fields."""
    from translator import translate_article as do_translate
    from translator import translate_content as do_translate_content
    from translator import is_predominantly_chinese
    if not config.TRANSLATE_TO_CHINESE:
        return article

    result = do_translate(article["title"], article.get("summary", ""))
    if result:
        article["translated_title"] = result.get("title", article["title"])
        article["translated_summary"] = result.get("summary", article.get("summary", ""))
    # Translate full content if available and not already Chinese
    content = article.get("content", "")
    if content and len(content) > 500 and not is_predominantly_chinese(content):
        translated = do_translate_content(content)
        if translated:
            article["translated_content"] = translated
    return article


def batch_translate_articles(articles: list[dict], batch_size: int = 15) -> None:
    """Translate multiple articles in batch API calls.

    Groups articles into batches, sends one LLM call per batch with all
    title/summary pairs listed, and parses numbered responses.
    Modifies articles in-place, filling translated_title and translated_summary.
    Skips articles already in Chinese.
    """
    from translator import contains_chinese
    if not config.TRANSLATE_TO_CHINESE or not articles:
        return

    # Identify which articles need translation
    needs_translation = []
    for i, art in enumerate(articles):
        if art.get("translated_title"):
            continue  # already translated
        if contains_chinese(art.get("title", "")):
            # Already Chinese, no translation needed
            art["translated_title"] = art["title"]
            art["translated_summary"] = art.get("summary", "")
            continue
        needs_translation.append(i)

    if not needs_translation:
        return

    from llm_client import create_completion
    from translator import apply_glossary

    for bstart in range(0, len(needs_translation), batch_size):
        batch_indices = needs_translation[bstart:bstart + batch_size]
        items = []
        local_idx = 0
        for idx in batch_indices:
            local_idx += 1
            art = articles[idx]
            title = art["title"].replace("{", "{{").replace("}", "}}")
            summary = (art.get("summary", "")[:1000]).replace("{", "{{").replace("}", "}}")
            items.append(
                f"[Article {local_idx}]\n"
                f"Title: {title}\n"
                f"Summary: {summary}"
            )

        prompt = f"""Translate the following news articles from any foreign language to Chinese (中文). Keep technical terms accurate.

For EACH article reply with exactly two lines:
[Article N]
Translated Title: <translated title>
Translated Summary: <translated summary>

Do NOT skip any article. Reply ONLY with these lines, nothing else.

{chr(10).join(items)}"""

        try:
            answer = create_completion(
                model=config.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100 + len(batch_indices) * 200,
            ).strip()
            if not answer:
                log.warning(f"Batch translation empty for batch {bstart//batch_size}, falling back")
                _fallback_individual(articles, batch_indices)
                continue

            # Parse response: find blocks by "[Article N]" header
            parsed = 0
            current_local = 1
            lines = answer.split("\n")
            i = 0
            while i < len(lines) and current_local <= len(batch_indices):
                line = lines[i].strip()
                expected_header = f"[Article {current_local}]"
                if line == expected_header or line.startswith(expected_header + " "):
                    # Next lines should contain Translated Title and Translated Summary
                    t_title = ""
                    t_summary = ""
                    i += 1
                    while i < len(lines) and not lines[i].strip().startswith("[Article "):
                        cl = lines[i].strip()
                        if cl.lower().startswith("translated title:"):
                            t_title = cl.split(":", 1)[1].strip()
                        elif cl.lower().startswith("translated summary:"):
                            t_summary = cl.split(":", 1)[1].strip()
                        i += 1
                    idx = batch_indices[current_local - 1]
                    art = articles[idx]
                    if t_title:
                        art["translated_title"] = apply_glossary(t_title, config.THEME_NAME)
                        parsed += 1
                    if t_summary:
                        art["translated_summary"] = apply_glossary(t_summary, config.THEME_NAME)
                    current_local += 1
                else:
                    i += 1

            # Fallback for any that failed parsing
            failed = []
            for idx in batch_indices:
                art = articles[idx]
                if not art.get("translated_title"):
                    failed.append(idx)

            if failed:
                log.info(f"batch_translate: {parsed}/{len(batch_indices)} parsed, "
                         f"{len(failed)} falling back to individual")
                _fallback_individual(articles, failed)
            else:
                log.info(f"batch_translate: {parsed}/{len(batch_indices)} translated in batch {bstart // batch_size}")

        except Exception as e:
            log.warning(f"Batch translation failed: {e}, falling back to individual")
            _fallback_individual(articles, batch_indices)


def _fallback_individual(articles: list[dict], indices: list[int]) -> None:
    """Translate remaining articles one by one (fallback for batch failures)."""
    from translator import translate_article as do_translate
    for idx in indices:
        art = articles[idx]
        try:
            result = do_translate(art["title"], art.get("summary", ""))
            if result:
                art["translated_title"] = result.get("title", art["title"])
                art["translated_summary"] = result.get("summary", art.get("summary", ""))
        except Exception as e:
            log.warning(f"Individual translation fallback failed for {art['title'][:50]}: {e}")


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


# ── Batch LLM Filter ────────────────────────────────────────────────────────


def batch_llm_filter(entries: list[dict], batch_size: int = 20) -> list[bool]:
    """Filter articles in batches using LLM.

    Groups articles into batches, sends one API call per batch with all articles
    listed, and parses \"INDEX: YES/NO\" responses.  Returns a bool list parallel
    to *entries* (True = relevant, accepted).
    """
    if not config.USE_LLM_FILTER or not config.LLM_API_KEY:
        return [True] * len(entries)

    from llm_client import create_completion

    base_rules = config.LLM_FILTER_PROMPT
    # Extract rules before the per-article template
    cut = base_rules.find("Article title:")
    rules = base_rules[:cut].strip() if cut > 0 else base_rules

    results: list[bool] = [True] * len(entries)  # default accept on parse failure

    for bstart in range(0, len(entries), batch_size):
        batch = entries[bstart:bstart + batch_size]

        items = []
        for i, art in enumerate(batch, 1):
            title = art["title"].replace("{", "{{").replace("}", "}}")
            summary = (art.get("summary", "")[:500]).replace("{", "{{").replace("}", "}}")
            items.append(f"{i}. Title: {title}\n   Summary: {summary}")

        prompt = f"""{rules}

For EACH article below, reply with exactly one line in the format "INDEX: YES" or "INDEX: NO".
Reply ONLY with these lines.

{chr(10).join(items)}"""

        try:
            answer = create_completion(
                model=config.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=50 + len(batch) * 10,
            ).strip()
            if not answer:
                continue  # keep defaults (True)
            for line in answer.split("\n"):
                line = line.strip()
                m = re.match(r"(\d+)\s*[:：]\s*(YES|NO)", line, re.IGNORECASE)
                if m:
                    idx = int(m.group(1)) - 1
                    if 0 <= idx < len(batch):
                        results[bstart + idx] = m.group(2).upper() == "YES"
        except Exception as e:
            log.warning(f"batch_llm_filter batch {bstart//batch_size} failed: {e}")

    # Log summary
    yes_count = sum(results)
    log.info(f"batch_llm_filter: {yes_count}/{len(entries)} accepted "
             f"({yes_count/max(len(entries),1)*100:.0f}%)")
    return results


# ── Main Polling Logic ────────────────────────────────────────────────────


def poll_once(conn: sqlite3.Connection, dry_run=False, skip_llm=False, source_type=None) -> list[dict]:
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

    # Filter sources by type if requested
    active_sources = {name: url for name, url in config.RSS_SOURCES.items() if name not in disabled_sources}
    if source_type:
        active_sources = {name: url for name, url in active_sources.items()
                          if article_type(name, "", "") == source_type}
        log.info(f"Source type filter: {source_type} → {len(active_sources)} source(s)")
    all_source_names = set(active_sources.keys())

    # With 100+ RSS sources, more workers keep poll times reasonable
    with ThreadPoolExecutor(max_workers=15) as pool:
        fut_map = {pool.submit(fetch_rss, url): name for name, url in active_sources.items()}
        try:
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
        except TimeoutError:
            log.warning("Global RSS fetch timeout (300s) reached, continuing with partial results")

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
    seen_urls: set[str] = set()

    # Cache recent titles once for similarity dedup (avoids N+1 inside loop)
    try:
        _recent_rows = conn.execute(
            "SELECT title, source FROM articles WHERE fetched_at > datetime('now', '-7 days')"
        ).fetchall()
        all_recent_titles = [(r[0], r[1]) for r in _recent_rows]
    except Exception:
        all_recent_titles = []

    # ── Phase 1: Fetch RSS → dedup → keyword match (collect candidates) ──
    candidates: list[tuple[str, dict, list[str]]] = []

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

            # URL-based dedup: same normalized URL already seen in current batch
            norm_url = _normalize_url(entry["url"])
            if norm_url in seen_urls:
                log.info(f"URL already seen, skipping: {entry['title'][:60]}...")
                continue

            # Date filter: skip articles published before COLLECT_START_DATE
            if not _published_after_cutoff(entry.get("published", "")):
                log.debug(f"Before cutoff, skipping: {entry['title'][:60]}...")
                continue

            # Title-based dedup: check against cached recent titles AND current batch
            all_titles_with_src = all_recent_titles + seen_titles
            is_dupe = False
            for t, src in all_titles_with_src:
                sim = _title_similarity(entry["title"], t)
                threshold = 0.80
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

            candidates.append((source_name, entry, matched))

    # ── Phase 2: Batch LLM filter ──
    if candidates and not skip_llm:
        batch_results = batch_llm_filter([c[1] for c in candidates])
        accepted: list[tuple[str, dict, list[str]]] = []
        for (source_name, entry, matched), keep in zip(candidates, batch_results):
            if keep:
                accepted.append((source_name, entry, matched))
            else:
                log.info(f"LLM rejected: {entry['title'][:60]}...")
    else:
        accepted = candidates

    # ── Phase 3: Save accepted articles ──
    # Phase 3a: Build article dicts (dedup + score filter)
    to_save: list[dict] = []
    for source_name, entry, matched in accepted:
        article_id = make_article_id(entry["url"], entry["title"])
        norm_url = _normalize_url(entry["url"])

        # Skip if already in DB
        if article_exists(conn, article_id):
            continue
        if norm_url in seen_urls:
            log.info(f"URL already seen, skipping: {entry['title'][:60]}...")
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
            "published": entry.get("published", "") or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "summary": entry.get("summary", ""),
            "matched_kw": ", ".join(matched),
            "relevance": score,
            "content": "",
            "author": entry.get("author", ""),
            "affiliation": "",
            "image_url": "",
            "content_images": "",
            "translated_title": "",
            "translated_summary": "",
            "translated_content": "",
            "article_type": article_type(source_name, entry["url"], entry.get("author", "")),
            "norm_url": norm_url,
        }
        to_save.append(article)

    # Phase 3b: Batch translate all at once
    if not dry_run and config.TRANSLATE_TO_CHINESE and to_save:
        batch_translate_articles(to_save)

    # Phase 3c: Save each article
    for article in to_save:
        article_id = article["id"]
        norm_url = article.pop("norm_url", "")
        source_name = article["source"]

        if not dry_run:
            # Assign or create event group before saving (if theme supports it)
            if config.HAS_EVENT_GROUPING:
                eg_id, eg_title = find_event_group(
                    conn, article["title"], article.get("published", "")
                )
                article["event_group"] = eg_id
                article["event_title"] = eg_title

            if save_article(conn, article):
                seen_titles.append((article["title"], source_name))

                # Source-based affiliation inference for journalists
                if article.get("author") and not article.get("affiliation"):
                    inferred = _source_based_affiliation(source_name)
                    if inferred:
                        conn.execute(
                            "UPDATE articles SET affiliation=? WHERE id=?",
                            (inferred, article_id),
                        )

                new_articles.append(article)
                display_title = (
                    article.get("translated_title") or article["title"]
                )[:70]
                kw_list = article["matched_kw"].split(", ")[:3]
                log.info(
                    f"[{source_name}] New: {display_title}... "
                    f"(score={article['relevance']}, kw={', '.join(kw_list)})"
                )

    conn.commit()
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

        _cn_re = re.compile(r'[一-鿿]')

        def _translate_to_chinese(text: str) -> str:
            """Translate non-Chinese affiliation to Chinese using LLM."""
            if _cn_re.search(text):
                return text
            try:
                from llm_client import create_completion
                prompt = (
                    f"Translate this institution/organization name into Chinese. "
                    f"Reply with ONLY the Chinese translation.\n\n{text}"
                )
                answer = create_completion(
                    model=config.LLM_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=100,
                ).strip()
                if _cn_re.search(answer):
                    return answer
            except Exception:
                pass
            return text

        def _update_author_articles(author_str: str, affiliation: str) -> int:
            """Update all articles matching the exact author string."""
            affiliation = _translate_to_chinese(affiliation)
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
                            from llm_client import create_completion
                            answer = create_completion(
                                model=config.LLM_MODEL,
                                messages=[{"role": "user", "content": prompt}],
                                max_tokens=60,
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
                    from llm_client import create_completion
                    answer = create_completion(
                        model=config.LLM_MODEL,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=60,
                    ).strip()
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


def run(dry_run=False, skip_llm=False, source_type=None):
    """Run the full monitor cycle."""
    from llm_client import reset_token_usage
    reset_token_usage()
    t_start = datetime.now(timezone.utc)
    log.info("=" * 60)
    log.info(f"{config.APP_NAME} - Starting poll cycle")
    log.info(f"Keywords: {len(config.ALL_KEYWORDS)} active")
    log.info(f"Sources: {len(config.RSS_SOURCES)} feeds")
    if source_type:
        log.info(f"Source type filter: {source_type}")
    if config.USE_LLM_FILTER and config.LLM_API_KEY:
        log.info(f"LLM filter: enabled ({config.LLM_MODEL})")
    if config.TRANSLATE_TO_CHINESE:
        log.info("Translation: enabled (→中文)")
    log.info("=" * 60)

    conn = init_db()
    try:
        new_articles = poll_once(conn, dry_run=dry_run, skip_llm=skip_llm, source_type=source_type)
        t_end = datetime.now(timezone.utc)
        duration_sec = int((t_end - t_start).total_seconds())

        log.info(f"Cycle complete. Found {len(new_articles)} new articles in {duration_sec}s.")

        # Report LLM token usage
        try:
            from llm_client import get_token_usage
            tok = get_token_usage()
            total = tok["prompt_tokens"] + tok["completion_tokens"]
            if total > 0:
                log.info(f"LLM token usage: {tok['prompt_tokens']:,} prompt + {tok['completion_tokens']:,} completion = {total:,} total")
        except Exception:
            pass

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
            try:
                from notifier import notify_batch
                notify_batch(new_articles)
            except Exception as e:
                log.warning(f"Notification failed: {e}")

        cleanup_snapshots(days=30)

        # Auto-backfill missing affiliations for newly fetched articles
        if not dry_run:
            try:
                backfill_affiliations()
            except Exception as e:
                log.warning(f"Affiliation backfill failed: {e}")

        return new_articles
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    dry_run = "--dry-run" in sys.argv
    skip_llm = "--skip-llm" in sys.argv
    run(dry_run=dry_run, skip_llm=skip_llm)
