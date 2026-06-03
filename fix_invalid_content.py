#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分析并修复无效内容的综合脚本
这个脚本会在服务器上运行
"""
import sqlite3
import re
import sys
import json
from datetime import datetime

def check_invalid_content(text):
    """检查文本是否是无效内容"""
    if not text or len(text.strip()) == 0:
        return False, "empty"
    
    # 检查是否是登录/验证页面内容
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
    
    # 检查内容太短（低于100字符，且不是标题类型）
    if len(text.strip()) < 100:
        return True, "too_short"
    
    # 检查是否包含大量重复内容
    # 检查是否重复3次以上的短语
    words = text.split()
    if len(words) > 10:
        word_counts = {}
        for word in words[:100]:  # 只检查前100个词
            word_counts[word] = word_counts.get(word, 0) + 1
        
        # 检查是否有重复超过5次的单词
        repeated_words = [w for w, c in word_counts.items() if c > 5 and len(w) > 2]
        if len(repeated_words) > 10:
            return True, f"repeated_content"
    
    # 检查是否是导航/菜单内容
    nav_patterns = [
        r"^首页\s*$", r"^关于我们\s*$", r"^联系我们\s*$",
        r"^产品\s*$", r"^服务\s*$", r"^新闻\s*$",
        r"^帮助\s*$", r"^支持\s*$", r"^下载\s*$",
        r"^菜单\s*$", r"^导航\s*$"
    ]
    
    lines = text.split('\n')
    nav_lines = sum(1 for line in lines if any(re.match(pat, line.strip(), re.I) for pat in nav_patterns))
    if nav_lines > len(lines) * 0.3:  # 如果超过30%的行是导航
        return True, "navigation_menu"
    
    # 检查是否主要是广告/相关链接内容
    junk_words = ["related", "recommended", "subscribe", "advertisement", "sponsored", 
                 "newsletter", "click here", "you may also like", "share", "follow"]
    junk_count = sum(1 for word in junk_words if word in text.lower())
    if junk_count > 5 and len(text) < 2000:
        return True, "advertisement"
    
    return False, None

def main():
    conn = sqlite3.connect('data/news.db')
    c = conn.cursor()
    
    print(f"=== 开始分析无效内容 === {datetime.now()}")
    print()
    
    # 统计
    total = c.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    with_content = c.execute("SELECT COUNT(*) FROM articles WHERE content IS NOT NULL AND content != ''").fetchone()[0]
    
    print(f"总文章数: {total}")
    print(f"有内容的文章: {with_content}")
    print()
    
    # 查找所有有内容的文章
    print("正在检查文章...")
    invalid_stats = {}
    invalid_articles = []
    
    c.execute("SELECT id, title, url, content FROM articles WHERE content IS NOT NULL AND content != ''")
    all_articles = c.fetchall()
    
    for idx, (art_id, title, url, content) in enumerate(all_articles):
        is_invalid, reason = check_invalid_content(content)
        
        if is_invalid:
            invalid_stats[reason] = invalid_stats.get(reason, 0) + 1
            invalid_articles.append((art_id, title, reason, content))
        
        if (idx + 1) % 100 == 0:
            print(f"已检查 {idx + 1}/{len(all_articles)} 篇文章...")
    
    print()
    print(f"=== 检查完成 ===")
    print(f"无效文章统计:")
    for reason, count in sorted(invalid_stats.items(), key=lambda x: -x[1]):
        print(f"  - {reason}: {count}")
    
    print()
    if invalid_articles:
        print(f"无效文章样本 (前10篇):")
        for i, (art_id, title, reason, content) in enumerate(invalid_articles[:10]):
            print(f"{i+1}. ID: {art_id}")
            print(f"   标题: {title}")
            print(f"   原因: {reason}")
            print(f"   内容预览: {repr(content[:200])}")
            print()
    
    # 询问是否修复
    if input("是否修复这些无效内容? (y/n): ").lower() == 'y':
        print()
        print("=== 开始修复 ===")
        
        # 备份数据库
        import shutil
        shutil.copy('data/news.db', f'data/news.db.backup_invalid_content_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
        print("已备份数据库")
        
        # 清除无效内容
        cleared_count = 0
        for art_id, title, reason, _ in invalid_articles:
            c.execute("UPDATE articles SET content = '' WHERE id = ?", (art_id,))
            cleared_count += 1
            if cleared_count % 50 == 0:
                print(f"已清除 {cleared_count}/{len(invalid_articles)} 篇文章的无效内容...")
        
        conn.commit()
        print()
        print(f"=== 修复完成 ===")
        print(f"已清除 {cleared_count} 篇文章的无效内容")
        print()
        print("接下来，让我们更新抓取程序，避免将来抓取无效内容...")
    
    conn.close()

if __name__ == "__main__":
    main()
