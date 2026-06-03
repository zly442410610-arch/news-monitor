
import sqlite3
from datetime import datetime

def init_source_stats(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 检查已有数据
    count = cursor.execute("SELECT COUNT(*) FROM source_stats").fetchone()[0]
    if count > 0:
        print(f"{db_path} already has {count} source_stats entries")
        conn.close()
        return
    
    # 从articles表提取所有不同的source
    sources = cursor.execute("SELECT DISTINCT source FROM articles").fetchall()
    now = datetime.now().isoformat()
    
    for (source,) in sources:
        # 统计该来源的文章数量
        article_count = cursor.execute("SELECT COUNT(*) FROM articles WHERE source = ?", (source,)).fetchone()[0]
        # 插入source_stats
        cursor.execute(
            "INSERT INTO source_stats (source_name, fetched_at, success, articles_found, error_msg) VALUES (?, ?, 1, ?, '')",
            (source, now, article_count)
        )
        print(f"  Added: {source} ({article_count} articles)")
    
    conn.commit()
    print(f"Added {len(sources)} sources to {db_path}")
    conn.close()

print("=== News DB ===")
init_source_stats("news.db")
print("\n=== AAM DB ===")
init_source_stats("aam.db")
