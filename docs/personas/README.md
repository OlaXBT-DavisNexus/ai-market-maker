# Hedge Fund Agent Personas

This directory documents every agent persona in the OlaXBT multi-agent hedge fund system. Each `.md` file corresponds to one runtime agent node.

## Architecture

```
                    ┌──────────────────────┐
                    │  Policy Orchestrator  │  (n0)
                    └──────────┬───────────┘
                               │
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
    ┌──────────┐       ┌──────────────┐     ┌──────────────┐
    │ Alpha    │       │  Execution   │     │  Governance  │
    │ Desks    │       │  Desks       │     │  Layer       │
    ├──────────┤       ├──────────────┤     ├──────────────┤
    │ n1  Scan │       │ n11 Liquidity│     │ n12 Risk     │
    │ n3  News │       │              │     │     Desk     │
    │ n4  Patt │       │              │     │ n15 Risk     │
    │ n5  Stat │       │              │     │     Guard    │
    │ n6  Tech │       │              │     │ n0  Policy   │
    │ n7  Hype │       │              │     │              │
    │ n8  Pro  │       │              │     └──────────────┘
    │ n9  Whale│       │              │
    │ n10 Flow │       │              │     ┌──────────────┐
    │ n2  Macr │       │              │     │ Observability│
    └──────────┘       └──────────────┘     ├──────────────┤
          │                                  │ n17 Audit   │
          ▼                                  └──────────────┘
    ┌──────────────┐
    │  Synthesis   │
    │ n12 Desk     │
    │     Debate   │
    │ n13 Signal   │
    │     Arb      │
    │ n14 Portfolio│
    │     Proposal │
    ├──────────────┤
    │ n16 Exec     │
    └──────────────┘
```

## Flow

1. **Policy Orchestrator** triggers a market cycle.
2. **Alpha Desks** (n1–n10) produce independent signals and reports.
3. **Risk Desk** (n11) produces a risk snapshot.
4. **Desk Debate** (n12) fuses all research into one memo.
5. **Signal Arbitrator** (n13) decides final stance.
6. **Portfolio Proposal** (n14) creates an allocation.
7. **Risk Guard** (n15) approves or vetoes.
8. **Execution Desk** (n16) produces exchange orders.
9. **Audit** (n17) records everything.

## File Index

| # | File | Node | Actor | Role |
|---|------|------|-------|------|
| 1 | `01_policy_orchestrator.md` | n0 | policy_orchestrator | Governance |
| 2 | `02_market_scan.md` | n1 | market_scan | Alpha: Momentum/Listings |
| 3 | `03_monetary_sentinel.md` | n2 | monetary_sentinel | Alpha: Macro |
| 4 | `04_news_narrative_miner.md` | n3 | news_narrative_miner | Alpha: Media |
| 5 | `05_pattern_recognition_bot.md` | n4 | pattern_recognition_bot | Alpha: Chart Patterns |
| 6 | `06_statistical_alpha_engine.md` | n5 | statistical_alpha_engine | Alpha: Pair Trading |
| 7 | `07_technical_ta_engine.md` | n6 | technical_ta_engine | Alpha: Indicators |
| 8 | `08_retail_hype_tracker.md` | n7 | retail_hype_tracker | Alpha: Social |
| 9 | `09_pro_bias_analyst.md` | n8 | pro_bias_analyst | Alpha: KOL |
| 10 | `10_whale_behavior_analyst.md` | n9 | whale_behavior_analyst | Alpha: On-Chain |
| 11 | `11_liquidity_order_flow.md` | n10 | liquidity_order_flow | Execution Support |
| 12 | `12_risk_desk.md` | n11 | risk | Governance: Risk Context |
| 13 | `13_desk_debate.md` | n12 | desk_debate | Synthesis |
| 14 | `14_signal_arbitrator.md` | n13 | signal_arbitrator | Decision |
| 15 | `15_portfolio_proposal.md` | n14 | portfolio_proposal | Allocation |
| 16 | `16_risk_guard.md` | n15 | risk_guard | Governance: Veto |
| 17 | `17_execution_desk.md` | n16 | portfolio_execute | Broker |
| 18 | `18_audit_logger.md` | n17 | audit | Log Step (not an agent) |
