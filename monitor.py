#!/usr/bin/env python3
"""
News Monitor - Core Engine
Fetches, filters, translates, archives, and notifies about news articles.
"""
import difflib
import hashlib
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import feedparser
import requests
from bs4 import BeautifulSoup

import config

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

    return conn


def article_exists(conn: sqlite3.Connection, article_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM articles WHERE id = ?", (article_id,)
    ).fetchone() is not None


def save_article(conn: sqlite3.Connection, article: dict) -> bool:
    """Save article to database. Returns True if new (inserted, not ignored)."""
    published = _normalize_date(article.get("published", ""))
    try:
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
        return conn.total_changes > 0
    except Exception as e:
        log.error(f"DB save error: {e}")
        return False


def get_articles(conn: sqlite3.Connection, limit=50, offset=0, unread_only=False, type_filter=""):
    query = "SELECT * FROM articles WHERE 1=1"
    if unread_only:
        query += " AND is_read = 0"
    if type_filter in ("paper", "news"):
        query += f" AND article_type = '{type_filter}'"
    query += " ORDER BY published DESC, relevance DESC LIMIT ? OFFSET ?"
    return conn.execute(query, (limit, offset)).fetchall()


def mark_read(conn: sqlite3.Connection, article_id: str):
    conn.execute("UPDATE articles SET is_read = 1 WHERE id = ?", (article_id,))
    conn.commit()


def search_articles(conn: sqlite3.Connection, keyword: str, limit=50):
    return conn.execute(
        "SELECT * FROM articles WHERE title LIKE ? OR summary LIKE ? "
        "OR translated_title LIKE ? OR translated_summary LIKE ? "
        "ORDER BY published DESC, relevance DESC LIMIT ?",
        (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%", f"%{keyword}%", limit),
    ).fetchall()


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
                               limit=50, offset=0, unread_only=False, type_filter=""):
    """Return articles ordered by event_group (grouped together, most recent first).

    Returns list of (row, is_group_start) tuples where is_group_start is True
    when a new event group begins.
    """
    query = "SELECT * FROM articles WHERE 1=1"
    if unread_only:
        query += " AND is_read = 0"
    if type_filter in ("paper", "news"):
        query += f" AND article_type = '{type_filter}'"
    query += (" ORDER BY "
              "CASE WHEN event_group != '' THEN event_group ELSE id END DESC, "
              "published DESC, relevance DESC "
              "LIMIT ? OFFSET ?")
    rows = conn.execute(query, (limit, offset)).fetchall()

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


def fetch_rss(url: str, timeout=15) -> list[dict]:
    """Fetch RSS feed and return raw entries."""
    entries = []
    try:
        feed = feedparser.parse(url)
        if feed.bozo and not feed.entries:
            log.warning(f"Feed parse error for {url}: {feed.bozo_exception}")
            return entries
        for entry in feed.entries:
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
                "published": entry.get("published", ""),
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
        for tag in soup(["script", "style", "nav", "footer", "aside", "iframe", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        return text
    except Exception as e:
        log.debug(f"Readability extraction failed: {e}")
        return ""


def _extract_largest_cluster(html: str, min_len=200) -> str:
    """Fallback: find the largest cluster of paragraphs/text blocks."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside",
                      "iframe", "noscript", "form", "button", "svg"]):
        tag.decompose()

    candidates = []
    for el in soup.find_all(["article", "main", "div", "section", "pre", "td",
                              "blockquote", "li", "p"]):
        el_text = el.get_text(separator="\n", strip=True)
        el_len = len(el_text)
        if el_len > min_len:
            candidates.append((el_len, el_text))

    if not candidates:
        body = soup.find("body")
        if body:
            return body.get_text(separator="\n", strip=True)[:8000]
        return ""

    candidates.sort(reverse=True)
    best_len, best_text = candidates[0]

    if len(candidates) > 1 and candidates[1][0] > best_len * 0.5:
        best_text = best_text + "\n\n" + candidates[1][1]

    return best_text[:8000]


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
    for ua in user_agents:
        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
        }
        try:
            r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
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
                # Fallback: find first image in article body, then sidebar, skip logos/icons
                content_areas = soup.find_all(["article", "main", "div", "section"],
                                               class_=re.compile(r"(content|post|article|entry|main)", re.I))
                if not content_areas:
                    content_areas = [soup]
                for area in content_areas:
                    for img in area.find_all("img", src=re.compile(r"https?://")):
                        src = img.get("src", "")
                        alt = img.get("alt", "") or ""
                        if not src or src.endswith((".svg", ".gif")):
                            continue
                        if re.search(r"(logo|avatar|favicon|banner)", src, re.I):
                            continue
                        if re.search(r"(logo|avatar|favicon|banner)", alt, re.I):
                            continue
                        w = img.get("width")
                        if w and w.isdigit() and int(w) < 100:
                            continue
                        image_url = src
                        break
                    if image_url:
                        break

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
    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Archived Article</title></head>
<body>
<pre style="white-space:pre-wrap;font-family:sans-serif;line-height:1.6;">
{content}
</pre>
</body>
</html>"""
    path.write_text(html, encoding="utf-8")
    return path


# ── Main Polling Logic ────────────────────────────────────────────────────


def poll_once(conn: sqlite3.Connection, dry_run=False, skip_llm=False) -> list[dict]:
    """Run one polling cycle. Returns list of new articles found."""
    new_articles = []
    total_keyword_matches = 0

    for source_name, rss_url in config.RSS_SOURCES.items():
        raw_entries = fetch_rss(rss_url)
        for entry in raw_entries:
            if not entry["title"] or not entry["url"]:
                continue

            article_id = make_article_id(entry["url"], entry["title"])

            # Skip if already in DB (by URL-based ID)
            if article_exists(conn, article_id):
                continue

            # Date filter: skip articles published before COLLECT_START_DATE
            if not _published_after_cutoff(entry.get("published", "")):
                log.debug(f"Before cutoff, skipping: {entry['title'][:60]}...")
                continue

            # Title-based dedup: check if a very similar title already exists (last 7 days)
            recent = conn.execute(
                "SELECT title FROM articles WHERE published > datetime('now', '-7 days')"
            ).fetchall()
            if any(_title_similarity(entry["title"], t[0]) > 0.60 for t in recent):
                log.info(f"Title similar, skipping: {entry['title'][:60]}...")
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
        return new_articles
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    dry_run = "--dry-run" in sys.argv
    skip_llm = "--skip-llm" in sys.argv
    run(dry_run=dry_run, skip_llm=skip_llm)
