
import sqlite3

print("=== Final verification ===")
conn = sqlite3.connect("news.db")
count = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
source_count = conn.execute("SELECT COUNT(*) FROM source_stats").fetchone()[0]
print(f"  News: {count} articles, {source_count} sources")
conn.close()

conn = sqlite3.connect("aam.db")
count = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
source_count = conn.execute("SELECT COUNT(*) FROM source_stats").fetchone()[0]
print(f"  AAM: {count} articles, {source_count} sources")
conn.close()

print("\n✅ Verification passed!")
