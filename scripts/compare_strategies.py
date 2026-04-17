#!/usr/bin/env python3
"""
Compare different trading strategies: default, demo, frequent, balanced
"""

import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

def run_backtest_with_policy(policy_name, policy_path, symbols, steps=100, timeframe="1d"):
    """Run backtest with specific policy"""
    print(f"  Running {policy_name} backtest...")
    
    # Set policy
    os.environ["AIMM_POLICY_PATH"] = str(policy_path)
    
    # Import after path setup
    from backtest.run_demo import main as run_demo_main
    
    # Create run ID
    run_id = f"compare_{policy_name.lower()}_{int(time.time())}"
    
    # Run backtest
    try:
        original_argv = sys.argv
        sys.argv = [
            "run_demo.py",
            "--symbols", symbols,
            "--steps", str(steps),
            "--online",
            "--exchange", "binance",
            "--timeframe", timeframe,
            "--initial-cash", "10000",
            "--run-id", run_id
        ]
        
        run_demo_main()
        
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv
    
    # Load results
    results_dir = project_root / ".runs" / "backtests" / run_id
    summary_file = results_dir / "summary.json"
    
    if summary_file.exists():
        with open(summary_file, 'r') as f:
            return json.load(f)
    return None

def analyze_results(results, policy_name):
    """Analyze backtest results"""
    if not results:
        return None
    
    trade_count = results.get("trade_count", 0)
    total_return = results.get("total_return_pct", 0)
    
    # Calculate actual return if needed
    if total_return == 0 and "final_equity_usd" in results and "initial_equity_usd" in results:
        initial = results["initial_equity_usd"]
        final = results["final_equity_usd"]
        if initial > 0:
            total_return = ((final - initial) / initial) * 100
    
    excess_return = results.get("benchmark", {}).get("excess_return_vs_buy_hold_equity_pct", 0)
    btc_buy_hold = results.get("benchmark", {}).get("benchmark_buy_hold_equity_return_pct", 0)
    
    metrics = results.get("metrics", {})
    sharpe = metrics.get("sharpe", 0)
    max_dd = metrics.get("max_drawdown", 0) * 100
    win_rate = metrics.get("win_rate", 0) * 100
    
    # Calculate trade frequency
    steps = results.get("steps", 100)
    timeframe = results.get("timeframe", "1d")
    
    if timeframe == "1d":
        days = steps
    elif timeframe == "4h":
        days = steps * 4 / 24
    else:
        days = steps
    
    trades_per_day = trade_count / days if days > 0 else 0
    trades_per_week = trades_per_day * 7
    
    return {
        "policy": policy_name,
        "trade_count": trade_count,
        "total_return": total_return,
        "excess_vs_btc": excess_return,
        "btc_buy_hold": btc_buy_hold,
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "win_rate": win_rate,
        "trades_per_day": trades_per_day,
        "trades_per_week": trades_per_week,
        "period_days": days,
        "timeframe": timeframe
    }

def print_comparison_table(comparisons):
    """Print comparison table"""
    print("\n" + "=" * 120)
    print("STRATEGY COMPARISON ANALYSIS")
    print("=" * 120)
    
    headers = [
        "Strategy",
        "Trades",
        "Total Return",
        "vs BTC B&H",
        "Sharpe",
        "Max DD",
        "Win Rate",
        "Trades/Wk",
        "Trades/Day"
    ]
    
    # Print header
    header_fmt = "{:<15} {:<8} {:<12} {:<12} {:<8} {:<8} {:<10} {:<10} {:<10}"
    print(header_fmt.format(*headers))
    print("-" * 120)
    
    for comp in comparisons:
        if comp:
            row = [
                comp["policy"],
                f"{comp['trade_count']}",
                f"{comp['total_return']:+.2f}%",
                f"{comp['excess_vs_btc']:+.2f}%",
                f"{comp['sharpe']:.2f}",
                f"{comp['max_drawdown']:.1f}%",
                f"{comp['win_rate']:.1f}%",
                f"{comp['trades_per_week']:.1f}",
                f"{comp['trades_per_day']:.2f}"
            ]
            print(header_fmt.format(*row))
    
    print("=" * 120)

def print_recommendations(comparisons):
    """Print strategy recommendations"""
    print("\n" + "=" * 120)
    print("RECOMMENDATIONS")
    print("=" * 120)
    
    # Find best strategies by metric
    best_return = max(comparisons, key=lambda x: x["total_return"])
    best_sharpe = max(comparisons, key=lambda x: x["sharpe"])
    best_trades = max(comparisons, key=lambda x: x["trade_count"])
    best_excess = max(comparisons, key=lambda x: x["excess_vs_btc"])
    
    print("\n🏆 BEST PERFORMERS:")
    print(f"  • Highest Return: {best_return['policy']} ({best_return['total_return']:+.2f}%)")
    print(f"  • Best Sharpe: {best_sharpe['policy']} ({best_sharpe['sharpe']:.2f})")
    print(f"  • Most Trades: {best_trades['policy']} ({best_trades['trade_count']} trades)")
    print(f"  • Best vs BTC: {best_excess['policy']} ({best_excess['excess_vs_btc']:+.2f}% excess)")
    
    print("\n🎯 STRATEGY SELECTION GUIDE:")
    
    for comp in comparisons:
        policy = comp["policy"]
        sharpe = comp["sharpe"]
        excess = comp["excess_vs_btc"]
        trades = comp["trade_count"]
        
        recommendation = []
        
        if sharpe > 1.0:
            recommendation.append("Excellent risk-adjusted returns")
        elif sharpe > 0:
            recommendation.append("Acceptable risk-adjusted returns")
        else:
            recommendation.append("Poor risk-adjusted returns")
        
        if excess > 0:
            recommendation.append("Outperforms BTC buy & hold")
        else:
            recommendation.append("Underperforms BTC buy & hold")
        
        if trades >= 10:
            recommendation.append("Good trade frequency")
        elif trades >= 5:
            recommendation.append("Moderate trade frequency")
        else:
            recommendation.append("Low trade frequency")
        
        print(f"\n  {policy}:")
        for rec in recommendation:
            print(f"    • {rec}")
    
    print("\n🔧 CONFIGURATION TIPS:")
    print("  1. For more trades: Lower confidence threshold, shorter cooldown, more symbols")
    print("  2. For better returns: Add trend filters, improve risk management")
    print("  3. For better Sharpe: Adjust stop loss/take profit ratios")
    print("  4. For beginners: Start with 'demo' or 'balanced' strategies")
    
    print("\n📊 SYMBOL SELECTION:")
    print("  • Core: BTC/USDT, ETH/USDT, SOL/USDT (high liquidity)")
    print("  • Mid-cap: BNB/USDT, XRP/USDT, ADA/USDT (good volatility)")
    print("  • Small-cap: AVAX/USDT, DOT/USDT, LINK/USDT (higher risk/reward)")
    
    print("\n⏱️ TIMEFRAME SELECTION:")
    print("  • 1d: Lower frequency, higher confidence signals")
    print("  • 4h: Moderate frequency, good balance")
    print("  • 1h: High frequency, more noise, requires faster execution")

def main():
    """Main comparison function"""
    print("🚀 AI Market Maker - Strategy Comparison")
    print("=" * 60)
    print("Comparing: Default, Demo, Frequent, and Balanced strategies")
    print()
    
    # Define strategies to compare
    strategies = [
        {
            "name": "Default",
            "path": project_root / "config" / "policy.default.json",
            "symbols": "BTC/USDT",
            "steps": 100,
            "timeframe": "1d"
        },
        {
            "name": "Demo", 
            "path": project_root / "config" / "policy.demo.json",
            "symbols": "BTC/USDT,ETH/USDT,SOL/USDT",
            "steps": 100,
            "timeframe": "1d"
        },
        {
            "name": "Frequent",
            "path": project_root / "config" / "policy.frequent.json", 
            "symbols": "BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT,XRP/USDT,ADA/USDT,AVAX/USDT,DOT/USDT",
            "steps": 200,
            "timeframe": "4h"
        },
        {
            "name": "Balanced",
            "path": project_root / "config" / "policy.balanced.json",
            "symbols": "BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT,XRP/USDT,ADA/USDT",
            "steps": 150,
            "timeframe": "1d"
        }
    ]
    
    comparisons = []
    
    for strategy in strategies:
        print(f"\n📋 Testing {strategy['name']} strategy...")
        print(f"   Symbols: {strategy['symbols']}")
        print(f"   Steps: {strategy['steps']} ({strategy['timeframe']})")
        
        results = run_backtest_with_policy(
            strategy["name"],
            strategy["path"],
            strategy["symbols"],
            strategy["steps"],
            strategy["timeframe"]
        )
        
        analysis = analyze_results(results, strategy["name"])
        if analysis:
            comparisons.append(analysis)
            print(f"   ✓ Completed: {analysis['trade_count']} trades, {analysis['total_return']:+.2f}% return")
        else:
            print(f"   ✗ Failed to get results")
    
    # Print comparison
    if comparisons:
        print_comparison_table(comparisons)
        print_recommendations(comparisons)
        
        # Save comparison results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = project_root / ".runs" / f"strategy_comparison_{timestamp}.json"
        
        with open(output_file, 'w') as f:
            json.dump({
                "timestamp": timestamp,
                "comparisons": comparisons
            }, f, indent=2)
        
        print(f"\n📁 Comparison saved to: {output_file}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())