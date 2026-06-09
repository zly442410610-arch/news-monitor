"""
Shared boilerplate/content filter for article text.
Used by both monitor.py (collection time) and dashboard/handler.py (display time).
"""
import re

# English footer/advertisement markers (line starts with or exact match)
FOOTER_MARKERS = [
    "Most Read", "Related Posts", "Posted in", "Tags:", "Share this:",
    "Free Satnews", "Subscribe", "Navigation", "Manage Profile",
    "in your inbox", "newsletter",
    "View All in", "Submenu", "All Rights Reserved", "All rights reserved",
    "Advertisement", "Sponsored", "Recommended",
    "Trending Now", "You May Also Like", "Read More",
    "© ", "Copyright",
    "Light theme", "Dark theme", "Vision problems",
    "Video Player is loading", "Loaded:", "简介：", "简介:",
    # Additional boilerplate
    "Manage Preferences", "Deny Non-Essential", "Non-Essential",
    "Forgot Password", "Not a subscriber", "not a registered user",
    "Get a Free Trial", "Subscriber-only content",
    "All Rights Reserved",
    # Jina fetch metadata markers
    "Title: ", "URL Source: ", "Published Time: ", "Markdown Content:",
]

# Chinese boilerplate markers (substring match)
CHINESE_MARKERS = [
    "版权所有", "订阅", "首页", "所有频道", "新闻直达",
    "保留所有权利", "相关新闻", "推荐文章",
    "归类于", "报道范围", "侧边栏", "标签", "分类：",
    "相关视频", "猜你喜欢", "热门视频", "视频信息",
    "视频加载", "播放器", "音量", "拖动",
    "退出", "表情", "分享到微博", "发布",
    "条评论", "人参与", "我有话说", "举报",
    "复制视频网址", "拷贝调试信息",
    "电话客服", "官方微博", "官方交流群",
    "频道：", "频道:", "搜索", "新浪视频",
    "最热评论", "最新评论", "登录", "注册",
    "投降是唯一出路", "查看更多精彩评论",
    # Additional Chinese boilerplate
    "低视力无障碍", "无障碍功能", "空标题", "主要导航", "主导航",
    "在新窗口中打开", "打开外部网站", "打开网站",
    "隐私政策", "非必需", "管理偏好",
    "本网站使用", "本网站利用",
    # WeChat article UI elements (RSS/exported content)
    "在小说阅读器读本章", "去阅读", "在小说阅读器中沉浸阅读",
    "觉得不错，请点在看", "分享一篇文章", "原创",
    "喜欢此内容的人还喜欢",
    # WeChat article footer
    "以上消息均来自", "本文来源：",
    # WeChat footer promos & disclaimers
    "扫码加入粉丝群", "免责声明：",
    "无法核实真实出处", "保护作者知识产权",
    "最终解释权", "相关争议",
    # WeChat in-content ads
    "中英文互译及英文润色服务", "扫描二维码", "查看下载全文",
    "点击查看详情",
]


# Section heading patterns that introduce unrelated content (e.g., "Related
# Articles" sidebars). Matching heading and all non-heading lines after it
# are removed (until the next heading or end of content).
_SECTION_REMOVE_PATTERNS = re.compile(
    r'^#{2,3}\s+(?:'
    r'Congress Updates|The Force Multipliers|'
    r'Related\s+(?:News|Articles|Posts|Content|Reading)|'
    r'Recommended(?:\s+(?:for\s+you|articles|news|reading))?|'
    r'You May Also Like|Trending Now|Most Read|Must Read|'
    r"Editor'?s\s+Picks|More\s+(?:News|Articles|Updates|from)|"
    r'Latest\s+(?:News|Articles|Updates)|'
    r'Sponsored\s+(?:Content|Articles?)'
    r')',
    re.IGNORECASE,
)


def _remove_related_sections(text: str) -> str:
    """Remove known unrelated-content sections from the text.

    Scans for heading lines matching patterns like "### Congress Updates"
    and removes all lines from that heading to the next heading or EOF.
    """
    lines = text.split("\n")
    result = []
    skip = False
    for line in lines:
        s = line.strip()
        if not skip and _SECTION_REMOVE_PATTERNS.match(s):
            skip = True
            continue
        if skip:
            if s.startswith("#"):
                skip = False
                # The heading that stopped the skip might itself be a
                # section header to remove — check and re-skip if so.
                if _SECTION_REMOVE_PATTERNS.match(s):
                    skip = True
                    continue
                # Fall through to include this heading
            else:
                continue
        result.append(line)
    return "\n".join(result)


def _remove_wechat_header(text: str) -> str:
    """Remove WeChat article UI header (author, source, read prompts).

    WeChat-exported articles have a consistent header pattern:
      [title]
      原创  (optional)
      [author name(s)]
      [source name]
      在小说阅读器读本章
      去阅读
      在小说阅读器中沉浸阅读
      [real content]

    Detects the WeChat UI marker ("原创" or "在小说阅读器读本章"
    etc.) within the first 25 lines, backtracks to find the start
    of the header, then removes everything until real content.
    """
    lines = text.split("\n")
    if len(lines) < 5:
        return text

    # Find a WeChat UI marker within first 25 lines
    wx_markers = {"在小说阅读器读本章", "去阅读", "在小说阅读器中沉浸阅读", "原创"}
    header_start = -1
    for i, line in enumerate(lines[:25]):
        if line.strip() in wx_markers:
            header_start = i
            break

    if header_start == -1:
        return text

    # Backtrack to find the true start of the header. If the marker is not
    # "原创", the lines between the marker and the title are short CJK lines
    # (author name, source name). Include them in the removal.
    for j in range(header_start - 1, -1, -1):
        s = lines[j].strip()
        # Stop at: empty line, a line that looks like heading, or a long line
        if not s or s.startswith("#") or s.startswith("="):
            header_start = j + 1
            break
        # Include short lines (<30 chars pure CJK, or <50 with mixed)
        is_short_cjk = len(s) < 30 and bool(re.search(r'[一-鿿]', s))
        is_short_mixed = len(s) < 50 and len(s) >= 30
        if is_short_cjk or is_short_mixed:
            header_start = j
        else:
            break

    # Scan forward from header_start to find the first real content line
    content_start = header_start
    for i in range(header_start, len(lines)):
        s = lines[i].strip()
        # Real content signals:
        # - Line starts with 【 (Chinese news bracket)
        # - Line starts with # (markdown heading)
        # - Line is a long CJK sentence (>40 chars)
        # - Line is a long mixed sentence (>80 chars)
        if s.startswith("【") or s.startswith("#"):
            content_start = i
            break
        if len(s) > 40 and bool(re.search(r'[一-鿿]', s)):
            content_start = i
            break
        if len(s) > 80:
            content_start = i
            break

    result = lines[:header_start] + lines[content_start:]
    return "\n".join(result)


def filter_boilerplate(text: str) -> str:
    """Remove boilerplate/advertisement/navigation lines from article text.

    Line-by-line filter targeting common patterns found in Jina-fetched
    markdown content: navigation menus, ads, share buttons, video player
    UI, related article lists, etc.
    """
    if not text:
        return ""

    # Pre-processing: remove known unrelated-content sections
    text = _remove_related_sections(text)
    # Remove WeChat article UI header (author/source/read prompts)
    text = _remove_wechat_header(text)

    lines = text.split("\n")
    filtered = []
    for line in lines:
        s = line.strip()
        # Keep empty lines (preserve paragraph spacing)
        if not s:
            filtered.append(line)
            continue

        # Long CJK lines are main content, not boilerplate — skip substring
        # marker checks that could false-positive on footer text like "标签"
        # appearing at the end of a single-paragraph article.
        _is_long_cjk = len(s) > 100 and bool(re.search(r'[一-鿿]', s))

        # English footer markers (startswith or exact match)
        if not _is_long_cjk and any(s.startswith(m) or s == m for m in FOOTER_MARKERS):
            continue

        # Chinese boilerplate markers (substring)
        if not _is_long_cjk and any(m in s for m in CHINESE_MARKERS):
            continue

        # Multi-word English markers (substring match, for lines where the
        # marker doesn't appear at the start of the line due to preceding
        # UI elements like "##### " heading prefixes or "Accept Deny").
        _PAYLOAD_MARKERS_IN = (
            "Not a subscriber", "not a registered user",
            "Subscriber-only content", "Subscriber-only",
            "Deny Non-Essential", "Manage Preferences", "Non-Essential",
            "Accept Deny", "Forgot Password",
        )
        if any(m in s for m in _PAYLOAD_MARKERS_IN):
            continue

        # "Skip to" navigation
        if s.startswith("Skip to") or s.startswith("*   Skip"):
            continue

        # Standalone URLs (separate navigation links)
        if re.match(r'^https?://\S+$', s):
            continue

        # Very short lines without CJK (likely navigation debris).
        # CJK punctuation (【】《》（）等) alone is still boilerplate;
        # but keep lines that are ALL CJK punct + chars.
        if len(s) < 15 and not re.search(r'[一-鿿　-〿＀-￯]', s):
            continue

        # Markdown list items with links — navigation menus, category lists
        # e.g. '* [text](url)', '- [text](url)', '* * [text](url)'
        if re.match(r'^[\*\-\+]\s+(\*\s+)?\[.+\]\(.+\)$', s):
            continue

        # Numbered breadcrumb items: '1. [text](url)'
        if re.match(r'^\d+\.\s+\[.+\]\(.+\)$', s):
            continue

        # Numbered plain-text breadcrumb: '3. Page Title' (short, after numbered links)
        if re.match(r'^\d+\.\s+\S', s) and len(s) < 80:
            continue

        # Standalone markdown links: '[text](url)'
        if re.match(r'^\[.+\]\(.+\)$', s):
            continue

        # Social media icon lines: '* []' or '* [](...)'
        if re.match(r'^[\*\-\+]\s+\[\]', s):
            continue

        # Empty markdown links: '[](url)'
        if re.match(r'^\[\]\(.+\)$', s):
            continue

        # Markdown images
        if re.match(r'^!\[.+\]\(.+\)$', s):
            continue

        # Lines that are just '#' characters (empty/separator headings)
        if re.match(r'^#+$', s):
            continue

        # Stock ticker lines: '$44.34↑0.0451.66↑0.06'
        if re.match(r'^\$[\d.,↑↓\-\+]+$', s):
            continue

        # Age / audience restriction boilerplate
        if re.match(r'^This (resource|content|site|website).*intended for.*(age|years?|18|21)', s, re.IGNORECASE):
            continue

        # Bold boilerplate: '**Information agency...**'
        if re.match(r'^\*\*.+\*\*$', s) and any(w in s.lower() for w in ['agency', 'information', 'media', 'news', 'resource', 'subject', 'identifier', 'rights']):
            continue

        # Lines containing only currency/stock data with symbols
        if re.match(r'^[\d\s,.↑↓\-\+€$£¥%°]+$', s) and len(s) < 30:
            continue

        # Video timestamp lines: '00:00 / 00:00'
        if re.match(r'^[\d: ]+_?/_?[\d: ]+$', s):
            continue

        # Markdown image with trailing timestamp: '* ![Image N](url)_00:00:22_'
        if re.match(r'^[\*\-\+]\s+!\[.+\]\(.+\)_\d{2}:\d{2}', s):
            continue

        # Sina hot-video list: '1. 1._9,440_[text](url)'
        if re.match(r'^\d+\.\s+\d+\._\d[\d,]*_\[', s):
            continue

        # Comment/forum one-liners: '10秒前[举报]'
        if re.match(r'^\d+秒前', s) or re.match(r'^\d+分钟前', s):
            continue

        # User info lines with [location]: '[name](url)[location]'
        if re.match(r'^\[.+\]\(.+\)\[.+\]$', s):
            continue

        # Short UI action lines
        if s in ("退出", "表情", "发布", "搜索", "频道"):
            continue

        # Comment UI links: '* [@user](http...'
        if re.match(r'^\* .*\[@?.+\]\(http', s):
            continue

        # Version/debug lines: '* V11220.210521.03'
        if re.match(r'^\*\s+V\d+', s):
            continue

        # Short section headers with underscores: '_频道_'
        if re.match(r'^_\S+_$', s) and len(s) < 12:
            continue

        # Heading-level markdown links: '#### [Title](url)'
        if re.match(r'^#{1,4}\s+\[.+\]\(.+\)$', s):
            continue

        # Markdown boilerplate section headings
        if re.match(r'^#+\s+(Read more|Latest News|Related|More|Recommended|Similar)', s, re.IGNORECASE):
            continue

        # Share button lines
        if re.match(r'^(Share|分享)[:：]?\s*(Facebook|Twitter|LinkedIn|微博|微信)?$', s):
            continue

        # Social share/ tag lines starting with [text](http
        if re.match(r'^\[(Facebook|Twitter|LinkedIn|X|微博|微信)\]\(http', s):
            continue

        # Tag lines: '[tag1](url)[tag2](url)...'
        if re.match(r'^\[.+\]\(http.+\)?\[', s):
            continue

        # Category metadata: '[Category](url)| Date'
        if re.match(r'^\[.+\]\(.+\)\|\s*\S', s):
            continue

        # ── New rules for paywall / newsletter / site boilerplate ──

        # "Opens in a new window" / "Opens an external website"
        if re.search(r'opens in a new window|opens an external website', s, re.IGNORECASE):
            continue

        # Cookie consent lines mentioning cookies + privacy/analytics
        if re.search(r'cookies.*(?:privacy|analytics|personalization|essential)', s, re.IGNORECASE):
            continue

        # Login/password form lines
        if re.search(r'Email or Username', s) or re.search(r'Forgot Password', s):
            continue

        # Contact/support lines
        if re.search(r'please contact us at|call us at', s, re.IGNORECASE):
            continue

        # Newsletter / free signup promos
        if re.search(r'(?:sign up for our|free e-?letters?|weekly digest)', s, re.IGNORECASE):
            continue

        # Tagline / company boilerplate: 'News & Technology for the Global...'
        if re.search(r'News & Technology for the', s):
            continue

        # Category tag lines that are just two category names separated by /
        if re.match(r'^[A-Z][a-zA-Z\s]+/\s*[A-Z][a-zA-Z\s]+$', s) and 15 < len(s) < 60:
            continue

        # "About <Company>" lines
        if re.match(r'^About\s+[A-Z]', s):
            continue

        # Embedded video player UI: 'Loaded: 0%', 'Volume', etc.
        if re.match(r'^Loaded:\s+\d+%', s) or re.match(r'^Volume\s+\d+%', s):
            continue

        # Repeated "Access Intelligence" company name lines
        if re.search(r'Access Intelligence', s) and re.search(r'All Rights? Reserved', s, re.IGNORECASE):
            continue

        # Year-prefixed copyright lines: "2026 [Company](url) - All Rights Reserved"
        if re.match(r'^\d{4}\s+\[', s) and re.search(r'Reserved', s, re.IGNORECASE):
            continue

        # Chinese author / editor / source attribution lines at article footer
        if re.match(r'^(?:作者|来源|编辑|责编|责任编辑|编译|审核|监制|策划|撰文|摄影|制图)[：:]\s*\S', s):
            continue

        # Repeated source name (e.g. "国防科技要闻" appearing as a standalone line)
        if re.match(r'^国防科技要闻$', s):
            continue

        # Newsletter tagline promoting subscription: "Trends, best practices..."
        if re.match(r'^Trends, best practices', s):
            continue

        # Italicized publication tagline: "_PubName_ tracks/delivers/provides..."
        if re.match(r'^_.+_\s+(?:tracks|delivers|provides|offers|brings)', s, re.IGNORECASE):
            continue

        # Image alt-text with markdown image in navigation context: '* ![...](...)'
        if re.match(r'^[\*\-\+]\s+!\[(?:图片\d*|image\d*|Picture|Thumbnail)', s):
            continue

        # ── Section-level removal of known unrelated-content sections ──
        # Detect heading lines like "### Congress Updates" that start a section
        # of unrelated article teasers. Remove this line and all following
        # non-heading lines until the next heading or end of content.

        filtered.append(line)

    return "\n".join(filtered)
