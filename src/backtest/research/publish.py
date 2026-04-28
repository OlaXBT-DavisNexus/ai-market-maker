"""CLI entry point for the research note generator.

Usage:
    python -m src.backtest.research.publish daily       # Quick daily brief
    python -m src.backtest.research.publish weekly      # Weekly deep dive
    python -m src.backtest.research.publish custom "my topic"  # Custom topic

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

    if style == "daily":
        article = writer.quick_note() if not topic else writer.publish(topic, style="daily")
    elif style == "weekly":
        article = writer.weekly_note() if not topic else writer.publish(topic, style="weekly")
    elif style == "sectors":
        article = writer.publish(topic or "Sector rotation analysis", style="sector_rotation")
    else:
        article = writer.publish(topic or f"Market analysis: {style}", style="daily")

    print(article)


if __name__ == "__main__":
    main()
