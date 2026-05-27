"""Database-backed keyword management.

Keywords stored in the DB augment (not replace) the theme defaults from theme.py.
The merged set is: theme_defaults + db_keywords, with db_keywords appended
to their group (duplicates skipped).
"""

from __future__ import annotations
import sqlite3
from typing import Optional


def init_keywords_table(conn: sqlite3.Connection) -> None:
    """Create keywords table if it does not exist."""
    from schema import METADATA_TABLE_DDLS
    for ddl in METADATA_TABLE_DDLS:
        conn.execute(ddl)
    conn.commit()


def get_db_keywords(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """Fetch keywords from DB, grouped by group_name."""
    groups: dict[str, list[str]] = {}
    rows = conn.execute(
        "SELECT group_name, keyword FROM keywords ORDER BY group_name, id"
    ).fetchall()
    for group_name, keyword in rows:
        groups.setdefault(group_name, []).append(keyword)
    return groups


def get_merged_keywords(
    conn: sqlite3.Connection,
    theme_defaults: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Merge theme defaults with DB keywords.

    DB keywords are appended to their corresponding theme group.
    Groups that exist only in the DB are also included.
    """
    merged: dict[str, list[str]] = {}
    for group, kws in theme_defaults.items():
        merged[group] = list(kws)
    db_groups = get_db_keywords(conn)
    for group, kws in db_groups.items():
        if group in merged:
            existing = set(merged[group])
            for kw in kws:
                if kw not in existing:
                    merged[group].append(kw)
                    existing.add(kw)
        else:
            merged[group] = list(kws)
    return merged


def get_merged_keywords_flat(
    conn: sqlite3.Connection,
    theme_defaults: dict[str, list[str]],
) -> list[str]:
    """Return a flat sorted list of all merged keywords (for keyword_match)."""
    merged = get_merged_keywords(conn, theme_defaults)
    return sorted(set(kw for group in merged.values() for kw in group))


def add_keyword(conn: sqlite3.Connection, group_name: str, keyword: str) -> bool:
    """Add a keyword to a group. Returns True if inserted, False if duplicate."""
    try:
        conn.execute(
            "INSERT INTO keywords (group_name, keyword) VALUES (?, ?)",
            (group_name.strip(), keyword.strip()),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def delete_keyword(conn: sqlite3.Connection, kw_id: int) -> bool:
    """Delete a keyword by its id. Returns True if deleted."""
    cursor = conn.execute("DELETE FROM keywords WHERE id = ?", (kw_id,))
    conn.commit()
    return cursor.rowcount > 0


def delete_keyword_group(conn: sqlite3.Connection, group_name: str) -> int:
    """Delete all keywords in a group. Returns the number of deleted rows."""
    cursor = conn.execute("DELETE FROM keywords WHERE group_name = ?", (group_name,))
    conn.commit()
    return cursor.rowcount
