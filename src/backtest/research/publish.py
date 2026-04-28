"""CLI entry point for multi-persona research note generator.

Usage:
    python -m src.backtest.research.publish macro_quant      Sell-side strategist
    python -m src.backtest.research.publish trade_read       Entry/stop/target setups
    python -m src.backtest.research.publish onchain          Crypto on-chain detective
    python -m src.backtest.research.publish options_greeks   Derivatives desk view
    python -m src.backtest.research.publish narrative_trader Theme/catalyst-driven
    python -m src.backtest.research.publish risk_parity      Portfolio construction
    python -m src.backtest.research.publish morning_call     3-min video script
    python -m src.backtest.research.publish data_snapshot    Pure data tables, no LLM

    python -m src.backtest.research.publish list             List all personas

Requires DEEPSEEK_API_KEY in environment.
"""

from __future__ import annotations

import os
import sys

from .writers import PERSONAS, ResearchNoteWriter


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    writer = ResearchNoteWriter()

    if command == "list":
        for pid, p in PERSONAS.items():
            print(f"  {pid:20s} {p.name:40s} {p.tagline}")
        return

    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("ERROR: DEEPSEEK_API_KEY environment variable is required.", file=sys.stderr)
        sys.exit(1)

    topic = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
    kwargs = {}
    if "no-crypto" in sys.argv:
        kwargs["include_crypto"] = False
    if "no-hk" in sys.argv:
        kwargs["include_hk"] = False

    article = writer.publish(command, topic, **kwargs)
    print(article)


if __name__ == "__main__":
    main()
