# Changelog

## [1.4.3] - 2026-05-14

### 新增
- 新增 `/news_subscribe HH:MM`，可直接在当前微信私聊或群聊订阅每日推送
- 新增 `/news_unsubscribe`，可取消当前会话的每日推送
- 新增 `/news_schedule`，可查看推送时间、订阅会话数和当前会话订阅状态

### 变更
- 微信指令保存的订阅设置优先于后台 `schedule_targets`，后台配置仅作为未使用指令时的默认值

---

## [1.4.2] - 2026-05-14

### 修复
- AstrBot 插件候选新闻改用分类均衡选择，避免 LLM 输入中某些板块只有一两条素材
- 回退模式和 CLI LLM 输出统一为 ClawBot 友好的 Markdown 标题、分隔线、编号列表和 GitHub 链接
- 定时推送注册增加日志，新增 `/newsid` 查看当前会话 ID，并在目标会话无效时记录错误
- `max_report_items` 默认值统一为 30，GitHub Trending 数量说明统一为 5 条

---

## [1.4.1] - 2026-05-13

### 修复
- `_fix_numbering` 彻底重写：新增对"无任何标记的纯段落"的处理，使序号在所有 LLM 输出格式（已有序号 / `-` 符号 / 纯文本）下均正确生成
- 回退模式（fallback）输出不再经过编号处理（避免误重编号 render.py 已生成的序号）

---

## [1.4.0] - 2026-05-13

### 新增
- 新增 7 个 RSS 源：The Verge AI、Ars Technica AI、Hugging Face Blog、MarkTechPost、DailyAI、TLDR AI、AI News、Unite.AI，大幅扩充 AI动态内容

### 修复
- OpenAI Blog RSS URL 修正（`/blog/rss.xml` → `/news/rss.xml`）
- GitHub Trending 改为只抓全语言榜单（移除 python、javascript 分类榜），消除跨语言榜单重复条目

---

## [1.3.2] - 2026-05-13

### 变更
- GitHub Trending 条目数从 10 条调整为 5 条

---

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
