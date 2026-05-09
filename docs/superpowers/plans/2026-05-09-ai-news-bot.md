# AI News Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a manually runnable daily technology and AI news bot that can summarize fetched items with an OpenAI-compatible LLM and push the result to WeChat through pushplus ClawBot.

**Architecture:** The bot is a small Python CLI with separate modules for configuration, news models, RSS fetching, deduplication, ranking, LLM summarization, report rendering, SQLite history, and pushplus notification. The first version keeps provider boundaries simple so pushplus or LLM providers can be swapped later.

**Tech Stack:** Python 3.11+, standard library, `feedparser`, `httpx`, `beautifulsoup4`.

---

### Task 1: Core Data Flow

**Files:**
- Create: `ai-news-bot/ai_news_bot/models.py`
- Create: `ai-news-bot/ai_news_bot/config.py`
- Create: `ai-news-bot/tests/test_config.py`

- [x] **Step 1: Write failing tests for loading environment-backed configuration.**
- [x] **Step 2: Run `python -m unittest discover -s tests -v` and confirm imports fail before implementation.**
- [ ] **Step 3: Implement minimal config dataclasses and loader.**
- [ ] **Step 4: Re-run tests and confirm config behavior passes.**

### Task 2: Selection and Rendering

**Files:**
- Create: `ai-news-bot/ai_news_bot/dedupe.py`
- Create: `ai-news-bot/ai_news_bot/render.py`
- Create: `ai-news-bot/tests/test_dedupe.py`
- Create: `ai-news-bot/tests/test_render.py`

- [x] **Step 1: Write failing tests for URL/title dedupe and source-link-preserving report rendering.**
- [ ] **Step 2: Implement minimal dedupe and render helpers.**
- [ ] **Step 3: Re-run unit tests and confirm behavior.**

### Task 3: LLM and Pushplus Boundaries

**Files:**
- Create: `ai-news-bot/ai_news_bot/llm.py`
- Create: `ai-news-bot/ai_news_bot/pushplus.py`
- Create: `ai-news-bot/tests/test_llm.py`
- Create: `ai-news-bot/tests/test_pushplus.py`

- [x] **Step 1: Write failing tests for OpenAI-compatible payload creation and pushplus ClawBot payload creation.**
- [ ] **Step 2: Implement payload builders and HTTP clients with injectable post functions.**
- [ ] **Step 3: Re-run unit tests and confirm behavior.**

### Task 4: Fetchers, Storage, CLI, Docs

**Files:**
- Create: `ai-news-bot/ai_news_bot/fetch_rss.py`
- Create: `ai-news-bot/ai_news_bot/fetch_hn.py`
- Create: `ai-news-bot/ai_news_bot/fetch_github.py`
- Create: `ai-news-bot/ai_news_bot/storage.py`
- Create: `ai-news-bot/ai_news_bot/main.py`
- Create: `ai-news-bot/config.example.json`
- Create: `ai-news-bot/sources.example.json`
- Create: `ai-news-bot/requirements.txt`
- Create: `ai-news-bot/README.md`

- [ ] **Step 1: Implement straightforward fetchers and SQLite history.**
- [ ] **Step 2: Implement CLI flags for dry run, send, and config paths.**
- [ ] **Step 3: Document environment variables, pushplus ClawBot setup, and scheduling examples.**
- [ ] **Step 4: Run unit tests and a dry-run command.**

