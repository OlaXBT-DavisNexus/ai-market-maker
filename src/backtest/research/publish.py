"""多角色研究筆記 CLI 入口。

用法:
    python -m src.backtest.research.publish macro_quant      宏觀量化策略師
    python -m src.backtest.research.publish trade_read       倉位分析 (entry/stop/target)
    python -m src.backtest.research.publish onchain          鏈上偵探
    python -m src.backtest.research.publish options_greeks   期權 Greeks
    python -m src.backtest.research.publish narrative_trader 敘事交易者
    python -m src.backtest.research.publish risk_parity      風險平價
    python -m src.backtest.research.publish morning_call     3分鐘晨報腳本
    python -m src.backtest.research.publish data_snapshot    純數據, 無需 API key
    python -m src.backtest.research.publish list             列出所有角色

    python -m src.backtest.research.publish trade_read no-crypto  跳過幣圈
    python -m src.backtest.research.publish macro_quant no-hk     跳過港股

需要 DEEPSEEK_API_KEY 環境變量（或 .env 文件）。
"""

from __future__ import annotations

import os
import sys

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from .writers import PERSONAS, ResearchNoteWriter


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    writer = ResearchNoteWriter()

    if command == "list":
        print("可用角色:\n")
        for pid, p in PERSONAS.items():
            print(f"  {pid:20s} {p.name:40s} {p.tagline}")
        return

    # data_snapshot 不需要 API key
    if command != "data_snapshot" and not os.environ.get("DEEPSEEK_API_KEY"):
        print("錯誤: DEEPSEEK_API_KEY 環境變量未設置。請檢查 .env 文件。", file=sys.stderr)
        sys.exit(1)

    args = [a for a in sys.argv[2:] if not a.startswith("no-")]
    flags = [a for a in sys.argv[2:] if a.startswith("no-")]
    topic = " ".join(args)
    kwargs = {}
    if "no-crypto" in flags:
        kwargs["include_crypto"] = False
    if "no-hk" in flags:
        kwargs["include_hk"] = False

    try:
        article = writer.publish(command, topic, **kwargs)
    except ValueError as e:
        print(f"錯誤: {e}", file=sys.stderr)
        sys.exit(1)

    print(article)


if __name__ == "__main__":
    main()
