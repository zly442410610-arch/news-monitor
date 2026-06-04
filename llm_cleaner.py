"""LLM-based content cleaner for article text.

Uses the existing LLM client to extract actual article body content,
removing navigation, ads, related articles, and other boilerplate that
regex-based filters can't reliably catch.
"""
import logging
from llm_client import create_completion
import config

log = logging.getLogger("llm_cleaner")

EXTRACT_PROMPT = """你是一个文章内容清洁专家。从网页抓取内容中提取真正的文章正文。

## 必须删除
- 导航菜单、主导航、页脚、版权声明
- Cookie 提示、隐私政策声明、管理偏好
- 登录/注册表单、付费墙提示、订阅邀请
- 广告、赞助内容、推广内容
- "相关文章"、"相似文章"、"推荐阅读"、"热门推荐"、"最新新闻"、"为您推荐"等板块及其下属所有内容
- 标签列表（#tag 行）、分类标签
- 作者头像、作者简介卡片、社交关注链接
- 分享按钮（Facebook/Twitter/微博等）
- 捐款链接、打赏二维码
- 评论区、评论输入框
- 语言切换选项（英文版/中文版/乌克兰语版等）
- 侧边栏内容、面包屑导航
- "打开外部网站"、"在新窗口中打开"等UI提示
- 纯链接列表、站点地图
- 来源网站的品牌标语、通讯社推广语
- 仅含图片标题的无内容段落

## 必须保留
- 文章标题（保持 # 格式）
- 发布日期
- 文章正文段落（保持原始markdown格式）
- 正文中的图片 ![描述](url)
- 正文中的子标题（## 或 ### 格式）
- 正文中的表格
- 正文中的引用

只输出清洁后的内容。如果内容是空的或全为无效信息，输出空字符串。不要添加任何说明。"""


def llm_extract_article(text: str) -> str:
    """Use LLM to extract the actual article body from mixed content.

    Returns cleaned text, or original text if LLM call fails or result is too short.
    """
    if not text or len(text.strip()) < 50:
        return text

    try:
        result = create_completion(
            model=config.LLM_MODEL,
            messages=[
                {"role": "system", "content": EXTRACT_PROMPT},
                {"role": "user", "content": text[:8000]},
            ],
            max_tokens=4096,
        )
        if result and result.strip():
            cleaned = result.strip()
            # Safeguard: don't allow LLM to gut the content
            if len(cleaned) < 50 and len(text) > 200:
                log.warning(
                    f"LLM over-cleaned ({len(text)}→{len(cleaned)} chars), "
                    "keeping original"
                )
                return text
            log.info(f"LLM cleaned: {len(text)} -> {len(cleaned)} chars")
            return cleaned
        return text
    except Exception as e:
        log.warning(f"LLM extraction failed, using original: {e}")
        return text


def backfill_llm_clean_translations(db_path: str, label: str = ""):
    """Apply LLM cleaner to all translated_content in a database.

    Iterates articles, runs llm_extract_article on translated_content
    where available, and updates the DB.
    """
    import sqlite3

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT id, title, translated_content FROM articles "
        "WHERE translated_content IS NOT NULL AND translated_content != ''"
    ).fetchall()
    total = len(rows)
    print(f"[{label or db_path}] Found {total} articles with translations")

    fixed = 0
    skipped = 0
    for rid, title, trans in rows:
        cleaned = llm_extract_article(trans)
        if cleaned != trans:
            # Safeguard: if LLM removed almost everything and original
            # was substantial, keep the original to avoid data loss.
            if len(cleaned) < 50 and len(trans) > 200:
                log.warning(
                    f"LLM over-cleaned '{title[:50]}' "
                    f"({len(trans)}→{len(cleaned)} chars), keeping original"
                )
                skipped += 1
                continue
            conn.execute(
                "UPDATE articles SET translated_content = ? WHERE id = ?",
                (cleaned, rid),
            )
            conn.commit()
            fixed += 1
            reduction = len(trans) - len(cleaned)
            print(f"  ✓ {title[:50]}... ({len(trans)}→{len(cleaned)} chars, -{reduction})")
    print(f"[{label or db_path}] Cleaned {fixed}/{total} articles ({skipped} skipped by safeguard)")
    conn.close()


if __name__ == "__main__":
    import os

    # Load ALL env vars from llm.env (not just LLM_API_KEY)
    env_file = "/etc/news-monitor/llm.env"
    if os.path.exists(env_file):
        for line in open(env_file):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k] = v

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    data_dir = "/root/news-monitor/data"
    backfill_llm_clean_translations(f"{data_dir}/news.db", "news.db")
    backfill_llm_clean_translations(f"{data_dir}/aam.db", "aam.db")
