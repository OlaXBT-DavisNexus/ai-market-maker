#!/usr/bin/env python3
"""
Demo backtest script for AI Market Maker
Optimized to show good results with decent trade frequency
"""

import os
import sys
import json
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Use demo policy config
os.environ["AIMM_POLICY_PATH"] = str(project_root / "config" / "policy.demo.json")

def run_demo_backtest():
    """Run optimized demo backtest"""
    print("🚀 AI Market Maker - Demo Backtest")
    print("=" * 50)
    print("Optimized for better trade frequency and results")
    print()
    
    # Import after path setup
    from backtest.run_demo import main as run_demo_main
    import argparse
    
    # Create custom args for demo
    class DemoArgs:
        def __init__(self):
            self.ticker = "BTC/USDT"
            self.symbols = "BTC/USDT,ETH/USDT,SOL/USDT"
            self.ticker_only = False
            self.steps = 100
            self.interval_sec = 86400  # 1 day
            self.online = True
            self.exchange = "binance"
            self.timeframe = "1d"
            self.initial_cash = 10000
            self.deploy_spot_pct = 0
            self.run_id = f"demo_{int(time.time())}"
            self.min_trades = 5
            self.max_fetch = 200
            self.llm = False
            self.runs_dir = None
            self.ohlcv_cache_dir = None
            self.refresh_ohlcv_cache = False
            self.csv_only = False
    
    args = DemoArgs()
    
    print(f"📊 Configuration:")
    print(f"  • Symbols: {args.symbols}")
    print(f"  • Steps: {args.steps}")
    print(f"  • Timeframe: {args.timeframe}")
    print(f"  • Initial Cash: ${args.initial_cash:,.0f}")
    print(f"  • Min Trades Target: {args.min_trades}")
    print(f"  • Policy: config/policy.demo.json (optimized)")
    print()
    
    # Run backtest
    try:
        # Monkey-patch sys.argv for the demo module
        original_argv = sys.argv
        sys.argv = [
            "run_demo.py",
            "--symbols", args.symbols,
            "--steps", str(args.steps),
            "--online",
            "--exchange", args.exchange,
            "--timeframe", args.timeframe,
            "--initial-cash", str(args.initial_cash),
            "--min-trades", str(args.min_trades),
            "--max-fetch", str(args.max_fetch),
            "--run-id", args.run_id
        ]
        
        if args.llm:
            sys.argv.append("--llm")
        
        run_demo_main()
        
    except SystemExit:
        # run_demo_main calls sys.exit(), we need to catch it
        pass
    finally:
        sys.argv = original_argv
    
    # Load and display results
    results_dir = project_root / ".runs" / "backtests" / args.run_id
    summary_file = results_dir / "summary.json"
    
    if summary_file.exists():
        with open(summary_file, 'r') as f:
            results = json.load(f)
        
        print()
        print("=" * 50)
        print("📈 DEMO BACKTEST RESULTS")
        print("=" * 50)
        
        # Key metrics
        trade_count = results.get("trade_count", 0)
        total_return = results.get("total_return_pct", 0)
        excess_return = results.get("benchmark", {}).get("excess_return_vs_buy_hold_equity_pct", 0)
        
        # Fix display if total_return is 0 but should have value
        if total_return == 0 and "final_equity_usd" in results and "initial_equity_usd" in results:
            initial = results["initial_equity_usd"]
            final = results["final_equity_usd"]
            if initial > 0:
                total_return = ((final - initial) / initial) * 100
        
        print(f"💰 Total Return: {total_return:.2f}%")
        print(f"📊 Excess vs Buy & Hold: {excess_return:.2f}%")
        print(f"🔄 Trade Count: {trade_count}")
        
        if "metrics" in results:
            metrics = results["metrics"]
            print(f"📈 Sharpe Ratio: {metrics.get('sharpe', 0):.2f}")
            print(f"📉 Max Drawdown: {metrics.get('max_drawdown', 0)*100:.2f}%")
            print(f"✅ Win Rate: {metrics.get('win_rate', 0)*100:.1f}%")
        
        print()
        print("🔧 Demo Optimizations Applied:")
        print("  • Lower confidence threshold (0.35 vs 0.45)")
        print("  • Shorter trade cooldown (12 vs 48 bars)")
        print("  • Higher position sizing (20% vs 10%)")
        print("  • Enable short selling")
        print("  • Multiple symbols for more opportunities")
        
        # Save demo summary
        demo_summary = {
            "demo_run": True,
            "run_id": args.run_id,
            "timestamp": int(time.time()),
            "config": {
                "symbols": args.symbols,
                "steps": args.steps,
                "policy": "demo_optimized"
            },
            "results": {
                "trade_count": trade_count,
                "total_return_pct": total_return if total_return != 0 else results.get("total_return_pct", 0),
                "excess_return_pct": excess_return
            }
        }
        
        demo_file = project_root / ".runs" / "demo_summary.json"
        with open(demo_file, 'w') as f:
            json.dump(demo_summary, f, indent=2)
        
        print()
        print(f"📁 Results saved to: {results_dir}")
        print(f"📋 Demo summary: {demo_file}")
        
        # Give recommendations
        print()
        print("💡 For New Users:")
        print("1. Run: python3 scripts/run_demo_backtest.py")
        print("2. Try different symbols: ETH/USDT, SOL/USDT, etc.")
        print("3. Adjust --steps for longer/shorter backtests")
        print("4. Use --llm for AI-enhanced signals (requires OpenAI key)")
        
        return results
    else:
        print("❌ Backtest completed but results not found")
        return None

if __name__ == "__main__":
    run_demo_backtest()