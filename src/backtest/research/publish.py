"""CLI entry point for the research note generator.

Usage:
    python -m src.backtest.research.publish daily         Daily brief (US + HK + crypto)
    python -m src.backtest.research.publish trade_read    Trade setups with entry/stop/target
    python -m src.backtest.research.publish kol           KOL-style daily brief
    python -m src.backtest.research.publish weekly        Weekly deep dive
    python -m src.backtest.research.publish sectors       Sector rotation note

Requires DEEPSEEK_API_KEY in environment.
"""

from __future__ import annotations

import os
import sys

from .writers import ResearchNoteWriter


def main():
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("ERROR: DEEPSEEK_API_KEY environment variable is required.", file=sys.stderr)
        sys.exit(1)

    style = sys.argv[1] if len(sys.argv) > 1 else "daily"
    topic = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else None

    writer = ResearchNoteWriter()

    style_map = {
        "daily": lambda: writer.daily_brief(topic or "US + HK + crypto market review"),
        "trade_read": lambda: writer.trade_read(topic or "Trade setups across US + HK + crypto"),
        "kol": lambda: writer.kol_daily(topic or "Trader's morning brief"),
        "weekly": lambda: writer.weekly_note(),
        "sectors": lambda: writer.publish(
            topic or "Sector rotation analysis", style="sector_rotation"
        ),
    }

    fn = style_map.get(style)
    if fn:
        article = fn()
    else:
        article = writer.publish(topic or f"Market analysis: {style}", style="daily")

    print(article)


if __name__ == "__main__":
    main()
