# AI News Bot — AstrBot 插件

每日科技/AI日报 AstrBot 插件。抓取 RSS、Hacker News、GitHub Trending，去重排序后交给 LLM 生成结构化中文日报，在对话中按需推送。

## 功能

- `/news` 命令：即时生成并分段发送当日科技/AI日报
- 多源采集：TechCrunch AI、The Verge、Ars Technica、MIT Technology Review、VentureBeat AI、Wired、OpenAI Blog、Google AI Blog、GitHub Blog、Hacker News、GitHub Trending
- URL 和标题去重，SQLite 记录已推送链接，减少重复内容
- LLM 生成中文摘要，格式固定：科技热点 6~8 条、AI动态 6~8 条、GitHub Trending 5 条（含仓库链接）
- 每条附来源媒体名，GitHub Trending 附仓库链接
- 无 LLM 时自动回退为 Markdown 原文模式

## 安装

在 AstrBot 插件管理界面，填入仓库地址安装：

```
https://github.com/Furinelle/ai-news-bot
```

## 配置

插件安装后在 AstrBot 仪表盘的插件配置页面配置以下项目：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `provider_id` | 用于生成日报的 LLM 模型提供商 | （必填） |
| `max_report_items` | 送入 LLM 的最大候选条目数 | `30` |
| `schedule_time` | 每日定时推送时间，格式 `HH:MM`（Asia/Shanghai） | 空 |
| `schedule_targets` | 后台配置的默认推送目标；微信内订阅指令会优先于此配置 | 空 |

## 使用

在任意对话中发送：

```
/news
```

插件会先回复"生成中"提示，随后将日报按三节（科技热点 / AI动态 / GitHub Trending）分段发送。

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
| MIT Technology Review | AI动态 |
| VentureBeat AI | AI动态 |
| The Verge | 科技热点 |
| Ars Technica | 科技热点 |
| Wired | 科技热点 |
| GitHub Blog | 科技热点 |
| Hacker News | 科技热点 |
| GitHub Trending | GitHub Trending |

## 事实安全

模型提示词已要求：

- 只使用候选新闻中的事实，不得编造公司名、数字、日期、融资金额或发布内容
- 普通新闻只标注来源媒体名，不输出完整链接
- GitHub Trending 每条附仓库链接
- 重大单来源新闻标注"未交叉验证"

这不能替代人工核查。涉及监管、融资、裁员、并购、安全事故等重大内容，建议在转发前人工确认。
