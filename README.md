# AI News Bot — VPS 每周科技/AI周报

每周科技/AI周报服务。抓取 RSS、Hacker News、GitHub Trending，并结合你的 GitHub star 图谱做个性化仓库推荐，去重排序后交给 OpenAI-compatible LLM 生成结构化中文周报。通过 CLI + systemd timer 在 VPS 上每周运行：生成周报、发布到 Rin 博客、保存本地 Markdown、上传 Cloudflare R2、Scripting Remote Push 推 iPhone，并按仓库向 Telegram 频道推送 GitHub 条目。

## 功能

- VPS one-shot：`python -m ai_news_bot.main --send`
- 每周定时：systemd timer 默认**每周一** `08:00`（Asia/Shanghai）
- 周报归档：`reports/YYYY-Www.md` / `.html`（ISO 周，如 `2026-W31`）与 latest 副本
- 候选窗口：生成日往前 **7 天**（含当日）的未推送条目
- R2 上传 + Rin 博客幂等发布（alias：`weekly-news-{slug}`）
- iPhone 通知：Scripting Remote Push，点击打开博客链接
- Telegram：推送 GitHub Trending + 你可能感兴趣仓库（逐条，频道行为保持不变）
- **⭐ 你可能感兴趣**：star 画像 + Search，周报汇总多兴趣簇，**21 天冷却**避免连播
- **GitHub Trending**：默认 `since=weekly`，解析本周 star、多语言抓取、**7 天冷却**、HTTP 重试
- **HN**：最低分过滤、AI 关键词分流到「AI动态」、每节 HN 条数上限
- LLM 生成后后处理：校正 GitHub 节格式、去掉错误「来源」尾巴、过滤空话
- 运行指标：`data/metrics-YYYY-MM-DD.json`（仅 `--send` 持久化时写入）

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
TELEGRAM_BOT_TOKEN=replace-with-your-telegram-bot-token
GITHUB_TOKEN=replace-with-your-github-pat
```

编辑 `config.json` 后：

```bash
python -m ai_news_bot.main --config config.json --sources sources.json --dry-run --no-llm
python -m ai_news_bot.main --config config.json --sources sources.json --send
```

安装 systemd：

```bash
cp deploy/systemd/ai-news-bot.service /etc/systemd/system/ai-news-bot.service
cp deploy/systemd/ai-news-bot.timer /etc/systemd/system/ai-news-bot.timer
systemctl daemon-reload
systemctl enable --now ai-news-bot.timer
```

从日报升级到周报时，额外确认：

```bash
# 若本地 config.json 仍写着旧默认，请改：
# scripting_push.title → Furina · 每周科技/AI周报
# blog.title_prefix / tags → 每周科技 / AI 周报、每周新闻
# r2.key_prefix → weekly
# sources.json github_trending.since → weekly

cp deploy/systemd/ai-news-bot.timer /etc/systemd/system/ai-news-bot.timer
cp deploy/systemd/ai-news-bot.service /etc/systemd/system/ai-news-bot.service
systemctl daemon-reload
systemctl restart ai-news-bot.timer
systemctl list-timers ai-news-bot.timer
```

更新代码：

```bash
cd /opt/ai-news-bot
git pull
.venv/bin/pip install -r requirements.txt
# config.json / sources.json / data / /etc/ai-news-bot.env 不会被覆盖
```

## 新闻源

默认见 `sources.example.json`。常见字段：

| 块 | 说明 |
|---|---|
| `rss` / `json_apis` | 常规资讯源 |
| `hacker_news.min_score` | HN 最低分数（默认 40） |
| `github_trending.languages` | 如 `["", "python", "typescript", "rust"]` |
| `github_trending.since` | 默认 `weekly` |
| `github_trending.cooldown_days` | Trending 冷却（默认 7） |
| `github_interest.cooldown_days` | 兴趣推荐冷却（默认 21） |
| `github_interest.max_stars` | 兴趣仓 star 上限（默认 12000，偏中腰部） |

### `github_interest` 示例

```json
"github_interest": {
  "enabled": true,
  "username": "Furinelle",
  "token_env": "GITHUB_TOKEN",
  "limit": 8,
  "min_stars": 80,
  "max_stars": 12000,
  "cooldown_days": 21,
  "pushed_within_days": 150,
  "profile_cache_path": "data/star_profile.json",
  "profile_ttl_hours": 24
}
```

## 事实安全

- 只使用候选事实，禁止编造
- 普通新闻标注可点击来源名
- GitHub 两节使用仓库链接，禁止「（来源：…）」尾巴与空话描述
- 重大单来源标注「未交叉验证」

这不能替代人工核查。
