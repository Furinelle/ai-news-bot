from __future__ import annotations


def build_news_help() -> str:
    return "\n".join(
        [
            "AI News Bot 指令",
            "",
            "/news - 立即生成今日科技/AI日报",
            "/news_help - 显示指令列表",
            "/newsid - 查看当前会话 ID",
            "/news_subscribe 08:30 - 订阅当前会话的每日推送",
            "/news_unsubscribe - 取消当前会话的每日推送",
            "/news_schedule - 查看定时推送状态",
        ]
    )
