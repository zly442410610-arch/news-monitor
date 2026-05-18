#!/usr/bin/env python3
"""
Aerospace News Monitor - Core Engine
Fetches, filters, translates, archives, and notifies about aerospace news.
"""
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
log = logging.getLogger("news-monitor")

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
            event_title       TEXT DEFAULT ''
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_articles_published
        ON articles(published)
    """)
    # Migrate old schema if needed (add columns that may not exist)
    try:
        conn.execute("SELECT translated_title FROM articles LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE articles ADD COLUMN translated_title TEXT DEFAULT ''")
        conn.execute("ALTER TABLE articles ADD COLUMN translated_summary TEXT DEFAULT ''")
        conn.execute("ALTER TABLE articles ADD COLUMN is_translated INTEGER DEFAULT 0")
    # Migrate old schema if needed (add author columns)
    try:
        conn.execute("SELECT author FROM articles LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE articles ADD COLUMN author TEXT DEFAULT ''")
        conn.execute("ALTER TABLE articles ADD COLUMN affiliation TEXT DEFAULT ''")
    # Migrate old schema if needed (add event grouping columns)
    try:
        conn.execute("SELECT event_group FROM articles LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE articles ADD COLUMN event_group TEXT DEFAULT ''")
        conn.execute("ALTER TABLE articles ADD COLUMN event_title TEXT DEFAULT ''")
    conn.commit()
    return conn


def article_exists(conn: sqlite3.Connection, article_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM articles WHERE id = ?", (article_id,)
    ).fetchone() is not None


def save_article(conn: sqlite3.Connection, article: dict) -> bool:
    """Save article to database. Returns True if new (inserted, not ignored)."""
    try:
        conn.execute("""
            INSERT OR IGNORE INTO articles
                (id, title, url, source, published, fetched_at, summary,
                 matched_kw, relevance, translated_title, translated_summary, is_translated,
                 author, affiliation, event_group, event_title)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            article["id"],
            article["title"],
            article["url"],
            article["source"],
            article.get("published", ""),
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
        ))
        conn.commit()
        return conn.total_changes > 0
    except Exception as e:
        log.error(f"DB save error: {e}")
        return False


def get_articles(conn: sqlite3.Connection, limit=50, offset=0, unread_only=False):
    query = "SELECT * FROM articles"
    if unread_only:
        query += " WHERE is_read = 0"
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

import difflib


def _normalize_title(title: str) -> str:
    """Normalize title for similarity comparison."""
    t = title.lower().strip()
    # Remove trailing punctuation
    t = t.rstrip(".。!！?？,:：;；·")
    # Remove common prefixes
    for prefix in ["breaking: ", "update: ", "新闻：", "快讯：", "最新：", "重磅："]:
        if t.startswith(prefix):
            t = t[len(prefix):]
            break
    return t


def _title_similarity(t1: str, t2: str) -> float:
    """Calculate title similarity using SequenceMatcher."""
    n1 = _normalize_title(t1)
    n2 = _normalize_title(t2)
    return difflib.SequenceMatcher(None, n1, n2).ratio()


def find_event_group(conn: sqlite3.Connection, title: str,
                     published: str) -> tuple[str, str]:
    """Find an existing event group for this article, or create a new one.

    Returns (event_group_id, event_title).
    """
    # Only look at recent articles (last 14 days)
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

    # Threshold: 0.55 (covers "India launches X" vs "Indian space agency launches X")
    if best_match and best_score >= 0.55:
        return best_match

    # No match — create a new group
    new_id = hashlib.sha256(
        _normalize_title(title).encode()
    ).hexdigest()[:16]
    return (new_id, title)


def get_event_grouped_articles(conn: sqlite3.Connection,
                               limit=50, offset=0, unread_only=False):
    """Return articles ordered by event_group (grouped together, most recent first).

    Returns list of (row, is_group_start) tuples where is_group_start is True
    when a new event group begins.
    """
    query = "SELECT * FROM articles"
    if unread_only:
        query += " WHERE is_read = 0"
    # Order so same event_group articles are together, newest first
    query += (" ORDER BY "
              "CASE WHEN event_group != '' THEN event_group ELSE id END DESC, "
              "published DESC, relevance DESC "
              "LIMIT ? OFFSET ?")
    rows = conn.execute(query, (limit, offset)).fetchall()

    # Detect group boundaries
    result = []
    last_group = None
    for row in rows:
        eg = row[16] if len(row) > 16 else ""  # event_group column
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
            # Extract author
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
            # Clean HTML from summary
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


def fetch_article_content(url: str, timeout=15) -> Optional[dict]:
    """Fetch full article HTML, extract text and metadata (author, affiliation)."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
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
        # Extract author/affiliation from HTML metadata
        author = ""
        affiliation = ""
        soup = BeautifulSoup(raw_html, "lxml")

        # Try meta tags first
        meta_authors = soup.find_all("meta", attrs={"name": re.compile(r"author|citation_author", re.I)})
        if meta_authors:
            author = "; ".join(m.get("content", "") for m in meta_authors if m.get("content"))
        # Try citation_author_institution (used by arXiv, Google Scholar)
        if not affiliation:
            meta_affils = soup.find_all("meta", attrs={"name": re.compile(r"citation_author_institution|citation_author_affiliation", re.I)})
            if meta_affils:
                affiliation = "; ".join(m.get("content", "") for m in meta_affils if m.get("content"))

        # Fallback: look for author/affiliation in common class names
        if not author:
            for cls in ["author", "authors", "byline", "article-author"]:
                el = soup.find(class_=re.compile(cls, re.I))
                if el:
                    author = el.get_text(separator=", ", strip=True)[:200]
                    break

        # Clean: remove HTML, get text
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)

        return {
            "text": text[:8000],
            "author": author,
            "affiliation": affiliation,
        }
    except requests.RequestException as e:
        log.debug(f"Content fetch failed for {url}: {e}")
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
    if not config.TRANSLATE_TO_CHINESE:
        return article

    result = do_translate(article["title"], article.get("summary", ""))
    if result:
        article["translated_title"] = result.get("title", article["title"])
        article["translated_summary"] = result.get("summary", article.get("summary", ""))
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

            # Title-based dedup: check if a very similar title already exists
            title_key = entry["title"][:80].lower().strip()
            dup = conn.execute(
                "SELECT title FROM articles WHERE title LIKE ? LIMIT 1",
                (title_key[:60] + "%",)
            ).fetchone()
            if dup:
                log.debug(f"Title duplicate, skipping: {entry['title'][:60]}...")
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

            # Use page-level author if RSS didn't provide one
            effective_author = entry.get("author", "") or page_author

            # Second pass: LLM filter (if enabled)
            article_data = {**entry, "content": content or ""}
            if not skip_llm and not llm_filter(article_data):
                log.info(f"LLM rejected: {entry['title'][:60]}...")
                continue

            score = relevance_score(matched, entry["title"], entry["summary"])

            # Third pass: minimum relevance score threshold
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
                "translated_title": "",
                "translated_summary": "",
            }

            # Translate to Chinese
            if not dry_run and config.TRANSLATE_TO_CHINESE:
                article = translate_article(article)
                # If article is already Chinese, translator returns None — mark as translated
                if article and not article.get("translated_title"):
                    from translator import contains_chinese
                    if contains_chinese(article.get("title", "")):
                        article["translated_title"] = article["title"]
                        article["translated_summary"] = article.get("summary", "")

            if not dry_run:
                # Assign or create event group before saving
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
    log.info("=" * 60)
    log.info("Aerospace News Monitor - Starting poll cycle")
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
        log.info(f"Cycle complete. Found {len(new_articles)} new articles.")

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
