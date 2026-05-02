# Node: Audit Logger (Log / 審計記錄站)

> **This is NOT an agent.** It is a stateless log step that runs at the end of every workflow cycle.

## Position
The last node in the workflow graph. Persists run outcome to memory.

## What It Does
- **Input**: Final state after Execution or after Risk Guard veto.
- **Process**: Serialises key fields (ticker, veto, execution status, policy decision) → appends to `events.jsonl` via `PolicyMemoryStore`.
- **Output**: Returns a `reasoning_logs` entry (informational only; not consumed by any downstream node).

## Why It Exists
- **Auditability**: Every cycle leaves a persistent trace in `events.jsonl`.
- **Memory for Policy Orchestrator**: The Orchestrator reads memory to decide the next cycle's policy preset.
- **Replay**: Historical `events.jsonl` can be replayed for backtesting and debugging.

## Rules
- Append-only — never modifies past entries.
- Never alters state — read-only on state.
- Has no effects on trading, signals, or execution.
