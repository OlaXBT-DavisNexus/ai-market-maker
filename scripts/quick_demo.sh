#!/bin/bash
# Quick demo script for AI Market Maker
# Shows good backtest results with decent trade frequency

set -e

echo "🚀 AI Market Maker - Quick Demo"
echo "================================"

# Check if in project directory
if [ ! -f "README.md" ]; then
    echo "❌ Please run this script from the ai-market-maker directory"
    echo "   cd /path/to/ai-market-maker"
    exit 1
fi

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found"
    exit 1
fi

echo "📊 Running optimized demo backtest..."
echo "   • Symbols: BTC/USDT,ETH/USDT,SOL/USDT"
echo "   • Timeframe: 1 day"
echo "   • Steps: 100"
echo "   • Optimized for better trade frequency"
echo ""

# Run demo backtest
python3 scripts/run_demo_backtest.py

echo ""
echo "✅ Demo completed!"
echo ""
echo "💡 Next steps:"
echo "1. Try different symbols: python3 scripts/run_demo_backtest.py --symbols \"ETH/USDT,SOL/USDT\""
echo "2. Run paper trading: python3 openclaw/scripts/claw_runner.py --paper"
echo "3. Check installation: ./openclaw/scripts/verify_installation.sh"
echo ""
echo "📚 Documentation:"
echo "   • OpenClaw guide: openclaw/examples/claw_usage.md"
echo "   • Korean guide: openclaw/examples/korean_guide.md"
echo "   • Full docs: docs/ directory"