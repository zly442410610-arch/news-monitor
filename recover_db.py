
import sqlite3
import sys

def recover_db(source_path, dest_path):
    print(f"Recovering {source_path} -> {dest_path}")
    try:
        # 先尝试直接连接并查询articles
        source_conn = sqlite3.connect(source_path)
        articles = source_conn.execute("SELECT * FROM articles").fetchall()
        print(f"  Found {len(articles)} articles")
        
        # 创建新数据库
        dest_conn = sqlite3.connect(dest_path)
        dest_conn.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id TEXT PRIMARY KEY,
                source TEXT,
                title TEXT,
                content TEXT,
                summary TEXT,
                translated_title TEXT,
                translated_content TEXT,
                article_type TEXT,
                relevance REAL,
                matched_kw TEXT,
                published TEXT,
                fetched_at TEXT,
                link TEXT,
                raw_html TEXT,
                patent_id TEXT
            )
        """)
        dest_conn.execute("""
            CREATE TABLE IF NOT EXISTS source_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_name TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                success INTEGER NOT NULL DEFAULT 1,
                articles_found INTEGER NOT NULL DEFAULT 0,
                error_msg TEXT NOT NULL DEFAULT ''
            )
        """)
        
        # 复制文章
        dest_conn.executemany("INSERT OR IGNORE INTO articles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", articles)
        dest_conn.commit()
        print(f"  Copied {len(articles)} articles")
        
        # 从articles生成source_stats
        sources = dest_conn.execute("SELECT DISTINCT source FROM articles").fetchall()
        from datetime import datetime
        now = datetime.now().isoformat()
        for (source,) in sources:
            cnt = dest_conn.execute("SELECT COUNT(*) FROM articles WHERE source=?", (source,)).fetchone()[0]
            dest_conn.execute("INSERT INTO source_stats (source_name, fetched_at, success, articles_found) VALUES (?, ?, 1, ?)", (source, now, cnt))
        dest_conn.commit()
        print(f"  Added {len(sources)} sources to source_stats")
        
        source_conn.close()
        dest_conn.close()
        print(f"✅ Recovered to {dest_path}")
        return True
    except Exception as e:
        print(f"❌ Failed to recover {source_path}: {e}")
        import traceback
        traceback.print_exc()
        return False

# 尝试恢复news.db
print("=== Recovering news ===")
if not recover_db("data/news.db", "news.db"):
    # 尝试其他可能的备份
    print("\nTrying backups...")
    import os
    for f in os.listdir("."):
        if f.startswith("news.db.backup") and f.endswith(".db"):
            print(f"Trying {f}...")
            if recover_db(f, "news.db"):
                break

# 尝试恢复aam.db
print("\n=== Recovering aam ===")
recover_db("data/aam.db", "aam.db")
