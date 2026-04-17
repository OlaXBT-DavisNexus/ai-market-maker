#!/usr/bin/env python3
"""
Frequent trading backtest with more symbols and aggressive settings
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

def run_frequent_backtest():
    """Run frequent trading backtest with more symbols"""
    print("🚀 AI Market Maker - Frequent Trading Backtest")
    print("=" * 60)
    print("Optimized for higher trade frequency with 10+ symbols")
    print()
    
    # Use frequent trading policy
    os.environ["AIMM_POLICY_PATH"] = str(project_root / "config" / "policy.frequent.json")
    
    # More symbols for more opportunities
    symbols = [
        "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
        "ADA/USDT", "AVAX/USDT", "DOT/USDT", "LINK/USDT", "MATIC/USDT"
    ]
    symbols_str = ",".join(symbols[:8])  # Use first 8 to avoid API limits
    
    # Import after path setup
    from backtest.run_demo import main as run_demo_main
    
    # Create args
    class FrequentArgs:
        def __init__(self):
            self.ticker = "BTC/USDT"
            self.symbols = symbols_str
            self.ticker_only = False
            self.steps = 200  # More steps for more trades
            self.interval_sec = 14400  # 4h timeframe
            self.online = True
            self.exchange = "binance"
            self.timeframe = "4h"
            self.initial_cash = 10000
            self.deploy_spot_pct = 0
            self.run_id = f"freq_{int(time.time())}"
            self.min_trades = 15  # Target more trades
            self.max_fetch = 300
            self.llm = False
            self.runs_dir = None
            self.ohlcv_cache_dir = None
            self.refresh_ohlcv_cache = False
            self.csv_only = False
    
    args = FrequentArgs()
    
    print(f"📊 Configuration:")
    print(f"  • Symbols: {len(symbols)} total, using {len(args.symbols.split(','))}")
    print(f"  • Steps: {args.steps} ({args.timeframe} timeframe)")
    print(f"  • Initial Cash: ${args.initial_cash:,.0f}")
    print(f"  • Min Trades Target: {args.min_trades}")
    print(f"  • Policy: config/policy.frequent.json")
    print(f"  • Timeframe: {args.timeframe} (faster signals)")
    print()
    
    print("🔧 Frequent Trading Optimizations:")
    print("  • Lower confidence: 0.25 (vs 0.35 demo, 0.45 default)")
    print("  • Shorter cooldown: 6 bars (vs 12 demo, 48 default)")
    print("  • More symbols: 8+ for more opportunities")
    print("  • 4h timeframe: Faster signal generation")
    print("  • Tighter stops: 1.5% stop loss, 4% take profit")
    print()
    
    # Run backtest
    try:
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
        
        run_demo_main()
        
    except SystemExit:
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
        print("=" * 60)
        print("📈 FREQUENT TRADING RESULTS")
        print("=" * 60)
        
        # Key metrics
        trade_count = results.get("trade_count", 0)
        total_return = results.get("total_return_pct", 0)
        
        if total_return == 0 and "final_equity_usd" in results and "initial_equity_usd" in results:
            initial = results["initial_equity_usd"]
            final = results["final_equity_usd"]
            if initial > 0:
                total_return = ((final - initial) / initial) * 100
        
        excess_return = results.get("benchmark", {}).get("excess_return_vs_buy_hold_equity_pct", 0)
        
        print(f"💰 Total Return: {total_return:.2f}%")
        print(f"📊 Excess vs BTC Buy & Hold: {excess_return:.2f}%")
        print(f"🔄 Trade Count: {trade_count}")
        
        if "metrics" in results:
            metrics = results["metrics"]
            print(f"📈 Sharpe Ratio: {metrics.get('sharpe', 0):.2f}")
            print(f"📉 Max Drawdown: {metrics.get('max_drawdown', 0)*100:.2f}%")
            print(f"✅ Win Rate: {metrics.get('win_rate', 0)*100:.1f}%")
            print(f"🎯 Sortino Ratio: {metrics.get('sortino', 0):.2f}")
        
        # Benchmark comparison
        if "benchmark" in results:
            bench = results["benchmark"]
            print()
            print("📊 BENCHMARK COMPARISON:")
            print(f"  • BTC Buy & Hold: {bench.get('benchmark_buy_hold_equity_return_pct', 0):.2f}%")
            print(f"  • Equal Weight Portfolio: {bench.get('benchmark_equal_weight_equity_return_pct', 0):.2f}%")
            print(f"  • Strategy vs Equal Weight: {bench.get('excess_return_vs_equal_weight_equity_pct', 0):.2f}%")
        
        # Calculate trade frequency
        if trade_count > 0 and "steps" in results:
            steps = results["steps"]
            timeframe = results.get("timeframe", "4h")
            
            # Estimate period
            if timeframe == "4h":
                hours_per_step = 4
                total_hours = steps * hours_per_step
                days = total_hours / 24
                trades_per_day = trade_count / days
                trades_per_week = trades_per_day * 7
                
                print()
                print("⏱️ TRADE FREQUENCY:")
                print(f"  • Period: {days:.1f} days ({total_hours:.0f} hours)")
                print(f"  • Trades per day: {trades_per_day:.2f}")
                print(f"  • Trades per week: {trades_per_week:.1f}")
                print(f"  • Steps between trades: {steps/trade_count:.1f}")
        
        # Save summary
        freq_summary = {
            "frequent_run": True,
            "run_id": args.run_id,
            "timestamp": int(time.time()),
            "config": {
                "symbols": args.symbols,
                "steps": args.steps,
                "timeframe": args.timeframe,
                "policy": "frequent_trading"
            },
            "results": {
                "trade_count": trade_count,
                "total_return_pct": total_return,
                "excess_return_pct": excess_return
            }
        }
        
        summary_file = project_root / ".runs" / "frequent_summary.json"
        with open(summary_file, 'w') as f:
            json.dump(freq_summary, f, indent=2)
        
        print()
        print(f"📁 Results saved to: {results_dir}")
        print(f"📋 Summary: {summary_file}")
        
        # Recommendations
        print()
        print("💡 TRADING STRATEGY ANALYSIS:")
        if trade_count >= args.min_trades:
            print("✅ Target achieved: Good trade frequency")
        else:
            print("⚠️  Below target: Consider further optimization")
        
        if excess_return > 0:
            print("✅ Positive alpha: Outperforming benchmarks")
        else:
            print("⚠️  Negative alpha: Review strategy parameters")
        
        sharpe = results.get("metrics", {}).get("sharpe", 0)
        if sharpe > 1.0:
            print("✅ Good risk-adjusted returns (Sharpe > 1.0)")
        elif sharpe > 0:
            print("⚠️  Acceptable risk-adjusted returns")
        else:
            print("❌ Poor risk-adjusted returns")
        
        return results
    else:
        print("❌ Backtest completed but results not found")
        return None

if __name__ == "__main__":
    run_frequent_backtest()