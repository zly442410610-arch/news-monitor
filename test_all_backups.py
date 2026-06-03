
import sqlite3
import os
backups_dir = "backups"

# List all backup files
backup_files = sorted(os.listdir(backups_dir))
print(f"Found {len(backup_files)} backups:")

for f in backup_files:
    if f.endswith(".db"):
        full_path = os.path.join(backups_dir, f)
        try:
            conn = sqlite3.connect(full_path)
            articles = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
            sources = conn.execute("SELECT COUNT(*) FROM source_stats").fetchone()[0]
            conn.close()
            print(f"✅ {f:30} | Articles: {articles:4} | Sources: {sources:4}")
        except Exception as e:
            print(f"❌ {f:30} | ERROR: {e}")
