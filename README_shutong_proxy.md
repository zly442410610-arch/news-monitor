# 书童代理 CNKI 访问配置

## 概述

书童图书馆 (http://3.shutong2.com) 是一个聚合数据库代理服务，通过 
上海图书馆 VPN (wvpn.sjlib.cn) 中转访问 CNKI。本脚本用于导入浏览器导出的
Cookie，使 monitor 系统能通过书童代理抓取 CNKI 全文。

## 手动操作步骤

### 1. 用浏览器登录书童

1. 打开 http://3.shutong2.com/
2. 点击"登录"，输入账号：
   - 用户名：095195923
   - 密码：391234
3. 输入验证码登录

### 2. 访问 CNKI 并完成滑块验证

1. 登录后自动跳转到中文数据库页面
2. 点击 **知网入口3(推荐)**（api33.php）
3. 在弹出的 CNKI 页面中：
   - 点击 **机构登录**（如未自动登录）
   - 完成滑块验证（向右滑动）
4. 验证成功后应在页面顶部看到"欢迎来自 书童图书馆"
5. 此时可在 CNKI 中搜索任意内容确认可用

### 3. 导出 Cookie

用浏览器扩展导出 Cookie（Netscape 格式）：

**Chrome:** 安装 "Get cookies.txt" 或 "EditThisCookie" 扩展
- 点击扩展图标 → 导出为 Netscape 格式
- 保存为 `/tmp/cookies_shutong.txt`

**Firefox:** 安装 "cookies.txt" 扩展
- 点击扩展 → Export → 保存文件

### 4. 运行 Cookie 导入脚本

```bash
cd /root/news-monitor
python3 import_shutong_cookies.py /tmp/cookies_shutong.txt
```

脚本会自动：
- 解析 Netscape 格式的 cookie 文件
- 提取书童会话 cookie 和 wvpn.sjlib.cn cookie
- 测试代理是否可用
- 保存配置到 `.shutong_cookies.json`

### 5. 运行回填脚本

```bash
# 测试单篇文章
python3 backfill_cnki_fulltext.py --shutong --news-only

# 完整回填（使用书童代理）
python3 backfill_cnki_fulltext.py --shutong
```

## Cookie 有效期

- 书童 VIP 会员剩余天数会在页面上显示（当前 7 天）
- Cookie 过期后需重新登录导出
- 建议每周重新导出一轮
