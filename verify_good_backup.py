
import sqlite3
conn = sqlite3.connect("news.db")
print("News: Articles=%d Sources=%d" % (
    conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0],
    conn.execute("SELECT COUNT(*) FROM source_stats").fetchone()[0]))
conn.close()

conn = sqlite3.connect("aam.db")
print("AAM: Articles=%d Sources=%d" % (
    conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0],
    conn.execute("SELECT COUNT(*) FROM source_stats").fetchone()[0]))
conn.close()
