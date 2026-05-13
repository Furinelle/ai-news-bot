# Changelog

## [1.3.1] - 2026-05-13

### 修复
- LLM 调用失败时静默回退，现在改为在日志中输出具体错误原因，方便排查
- `provider_id` 未配置时在日志中给出明确提示
- 回退模式（无 LLM）下 GitHub Trending 条目数量无上限，现在限制为最多 10 条，科技热点/AI动态各最多 8 条

---

## [1.3.0] - 2026-05-13

### 修复
- GitHub Trending 条目链接缺失：改为在传入 LLM 的数据中预嵌 Markdown 链接，LLM 原样复制，不再依赖模型自行生成
- 条目序号缺失：新增 `_fix_numbering()` 后处理，将 LLM 输出的项目符号（`-` / `•`）强制转换为阿拉伯数字序号

---

## [1.2.0] - 2026-05-13

### 新增
- 恢复每日定时推送功能，改用 AstrBot 原生 `context.send_message` 发送，不再依赖 PushPlus
- 新增配置项 `schedule_time`（定时时间，HH:MM 格式）
- 新增配置项 `schedule_targets`（目标会话 ID，支持群和私信，换行或逗号分隔）

---

## [1.1.0] - 2026-05-13

### 新增
- 新增 Ars Technica、MIT Technology Review、VentureBeat AI、Wired 四个 RSS 源
- 科技热点和 AI动态每节要求 6~8 条，GitHub Trending 固定 10 条
- 每条末尾附来源媒体名，格式：`（来源：媒体名）`
- 日报改用 Markdown 格式输出，适配微信 ClawBot 渲染

### 变更
- `max_report_items` 默认值从 18 调整为 30
- 移除 PushPlus 推送功能

### 修复
- `sources.json` RSS 条目缺少 `name` / `category` 字段导致 KeyError
- HN 配置键名 `hackernews` → `hacker_news`
- `filter` 导入路径错误（`astrbot.api.all` → `astrbot.api.event`）

---

## [1.0.0] - 2026-05-13

### 新增
- 首次作为 AstrBot 插件发布
- `/news` 命令按需生成当日科技/AI日报，分三节发送
- 采集源：TechCrunch AI、The Verge、OpenAI Blog、Google AI Blog、GitHub Blog、Hacker News、GitHub Trending
- 使用 AstrBot 内置 LLM provider 生成摘要，无 LLM 时自动回退为原文模式
- SQLite 去重，避免重复推送已读条目
- 插件配置：`provider_id`、`max_report_items`
