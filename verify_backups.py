
import sqlite3
import sys

print("=== Checking backup news.db ===")
try:
    conn = sqlite3.connect("backups/news-20260529.db")
    count = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    source_count = conn.execute("SELECT COUNT(*) FROM source_stats").fetchone()[0]
    print(f"  Articles: {count}")
    print(f"  Sources: {source_count}")
    conn.close()
    print("  ✅ News backup OK")
except Exception as e:
    print(f"  ❌ News backup failed: {e}")
    sys.exit(1)

print("\n=== Checking backup aam.db ===")
try:
    conn = sqlite3.connect("backups/aam-20260529.db")
    count = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    source_count = conn.execute("SELECT COUNT(*) FROM source_stats").fetchone()[0]
    print(f"  Articles: {count}")
    print(f"  Sources: {source_count}")
    conn.close()
    print("  ✅ AAM backup OK")
except Exception as e:
    print(f"  ❌ AAM backup failed: {e}")
    sys.exit(1)

print("\n✅ Both backups are good!")
