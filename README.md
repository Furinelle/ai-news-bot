# AI News Bot

每日科技/AI日报机器人：抓取 RSS、Hacker News、GitHub Trending，去重排序后交给 OpenAI-compatible 大模型生成中文 Furina 日报，并通过 pushplus 的 ClawBot 渠道推送到微信。

## 功能

- RSS 新闻采集：TechCrunch AI、The Verge、OpenAI News、Google AI、GitHub Blog，可自行增删。
- Hacker News API 采集。
- GitHub Trending 页面采集。
- URL 和标题去重。
- SQLite 记录已推送链接，减少重复日报。
- OpenAI-compatible API 摘要，可接 OpenAI、DeepSeek、通义、硅基流动、本地 vLLM/Ollama 兼容服务等。
- pushplus ClawBot 微信推送。
- `--dry-run` 本地预览，`--send` 正式推送。
- 默认生成约 18 条内容，每条包含“发生了什么 + 为什么值得看”，比纯快讯更耐读。

## 安装

```powershell
chcp 65001
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()

cd C:\Users\Furina\Documents\GitHub\VPS\ai-news-bot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item config.example.json config.json
Copy-Item sources.example.json sources.json
```

## 配置密钥

不要把真实密钥写进仓库，使用环境变量：

```powershell
$env:LLM_API_KEY = "你的大模型 API Key"
$env:PUSHPLUS_TOKEN = "你的 pushplus token"
```

`config.json` 默认使用 OpenAI 官方接口：

```json
{
  "llm": {
    "base_url": "https://api.openai.com/v1",
    "api_key_env": "LLM_API_KEY",
    "model": "gpt-4.1-mini",
    "timeout_seconds": 180
  }
}
```

如果使用 DeepSeek、硅基流动或其他 OpenAI-compatible 服务，只改 `base_url` 和 `model` 即可。

想让日报更耐读，可以把 `config.json` 里的数量设成：

```json
{
  "limits": {
    "max_items": 60,
    "max_report_items": 18
  }
}
```

如果 DeepSeek 生成较慢并出现 `LLM request timed out`，优先把 `llm.timeout_seconds` 提到 `240` 或 `300`；如果仍超时，再把 `max_report_items` 调低到 `12`。

## pushplus ClawBot

1. 在 pushplus 获取 token。
2. 按 pushplus 页面说明绑定微信 ClawBot。
3. 确认 `config.json` 中：

```json
{
  "pushplus": {
    "token_env": "PUSHPLUS_TOKEN",
    "channel": "clawbot",
    "template": "txt"
  }
}
```

ClawBot 通道通常需要你定期主动给机器人发消息以保持可推送状态；如果推送失败，先检查 pushplus 后台和 ClawBot 会话状态。

## 运行

预览日报但不推送：

```powershell
python -m ai_news_bot.main --config config.json --sources sources.json --dry-run
```

生成不用大模型的原文回退版日报：

```powershell
python -m ai_news_bot.main --config config.json --sources sources.json --dry-run --no-llm
```

`--no-llm` 是原文回退模式，会保留英文来源标题；要中文日报请运行不带 `--no-llm` 的命令，让 DeepSeek 或其他大模型翻译和改写。

正式推送到微信：

```powershell
python -m ai_news_bot.main --config config.json --sources sources.json --send
```

同时保存报告：

```powershell
python -m ai_news_bot.main --config config.json --sources sources.json --send --out reports\daily.txt
```

## Windows 计划任务示例

先确认虚拟环境路径存在，然后创建每天 08:00 执行的任务：

```powershell
$Action = New-ScheduledTaskAction -Execute "C:\Users\Furina\Documents\GitHub\VPS\ai-news-bot\.venv\Scripts\python.exe" -Argument "-m ai_news_bot.main --config config.json --sources sources.json --send" -WorkingDirectory "C:\Users\Furina\Documents\GitHub\VPS\ai-news-bot"
$Trigger = New-ScheduledTaskTrigger -Daily -At 08:00
Register-ScheduledTask -TaskName "AI News Bot" -Action $Action -Trigger $Trigger
```

如果使用计划任务，建议把 `LLM_API_KEY` 和 `PUSHPLUS_TOKEN` 配成系统环境变量，或改用专门的安全密钥注入方式。

## Linux cron 示例

```cron
0 8 * * * cd /opt/ai-news-bot && . .venv/bin/activate && python -m ai_news_bot.main --config config.json --sources sources.json --send >> logs/news-bot.log 2>&1
```

## 事实安全

模型提示词已要求：

- 不得编造候选新闻之外的事实。
- 普通新闻只保留来源名，GitHub Trending 保留仓库链接，减少微信正文干扰。
- 输出使用纯文本，不依赖 Markdown 加粗等微信可能不稳定支持的格式。
- 重大新闻单来源时标注“未交叉验证”。

这不能替代人工核查。涉及监管、融资、裁员、并购、安全事故等重大内容，建议在推送前人工扫一眼。
