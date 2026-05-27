#!/usr/bin/env python3
"""
Backfill CNKI article content from Playwright output JSON files.
Reads data/cnki_article_*.json and updates the database.

Usage:
  python3 backfill_cnki_content.py              # process all existing output files
  python3 backfill_cnki_content.py --watch       # watch for new files and process them
"""
import json, sys, time, logging, re
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).parent
DATA_DIR = BASE / "data"
DB_PATH = BASE / "data" / "news.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("backfill_cnki")


def extract_content(result: dict) -> dict:
    """Extract the best available content from Playwright page evaluation result."""
    out = {
        "content": "",
        "abstract": "",
        "keywords": "",
        "authors": "",
        "doi": "",
    }

    if not result:
        return out

    # Priority 1: explicit content container matches
    content = (result.get("content") or "").strip()
    # Priority 2: body_text as fallback (but clean it up)
    body = (result.get("body_text") or "").strip()
    # Priority 3: abstract
    abstract = (result.get("abstract") or "").strip()
    # Priority 4: JSON-LD
    jsonld_str = result.get("jsonld") or ""

    if content and len(content) > 200:
        out["content"] = content
    elif body and len(body) > 200:
        out["content"] = body
    elif abstract:
        out["content"] = abstract

    if abstract:
        out["abstract"] = abstract

    # Try to get more detail from JSON-LD
    if jsonld_str:
        try:
            ld = json.loads(jsonld_str)
            if isinstance(ld, list):
                ld = ld[0]
            if isinstance(ld, dict):
                if not out["abstract"]:
                    out["abstract"] = ld.get("description") or ""
                if not out["keywords"]:
                    kw = ld.get("keywords") or ""
                    if isinstance(kw, list):
                        kw = ", ".join(kw)
                    out["keywords"] = kw
                if not out["authors"]:
                    auth = ld.get("author") or []
                    out["authors"] = "; ".join(
                        [a.get("name", "") for a in auth if isinstance(a, dict)]
                    ) if isinstance(auth, list) else ""
        except (json.JSONDecodeError, TypeError):
            pass

    out["keywords"] = result.get("keywords") or out["keywords"]
    out["authors"] = result.get("authors") or out["authors"]
    out["doi"] = result.get("doi") or out["doi"]

    # Clean content: remove excessive whitespace
    for key in ["content", "abstract"]:
        out[key] = re.sub(r"\n{3,}", "\n\n", out[key]).strip()
        out[key] = re.sub(r" {2,}", " ", out[key])

    return out


def update_article_in_db(article_id: str, content_data: dict):
    """Update the article record with fetched content."""
    import sqlite3
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Check if article exists
    cur = conn.execute("SELECT id, title, content FROM articles WHERE id=?", (article_id,))
    row = cur.fetchone()
    if not row:
        log.warning(f"Article {article_id} not found in DB")
        conn.close()
        return False

    existing_content = row["content"] or ""
    new_content = content_data.get("content") or ""
    new_abstract = content_data.get("abstract") or ""

    updates = {}
    if new_content and (not existing_content or len(new_content) > len(existing_content)):
        updates["content"] = new_content
    if new_abstract:
        updates["summary"] = new_abstract
    if content_data.get("keywords"):
        updates["matched_kw"] = content_data["keywords"]
    if content_data.get("authors"):
        updates["author"] = content_data["authors"]
    if content_data.get("doi"):
        updates["source"] = f"CNKI (DOI: {content_data['doi']})"

    if not updates:
        log.info(f"Article {article_id}: no new content to update")
        conn.close()
        return True

    set_clauses = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [article_id]
    conn.execute(f"UPDATE articles SET {set_clauses} WHERE id=?", values)
    conn.commit()

    log.info(f"Article {article_id}: updated {list(updates.keys())} ({len(new_content)} chars content)")
    conn.close()
    return True


def process_file(filepath: Path) -> bool:
    """Process a single output JSON file."""
    try:
        data = json.loads(filepath.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.error(f"Failed to read {filepath}: {e}")
        return False

    article_id = data.get("id")
    result = data.get("result")
    if not article_id or not result:
        log.warning(f"{filepath.name}: missing id or result")
        return False

    content_data = extract_content(result)
    if not content_data.get("content"):
        log.warning(f"{filepath.name}: no content extracted")
        return False

    update_article_in_db(article_id, content_data)

    # Rename file to mark as processed
    processed = filepath.parent / f"{filepath.stem}.processed{filepath.suffix}"
    filepath.rename(processed)
    log.info(f"  Renamed to {processed.name}")
    return True


def main():
    watch = "--watch" in sys.argv

    if watch:
        log.info("Watching for new CNKI article output files...")
        already_processed = set()
        while True:
            files = sorted(DATA_DIR.glob("cnki_article_*.json"))
            for fp in files:
                if fp.name not in already_processed:
                    log.info(f"Found: {fp.name}")
                    process_file(fp)
                    already_processed.add(fp.name)
            time.sleep(5)
    else:
        files = sorted(DATA_DIR.glob("cnki_article_*.json"))
        if not files:
            log.info("No CNKI output files found in data/")
            # Also check for any json that might have been named differently
            files = sorted(DATA_DIR.glob("*.json"))
            if files:
                log.info(f"Found JSON files: {[f.name for f in files]}")
        for fp in files:
            log.info(f"Processing: {fp.name}")
            process_file(fp)

    log.info("Done")


if __name__ == "__main__":
    main()
