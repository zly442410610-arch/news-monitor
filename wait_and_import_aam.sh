#!/bin/bash
# Wait for AAM poll to finish, then import the AAM review paper
POLL_PID=$(pgrep -f "main.py poll" | head -1)
if [ -n "$POLL_PID" ]; then
    echo "Waiting for AAM poll (PID $POLL_PID) to finish..."
    while kill -0 "$POLL_PID" 2>/dev/null; do
        sleep 30
    done
    echo "Poll finished at $(date). Importing AAM review..."
fi
cd /root/news-monitor && python3 -c "
import sqlite3, hashlib, time, logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger('auto_import')

with open('/tmp/aam_review_2025_text.txt') as f:
    text = f.read()

conn = sqlite3.connect('data/aam.db')
conn.execute('PRAGMA busy_timeout = 30000')
cur = conn.cursor()

title = '2025年国外空空导弹发展回顾'
aid = hashlib.sha256(title.encode()).hexdigest()[:24]
cur.execute('SELECT id FROM articles WHERE id = ?', (aid,))
if cur.fetchone():
    log.warning('AAM review already exists, skipping')
else:
    import re
    summary = re.sub(r'\s+', ' ', text[:1500]).strip()[:1000]
    now = time.strftime('%Y-%m-%d %H:%M:%S')
    cur.execute(\"\"\"
        INSERT INTO articles (id, title, url, source, published, fetched_at,
                              summary, relevance, is_read, is_archived,
                              translated_title, is_translated, author,
                              article_type, content, translated_content)
        VALUES (?, ?, ?, ?, ?, ?,
                ?, ?, 0, 0,
                ?, ?, ?,
                ?, ?, ?)
    \"\"\", (
        aid, title,
        'https://www.qk.sjtu.edu.cn/ktfy/EN/Y2026/V9/I2/105',
        '空天防御', '2026', now,
        summary, 100,
        title, 1, '夏晓靖, 唐楚淳, 杨闯, 桑晨, 惠文智',
        'review', text, ''
    ))
    conn.commit()
    log.info(f'Imported AAM review: {title} ({len(text)} chars)')

conn.close()
print('AAM review import complete!')
" 2>&1 | tee -a /var/log/aam-import.log
