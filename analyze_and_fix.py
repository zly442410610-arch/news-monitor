
import sqlite3
import re
from datetime import datetime

def check_invalid_content(text):
    if not text or len(text.strip()) == 0:
        return False, "empty"
    
    invalid_keywords = [
        "登录", "login", "Cookie", "cookie", "验证码", "captcha",
        "验证", "blocked", "error", "访问", "检查", "verify",
        "请您先", "需要登录", "登录账号", "sign in", "log in",
        "登录以", "登录才能", "先登录", "登录访问",
        "人机验证", "human verification", "security check",
        "被阻止", "blocked", "forbidden", "403", "404", "500"
    ]
    
    text_lower = text.lower()
    found_keywords = [kw for kw in invalid_keywords if kw.lower() in text_lower]
    
    if len(found_keywords) > 0 and len(text) < 3000:
        return True, f"login/captcha ({', '.join(found_keywords[:3])})"
    
    if len(text.strip()) < 100:
        return True, "too_short"
    
    return False, None

conn = sqlite3.connect('data/news.db')
c = conn.cursor()
print(f"=== 分析无效内容 === {datetime.now()}")

total = c.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
with_content = c.execute("SELECT COUNT(*) FROM articles WHERE content IS NOT NULL AND content != ''").fetchone()[0]

print(f"总文章数: {total}")
print(f"有内容的文章: {with_content}")
print()

invalid_stats = {}
invalid_articles = []
c.execute("SELECT id, title, url, content FROM articles WHERE content IS NOT NULL AND content != ''")
all_articles = c.fetchall()

for art_id, title, url, content in all_articles:
    is_invalid, reason = check_invalid_content(content)
    if is_invalid:
        invalid_stats[reason] = invalid_stats.get(reason, 0) + 1
        invalid_articles.append((art_id, title, reason))

print(f"=== 检查结果 ===")
for reason, count in sorted(invalid_stats.items(), key=lambda x: -x[1]):
    print(f"  - {reason}: {count}")

print(f"\n无效文章总数: {len(invalid_articles)}")
print()

# 自动修复（直接进行，不询问）
print("=== 开始自动修复 ===")
import shutil
backup_name = f'data/news.db.backup_invalid_content_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
shutil.copy('data/news.db', backup_name)
print(f"已备份数据库到: {backup_name}")

cleared_count = 0
for art_id, title, reason in invalid_articles:
    c.execute("UPDATE articles SET content = '' WHERE id = ?", (art_id,))
    cleared_count += 1

conn.commit()
print(f"已清除 {cleared_count} 篇文章的无效内容")
conn.close()
print("=== 修复完成 ===")
