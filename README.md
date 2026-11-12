# tieba-mcp

只读的百度贴吧 MCP 服务，给 AI 提供“搜索帖子、看吧内帖子、读帖子楼层、查吧信息”的能力。

只做读取，不提供发帖、回复、点赞、关注、登录等写操作；不实现验证码破解。默认请求间隔 1.5 秒，
请遵守百度贴吧的用户协议与 robots 规则，不要高频抓取。

## 安装

```bash
pip install -r requirements.txt
```

`browser` 后端额外需要：

```bash
pip install playwright
# 使用系统 Chrome，无需下载 Chromium
```

## 配置

两种方式任选其一，环境变量优先级高于 JSON 文件。

### 方式一：config.json（推荐）

```bash
cp config.example.json config.json
```

```json
{
  "cookie": "BDUSS=你的BDUSS; STOKEN=可选的STOKEN",
  "backend": "http",
  "delay": 1.5,
  "timeout": 20,
  "max_items": 50,
  "debug_dump": ""
}
```

获取 Cookie：浏览器登录 `https://tieba.baidu.com/`，按 F12 → Application → Cookies →
`https://tieba.baidu.com` → 复制 `BDUSS`（通常再带上 `STOKEN`）。

### 方式二：.mcp.json 里直接写环境变量

```json
{
  "mcpServers": {
    "tieba": {
      "command": "python3",
      "args": ["/path/to/tieba-mcp/server.py"],
      "env": {
        "TIEBA_COOKIE": "BDUSS=你的BDUSS; STOKEN=可选的STOKEN",
        "TIEBA_DELAY": "1.5",
        "TIEBA_MAX_ITEMS": "50"
      }
    }
  }
}
```

也可以用 `TIEBA_CONFIG` 指向任意 JSON 配置文件：

```json
"env": { "TIEBA_CONFIG": "/path/to/tieba-mcp/config.json" }
```

### 配置项

| JSON 键 | 环境变量 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `cookie` | `TIEBA_COOKIE` | `""` | 完整 Cookie 字符串 |
| `bduss` | `TIEBA_BDUSS` | `""` | 只填 BDUSS 时自动拼成 `BDUSS=...` |
| `backend` | `TIEBA_BACKEND` | `http` | `http` 或 `browser` |
| `headless` | `TIEBA_HEADLESS` | `false` | browser 后端是否无头 |
| `profile_dir` | `TIEBA_PROFILE_DIR` | `""` | browser 持久化用户目录，可复用登录态 |
| `delay` | `TIEBA_DELAY` | `1.5` | 两次请求的最小间隔（秒） |
| `timeout` | `TIEBA_TIMEOUT` | `20` | 单次请求超时（秒） |
| `max_items` | `TIEBA_MAX_ITEMS` | `50` | 默认返回条数上限，最大 200 |
| `verify_wait` | `TIEBA_VERIFY_WAIT` | `120` | browser 有头模式下等待人工过验证的秒数 |
| `debug_dump` | `TIEBA_DEBUG_DUMP` | `""` | 导出 HTML 的目录或文件，排查解析问题 |
| `user_agent` | `TIEBA_USER_AGENT` | Chrome UA | 自定义 UA |
| `referer` | `TIEBA_REFERER` | tieba 首页 | 自定义 Referer |

## 工具

| 工具 | 作用 |
| --- | --- |
| `tieba_search(keyword, page=1, forum="", limit=0)` | 搜索帖子，可限定某个吧 |
| `tieba_home_threads(limit=0)` | 首页推荐流帖子、热门吧与热搜关键词 |
| `tieba_forum_threads(forum, page=1, limit=0)` | 吧内帖子列表 |
| `tieba_thread(thread, page=1, max_floors=0, include_comments=false)` | 读帖子标题与楼层，`thread` 支持 tid 或链接 |
| `tieba_forum_info(forum)` | 吧的关注数、帖子数、简介 |
| `tieba_diagnose()` | 自检配置与当前网络是否可用（先查 403/验证） |

所有工具返回统一 JSON：

```json
{ "ok": true, "tool": "tieba_thread", "data": { "...": "..." } }
```

失败时：

```json
{
  "ok": false,
  "tool": "tieba_thread",
  "error": {
    "code": "verification_required",
    "message": "贴吧返回了安全验证页，当前 IP 或未登录状态被风控",
    "hint": "在 config.json 或环境变量 TIEBA_COOKIE 中填入 ..."
  }
}
```

## 常见问题

**403 / 百度安全验证**

裸请求被百度风控。依次尝试：

1. 填 `cookie`（至少 `BDUSS`），然后调用 `tieba_diagnose` 确认；
2. 把 `backend` 改成 `browser`、`headless` 设为 `false`，首次运行会弹出 Chrome，
   手动完成滑块/登录后继续；配置 `profile_dir` 可复用登录态；
3. 仍然失败通常是账号或出口 IP 被限制，换网络或稍后再试。

**解析不到内容（parse_failure）**

贴吧页面结构可能变化。设置 `debug_dump` 为目录，重跑一次，把导出的 HTML 用于排查。
解析器优先读 `data-field` 里的 JSON，其次才用 CSS 选择器兜底，所以部分改版仍可用。

**browser 模式报缺少浏览器**

本机已有 Chrome 时直接用 `channel="chrome"`，不需要 `playwright install`。

## 开发

```bash
cd tieba-mcp
python3 -m pytest
```

测试使用固定 HTML fixture 和 `httpx.MockTransport`，不访问真实贴吧。