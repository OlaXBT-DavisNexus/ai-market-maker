# Hedge Fund Agent Personas

This directory documents every persona node in the OlaXBT multi-agent hedge fund system. Each `.md` file corresponds to one runtime node in the LangGraph workflow.

## Node Types

- **Agent class**: A `BaseAgent` subclass with its own `.py` file in `src/agents/`.
- **Node function**: A stateless function defined in `src/main.py` that operates on the graph state.

## Architecture

```
                    ┌──────────────────────┐
                    │  Policy Orchestrator  │  (n0) Agent class
                    └──────────┬───────────┘
                               │
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
    │  Alpha       │    │  Synthesis   │    │  Governance  │
    │  Desks       │    │              │    │              │
    │ (Tier-0)     │    │ n13 Debate   │    │ n12 Risk     │
    │              │    │    (function) │    │    (agent)   │
    │ n1  Scan     │    │ n14 Signal   │    │ n16 Risk     │
    │ n2  Macro    │    │    Arb       │    │    Guard     │
    │ n3  News     │    │    (function)│    │    (agent)   │
    │ n4  Pattern  │    │ n15 Proposal │    └──────────────┘
    │ n5  OI/Stat  │    │    (function)│
    │ n6  TA       │    │              │    ┌──────────────┐
    │ n7  Retail   │    │ n17 Execute  │    │  Log Step    │
    │ n8  Pro      │    │    (function)│    │ n18 Audit    │
    │ n9  Whale    │    └──────────────┘    │  (function)  │
    │ n10 Liq/Flow │         │              └──────────────┘
    │ n11 Mkt Scan │         │
    └──────────────┘         │
         │                   │
         ▼                   ▼
    ┌──────────────────────────────────┐
    │        All parallel →            │
    │   Risk → Desk Debate → Signal → │
    │   Proposal → Risk Guard → Exec  │
    └──────────────────────────────────┘
```

## Flow

1. **Policy Orchestrator** (n0) selects config preset from memory.
2. **11 Alpha Desks** (n1–n11) run in parallel producing independent signals.
3. **Risk Desk** (n12) produces a risk context snapshot.
4. **Desk Debate** (n13) fuses all outputs into a structured transcript (function).
5. **Signal Arbitrator** (n14) decides final bullish/bearish/neutral stance (function, optional LLM).
6. **Portfolio Proposal** (n15) creates allocation (function).
7. **Risk Guard** (n16) approves or vetoes (agent class).
8. **Execution Desk** (n17) generates orders via CCXT (function).
9. **Audit** (n18) persists run outcome to memory (function).

## File Index

| # | File | Node | Actor | Type | Role |
|---|------|------|-------|------|------|
| 1 | `01_policy_orchestrator.md` | n0 | policy_orchestrator | Agent class | Config/Preset selection |
| 2 | `02_market_scan.md` | n1 | market_scan | Agent class | Exchange scan (CCXT) |
| 3 | `03_monetary_sentinel.md` | n2 | monetary_sentinel | Module fn | Macro economist |
| 4 | `04_news_narrative_miner.md` | n3 | news_narrative_miner | Module fn | Event-driven analyst |
| 5 | `05_pattern_recognition_bot.md` | n4 | pattern_recognition_bot | Module fn | Chart technician |
| 6 | `06_statistical_alpha_engine.md` | n5 | statistical_alpha_engine | Module fn | OI/positioning actuary |
| 7 | `07_technical_ta_engine.md` | n6 | technical_ta_engine | Module fn | TA-Lib indicators |
| 8 | `08_retail_hype_tracker.md` | n7 | retail_hype_tracker | Agent class | Behavioural psychologist |
| 9 | `09_pro_bias_analyst.md` | n8 | pro_bias_analyst | Agent class | Smart-money tracker |
| 10 | `10_whale_behavior_analyst.md` | n9 | whale_behavior_analyst | Agent class | On-chain sentinel |
| 11 | `11_liquidity_order_flow.md` | n10 | liquidity_order_flow | Module fn | Microstructure analyst |
| 12 | `12_risk_desk.md` | n11 | risk | Agent class | Risk snapshot |
| 13 | `13_desk_debate.md` | n12 | desk_debate | Node function | Debate synthesis |
| 14 | `14_signal_arbitrator.md` | n13 | signal_arbitrator | Node function | Final arbitrator |
| 15 | `15_portfolio_proposal.md` | n14 | portfolio_proposal | Node function | Allocation |
| 16 | `16_risk_guard.md` | n15 | risk_guard | Agent class | Veto authority |
| 17 | `17_portfolio_execute.md` | n16 | portfolio_execute | Node function | CCXT order generation |

## Non-Agent Node

| # | File | Node | Actor | Type | Role |
|---|------|------|-------|------|------|
| — | (no doc) | n17 | audit | Log function | Event persistence (not an agent) |

## Key Distinctions

- **Agent classes** (`BaseAgent` subclasses): policy_orchestrator, market_scan, retail_hype_tracker, pro_bias_analyst, whale_behavior_analyst, risk_management (desk), risk_guard.
- **Module-level functions**: monetary_sentinel, news_narrative_miner, pattern_recognition_bot, statistical_alpha_engine, technical_ta_engine, liquidity_order_flow.
- **LangGraph node functions** (in `main.py`): desk_debate, signal_arbitrator, portfolio_proposal, portfolio_execute, audit.
