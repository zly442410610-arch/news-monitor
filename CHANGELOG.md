# Changelog

## v0.24.0 (2026-06-03)

### Added
- **AAM 面板扩展**：新增 12 个中文新闻源（参考消息、环球军事、澎湃等）、6 个 Google News 搜索词（空战/BVR/空空导弹等）
- **高超声速内容分流**：推进/发动机类高超声速文章留在新闻面板，武器/飞行器综述类高超声速内容进 AAM 面板
- **API 密钥安全**：从 systemd 服务文件迁移到独立的 `/etc/news-monitor/llm.env`，权限 600
- **VERSION 文件**：项目版本跟踪

### Fixed
- **LLM 批处理解析失败**：35 篇文章因批处理格式解析异常默认 llm=50，已逐个重新打分修复
- **误报清理**：删除关键词误匹配文章（NATO "mission creep"、生物燃料、涡轮疲劳、增材制造等 4 篇）
- **auth-proxy 端口冲突**：10100 端口被 aerospace-platform 占用，停用 auth-proxy 服务

### Changed
- **关键词重组**：`hypersonic_propulsion` 分组保留在新闻面板，AAM 仅保留 `hypersonic_weapons` 分组
- **过滤器提示更新**：新闻面板 `_FILTER_NEWS` 明确区分推进类高超声速（保留）与武器综述（排除）
- **日志配置**：dashboard 服务添加 `StandardOutput/Error` 日志重定向

## v0.23.0 (2026-05-30)

### Fixed
- CNKI 代理请求添加随机延时 (3-10s/篇)，防止被封 IP
- 切换 CNKI 代理到浙江图书馆 (erm.zjlib.cn/goto)

## v0.22.0 (2026-05-29)

### Fixed
- 翻译词汇表重复键问题：清理战术术语/测试评审术语/飞机型号/导弹型号等17+个重复条目
- 数据库中现有文章翻译重复问题：清理24篇文章中的翻译内容重复
- 9090端口固体超燃冲压发动机界面按钮无响应问题：添加缺失的sf_scramjet路由
- 8080端口无效内容：清理登录页/验证码页/错误页(403/404/500)等24篇无效内容

### Improved
- 增强无效内容检测：新增中文无效关键词过滤、内容长度检查、提前返回机制
- 扩展_JUNK_PATTERNS：新增首页/关于我们/联系我们等中文导航菜单模式
- 数据库清理备份：每次清理前自动备份数据库

## # Changelog

## v0.17.0 (2026-05-25)

### Added
- **相关报道/相似文章类型标签**：标题前显示"论文/专利/新闻"彩色标签
- **多语言翻译**：韩文、日文、俄文自动检测并翻译为中文，`detect_language()` 新增韩/日/俄字符集识别
- **AI 问答**：文章详情页新增 AI 问答悬浮按钮，支持对文章内容提问
- **文章管理**：支持收藏（星标）、固定/跳转事件分组
- **月报自动预生成**：Dashboard 启动时自动生成当月月报
- **左侧导航面板**：文章详情页新增左侧面板，支持筛选/搜索/事件分组导航

### Fixed
- **韩文专利全文乱码**：content fetch 编码修复，优先检测 HTML `<meta charset>` 而非 chardet（对韩文检测不准），已重新采集并翻译 2 篇 KR 专利
- **翻译提示语**：`CONTENT_TRANSLATION_PROMPT` 从"from English"改为"from any foreign language"，确保韩/日/俄等语言正确翻译
- **相关文章手机布局**：`related-item` 改为纵向排列，标题左对齐 + 自动换行，来源信息在标题下方

### Changed
- **文章卡片重新设计**：更清晰的信息层级，支持收藏操作
- **导航重构**：首页改为左右分栏布局

## v0.16.0 (2026-05-24)

- 新增相似文章推荐：文章详情页底部展示关键词重叠最多的 8 篇相关文章

## v0.15.0 (2026-05-24)

- 新增关键词趋势页面 /trends，SVG 柱状图展示关键词每日文章数变化
- 新增 AI 问答页面 /ask，基于已采集文章做 RAG 问答，引用来源可追溯
- 新增重复文章智能合并：AAM 主题启用事件分组，文章详情页显示相关报道
- 改进标题归一化，增加更多前缀清洗模式，提高去重准确率

## v0.14.0 (2026-05-24)

- 补充 NEEDS_PROXY_DOMAINS 代理域名列表，Clash 翻墙可用
- 恢复 8 个 GFW 被墙源（Breaking Defense、Atlantic Council 等），走 Clash 代理采集
- 清理真正失效的源（Janes、TASS、Defence Connect、Defence Technology 等 11 个 404/403 源）

## v0.13.0 (2026-05-24)

- 文章正文展示改进：分段 `<p>` 渲染，移除 10000 字符截断
- 新增缺失全文页面 /missing-content，支持单条和批量补抓
- 新增关键词管理页面 /keywords，支持添加/删除关键词和分组
- DB 关键词与 theme.py 默认关键词自动合并，无需重启
- 新增 POST 路由模式支持表单提交

## v0.12.0 (2026-05-24)

- 导航栏月度报告左对齐，与全部/论文等链接同级排列
- 移除未读功能（无账户系统，共享已读状态无实际意义）
- 统计栏精简为总计/最近24h

## v0.11.0 (2026-05-24)

### Fixed
- Google Patents 编码乱码 — 强制 UTF-8 解码，修复 22 篇已采集专利文章
- 专利文本排版噪声 — 新增 `_clean_google_patent_text()` 清洗函数，去除分类号（G06/CN/…）、引用文献列表、法律状态事件等尾部元数据
- 文章详情页可读性 — 增大正文字号（1.05rem）、行高（1.9）、对比度

### Changed
- 文章详情有翻译时仅显示中文，不再同时展示英文原文

## v0.10.0 (2026-05-22)

### Added
- Google Patents 官方 API (`/xhr/query`) 采集引擎 — 基于会话认证 (NID cookie) 绕过 GFW 限制
- 专利主题分组查询 (sfrj: 5组 / aam: 5组)，每组 30 条结果，按最新排序
- 专利关键词过滤 + LLM 语义过滤 + 低相关度文章自动剔除
- 专利回填脚本 (backfill_patents.py)：5 月份采集 206 篇 news 专利 + 163 篇 aam 专利，清洗后保留 34 + 13 篇相关专利
- 专利自动翻译为中文（与 RSS 管道一致）
- 新增统一 LLM 客户端模块 (llm_client.py)，支持请求超时和重试

### Fixed
- 面板点击专利文章卡死 — 改用 ThreadingHTTPServer (原 HTTPServer 单线程)，专利文章跳过 live fetch
- 首页专利标题显示英文 — 回填翻译后正确显示中文
- 专利作者单位缺失 (affiliation 被拼接到 author 字段) — 拆分为 inventor + assignee
- AAM 专利 cron 路径错误 (指向不存在的目录) — 修正到 news-monitor
- FTS5 搜索含特殊字符 (`+-*()~^`) 崩溃 — 正则剥离 + 移除 AND/OR/NOT
- str.format() 花括号 KeyError — 标题中 `{like_this}` 通过 `.replace` 转义
- as_completed TimeoutError 未捕获导致 poll_once 崩溃
- main.py 回填命令缺少 `contains_chinese` 导入引发 NameError
- Telegram Markdown 未转义导致 400 错误 — 新增 `_esc_md()` 转义 `_*`[
- Email HTML 模板未转义用户字段 — 全面使用 `html.escape()`
- 日志中代理密码明文打印 — 新增 `_redact_proxy()` 脱敏
- 时区映射全为 +0000 — `_TZ_MAP` 修正 EDT/BST/CST 等正确偏移量
- `_GNEWS_LOCK` 为布尔值而非 threading.Lock — 改为 threading.Lock()
- LLM 请求无超时 — `_API_TIMEOUT = 60`

### Changed
- 采集时间调整为统一每日排程：3:00 News RSS → 3:30 AAM RSS → 4:00 News 专利 → 4:30 AAM 专利
- cron 日志轮转移至周日 2:00
- `TRANSLATE_TO_CHINESE` 从硬编码改为环境变量配置

### Optimized
- Google Patents API 会话复用：首次访问 google.com 获取 NID cookie，避免 503 限流
- 专利查重使用 `seen_urls` set 减少数据库查询
- 批量查询使用 OR 合并减少 API 调用次数

## v0.9.1 (2026-05-21)

### Changed
- 全面重构导航布局，搜索框独立一行，移除导出功能
- 恢复翻译功能，接入 DeepSeek API

### Fixed
- 修复跨来源文章去重逻辑
- 修复日期格式一致性

### Added
- 新增作者单位自动回填
- 新增搜索框支持全文检索

### Removed
- 移除无法访问的 Google News 链接

## v0.9.0 (2026-05-20)

### Optimized
- Poll 轮询 DB 查询减少 76%：recent 标题查重移出循环避免 N+1、批量提交替代逐条 fsync
- 缺失索引：`(published, relevance)`、`(fetched_at)`、`(event_group, published)` 加速排序和过滤
- `get_articles_by_month` 改用范围查询代替 strftime 包裹，利用 `published` 索引
- Dashboard 首页合并 4 次 COUNT 查询为 1 次 SQL，`all_count` 复用 `total` 变量
- CSS 生成按主题缓存，避免每次页面渲染重新拼接 240 行 CSS
- `format_time_cn` 先试 `fromisoformat`（覆盖 90%+）再试 7 个 strptime 格式

### Fixed
- 文章列表页"查看原文"链接缺少 `html.escape()` 导致 XSS 风险
- Dashboard `_handle_search` 页码参数非数字时崩溃
- 24h 统计卡在过滤状态下显示过滤后数量而非总数量
- notifier.py `fmt_msg`/`fmt_html` 字典直接取值可能引发 KeyError
- 文章详情页重复的 `from theme import AAM, NEWS` 移入模块顶部
- 删除 duplicate `_safe_href` 函数定义

## v0.8.0 (2026-05-20)

### Added
- 专利监测：新增 FPO (FreePatentsOnline) 专利 RSS 源，文章自动归类为"专利"类型
- 面板新增"专利"筛选标签和紫色专利标签样式
- 文章详情页空内容时回退显示 RSS 摘要

### Fixed
- 数据库损坏导致文章弹窗空白 — 重建 aam.db 和 news.db
- translated_content 列索引硬编码问题 — 改用列名访问，修复 aam 主题翻译不显示
- fetch_article_content 不跟随 302 跳转 — 改用 allow_redirects=True
- 面板 JS 导航高亮缺少 patent 类型判断

## v0.5.0 (2026-05-19)

### Added
- 自建 RSSHub 实例 (Docker, localhost:1200)
- 切换 21 个 RSSHub 源至自建实例，延迟更低更稳定
- 新增 15+ RSS 源：Springer 系列期刊、Combustion Sci & Tech、Propulsion & Power Research、
  ESA Space Engineering、Lockheed Martin、Shephard Media、Janes、Breaking Defense、
  National Defense Mag、The Defense Post、TASS Defense、SpaceWatch Global 等
- 新增中文源：中国新闻网、参考消息、知乎想法日报、知乎每周精选、环球网军事、
  BBC中文、央视新闻
- 新增学术源：AIAA J. Spacecraft & Rockets、Chinese J. Aeronautics、Defence Technology
- Hacker News (tech/engineering discussions)

### Removed
- 清理 16 个不可用的 RSSHub 源（知乎话题、新浪/凤凰/澎湃/网易/腾讯/搜狐军事等）

### Fixed
- Dashboard theme-badge 颜色从硬编码修复为使用 config.COLOR_PRIMARY 变量

## v0.2.0 (2026-05-18)

### Added
- arXiv academic paper sources: 3 keyword-based Atom feeds for solid rocket, ramjet/scramjet, and hypersonic propulsion papers
- CNKI Chinese academic journal sources: 5 core journals (推进技术, 固体火箭技术, 宇航学报, 航空动力学报, 火箭推进)
- Chinese news sources: 联合早报 中国/国际 feeds
- Article detail page: click title to view full translated content with collapsible original summary
- Patent search function in collector.py for Google Patents
- 4 new international RSS sources (European Spaceflight, JAXA, Universe Today, Space.com)
- 3 additional technical/defense sources (Ars Technica, The War Zone, Interesting Engineering)
- Chinese time format on article cards (年月日 时分秒)
- Expanded keyword list from 66 to 77 terms
- Relaxed LLM filter to accept missile/hypersonic propulsion content

### Changed
- Dashboard: dark theme redesign with stats bar, filter tabs, source type classification
- Dashboard: title links now point to article detail page instead of original URL
- POLL_INTERVAL changed from 120min to 1440min (daily), cron set for 9am
- Database schema includes translated fields (translated_title, translated_summary)

### Fixed
- LLM filter handling of thinking blocks (Anthropic API)
- Translation parsing for flexible response headers
- Dashboard column index off-by-one for translated fields
- Date format to Chinese locale

## v0.1.0 (2026-05-16)

### Added
- Initial aerospace news monitoring system
- International RSS sources (Defense News, Spaceflight Now, NASA, etc.)
- Two-tier filtering: keyword matching + LLM semantic filter (Claude Sonnet)
- English-to-Chinese translation via Anthropic API
- SQLite database with WAL mode
- Web dashboard with dark theme (BaseHTTPRequestHandler)
- Telegram and email notification support
- Weekly briefing generator
- CLI entry point (poll, serve, daemon, briefing, stats)
- Domestic collector script for Chinese news sources
