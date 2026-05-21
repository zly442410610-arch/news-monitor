"""
Shared database schema for the news monitor.
Both monitor.py (polling) and dashboard/handler.py (serving) use the same DDL.
"""
from __future__ import annotations

ARTICLES_TABLE_DDL = """
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
"""

ARTICLES_INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published)",
    "CREATE INDEX IF NOT EXISTS idx_articles_pub_rel ON articles(published DESC, relevance DESC)",
    "CREATE INDEX IF NOT EXISTS idx_articles_fetched ON articles(fetched_at)",
    "CREATE INDEX IF NOT EXISTS idx_articles_event_group ON articles(event_group, published DESC)",
]

# Columns added after the initial schema (for migration from older versions)
EXTRA_COLUMNS: list[tuple[str, str]] = [
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
]

METADATA_TABLE_DDLS: list[str] = [
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
]

FTS5_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
    title, summary, content, translated_title, translated_summary, translated_content,
    content=articles, content_rowid=rowid,
    tokenize='unicode61'
)
"""

FTS_TRIGGER_DDLS: list[str] = [
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
]
