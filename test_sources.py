
import sqlite3
from monitor import get_source_stats, init_db

print("=== Testing news.db ===")
conn = sqlite3.connect("news.db")
stats = get_source_stats(conn)
print(f"Got {len(stats)} source stats:")
for i, s in enumerate(stats[:5]):
    print(f"  {i+1}. {s}")
conn.close()

print("\n=== Testing aam.db ===")
conn = sqlite3.connect("aam.db")
stats = get_source_stats(conn)
print(f"Got {len(stats)} source stats:")
for i, s in enumerate(stats[:5]):
    print(f"  {i+1}. {s}")
conn.close()

print("\n=== Testing source_stats table directly ===")
conn = sqlite3.connect("news.db")
cursor = conn.execute("SELECT COUNT(*) FROM source_stats")
count = cursor.fetchone()[0]
print(f"Total in source_stats: {count}")
if count > 0:
    print("
Sample from source_stats:")
    cursor = conn.execute("SELECT * FROM source_stats ORDER BY id DESC LIMIT 5")
    for row in cursor.fetchall():
        print(f"  {row}")
conn.close()
