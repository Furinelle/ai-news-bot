# AI News Bot — VPS 每日科技/AI日报

每日科技/AI日报服务。抓取 RSS、Hacker News、GitHub Trending，并结合你的 GitHub star 图谱做个性化仓库推荐，去重排序后交给 OpenAI-compatible LLM 生成结构化中文日报。项目既保留 AstrBot 插件入口，也提供可直接运行在 VPS 上的 CLI + systemd timer：每天生成日报、发布到 Rin 博客、保存本地 Markdown、上传 Cloudflare R2，并通过 Scripting Remote Push 推送博客链接到 iPhone。

## 功能

- VPS one-shot：`python -m ai_news_bot.main --send`
- 每日定时：systemd timer 默认每天 `08:00` 运行
- 日报归档：保存 `reports/YYYY-MM-DD.md`、`reports/YYYY-MM-DD.html` 和 latest 副本
- R2 上传：使用 Cloudflare R2 S3-compatible API 上传 Markdown 与 HTML 日报
- 博客发布：登录 Rin 管理 API，按日期幂等发布公开文章
- iPhone 通知：通过 Scripting Remote Push 发送通知，正文和点击动作均使用博客文章链接
- `/news` 命令：即时生成并分段发送当日科技/AI日报
- **⭐ 你可能感兴趣**：根据 star 列表建立兴趣画像，用 GitHub Search 找未必上 Trending、但有一技之长的仓库（过滤已 star / fork / 合集向仓库），写入日报第四节
- 多源采集：TechCrunch AI、The Verge、Ars Technica、MIT Technology Review、VentureBeat AI、Wired、OpenAI Blog、Google AI Blog、GitHub Blog、Hacker News、GitHub Trending
- URL 和标题去重，SQLite 记录已推送链接，减少重复内容
- LLM 生成中文摘要，格式固定四节：科技热点 / AI动态 / GitHub Trending / 你可能感兴趣（前三节各最多 15 条，兴趣节最多 8 条）
- 每条附来源媒体名，GitHub Trending 附仓库链接
- 无 LLM 时自动回退为 Markdown 原文模式

## VPS 快速部署

```bash
cd /opt
git clone https://github.com/Furinelle/ai-news-bot.git
cd /opt/ai-news-bot
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp config.example.json config.json
cp sources.example.json sources.json
mkdir -p data reports
```

把密钥写到 `/etc/ai-news-bot.env`：

```env
LLM_API_KEY=replace-with-your-llm-api-key
SCRIPTING_PUSH_API_KEY=replace-with-your-scripting-remote-push-key
CLOUDFLARE_ACCOUNT_ID=replace-with-your-cloudflare-account-id
R2_ACCESS_KEY_ID=replace-with-your-r2-access-key-id
R2_SECRET_ACCESS_KEY=replace-with-your-r2-secret-access-key
BLOG_ADMIN_USERNAME=replace-with-your-rin-admin-username
BLOG_ADMIN_PASSWORD=replace-with-your-rin-admin-password
```

R2 通过官方 S3-compatible endpoint 工作，默认由 `CLOUDFLARE_ACCOUNT_ID` 拼出：

```text
https://<ACCOUNT_ID>.r2.cloudflarestorage.com
```

编辑 `config.json`：

- `llm.base_url` / `llm.model`：换成你的 OpenAI-compatible 模型
- `r2.bucket`：换成真实 bucket
- `r2.public_base_url`：可选。填公开域名时使用固定公开 URL；留空时自动生成 7 天有效的 R2 presigned URL，bucket 可保持私有
- `r2.presigned_url_expires_seconds`：私有 R2 点击链接有效期，默认 `604800` 秒
- `scripting_push.enabled`：保持 `true`
- `blog.enabled`：启用 Rin 博客发布
- `blog.base_url`：Rin 博客根地址；远程推送会直接使用生成的 `/feed/daily-news-YYYY-MM-DD` 链接

本地 dry-run：

```bash
set -a
. /etc/ai-news-bot.env
set +a
python -m ai_news_bot.main --config config.json --sources sources.json --dry-run --no-llm
```

完整运行一次：

```bash
python -m ai_news_bot.main --config config.json --sources sources.json --send
```

安装 systemd：

```bash
cp deploy/systemd/ai-news-bot.service /etc/systemd/system/ai-news-bot.service
cp deploy/systemd/ai-news-bot.timer /etc/systemd/system/ai-news-bot.timer
systemctl daemon-reload
systemctl enable --now ai-news-bot.timer
```

## AstrBot 安装

在 AstrBot 插件管理界面，填入仓库地址安装：

```
https://github.com/Furinelle/ai-news-bot
```

## AstrBot 配置

插件安装后在 AstrBot 仪表盘的插件配置页面配置以下项目：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `provider_id` | 用于生成日报的 LLM 模型提供商 | （必填） |
| `max_report_items` | 送入 LLM 的最大候选条目数 | `45` |
| `schedule_time` | 每日定时推送时间，格式 `HH:MM`（Asia/Shanghai） | 空 |
| `schedule_targets` | 后台配置的默认推送目标；微信内订阅指令会优先于此配置 | 空 |

## 使用

在任意对话中发送：

```
/news
```

插件会先回复"生成中"提示，随后将日报按四节（科技热点 / AI动态 / GitHub Trending / 你可能感兴趣）分段发送；VPS 生成的 HTML 阅读页会把各节放在同一个页面的标签页中。

查看指令列表：

```
/news_help
```

清除已推送新闻缓存：

```
/news_clear_cache
```

该指令只清除新闻去重记录，不会删除订阅会话、定时时间或新闻源配置。

查看当前会话 ID，用于配置定时推送：

```
/newsid
```

在当前微信私聊或群聊订阅每日推送：

```
/news_subscribe 08:30
```

取消当前会话的每日推送：

```
/news_unsubscribe
```

查看当前定时推送状态：

```
/news_schedule
```

通过微信指令设置过订阅后，插件会优先使用指令保存的会话列表；后台 `schedule_targets` 只在没有使用过微信订阅指令时作为默认值。

## 新闻源

默认采集以下来源，可编辑插件数据目录下的 `sources.json` 自定义：

| 来源 | 分类 |
|------|------|
| TechCrunch AI | AI动态 |
| OpenAI Blog | AI动态 |
| Google AI Blog | AI动态 |
| Google DeepMind | AI动态 |
| MIT Technology Review | AI动态 |
| VentureBeat AI | AI动态 |
| AWS Machine Learning Blog | AI动态 |
| TensorFeed AI | AI动态 |
| The Verge | 科技热点 |
| Ars Technica | 科技热点 |
| Wired | 科技热点 |
| GitHub Blog | 科技热点 |
| NVIDIA Developer Blog | 科技热点 |
| Spaceflight News API | 科技热点 |
| Hacker News | 科技热点 |
| GitHub Trending | GitHub Trending |
| GitHub 兴趣推荐（star 画像 + Search） | 你可能感兴趣 |

### `github_interest` 配置（`sources.json`）

```json
"github_interest": {
  "enabled": true,
  "username": "Furinelle",
  "token_env": "GITHUB_TOKEN",
  "limit": 8,
  "min_stars": 80,
  "max_stars": 20000,
  "pushed_within_days": 150,
  "profile_cache_path": "data/star_profile.json",
  "profile_ttl_hours": 24
}
```

- 需要可读 star 列表：配置 `GITHUB_TOKEN`，或本机已登录 `gh`
- 候选不必上 Trending；会排除已 star / fork / 合集向仓库

## 事实安全

模型提示词已要求：

- 只使用候选新闻中的事实，不得编造公司名、数字、日期、融资金额或发布内容
- 普通新闻只标注来源媒体名，不输出完整链接
- GitHub Trending 每条附仓库链接
- 重大单来源新闻标注"未交叉验证"

这不能替代人工核查。涉及监管、融资、裁员、并购、安全事故等重大内容，建议在转发前人工确认。
