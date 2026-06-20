---
name: analyst
description: Analyze TradingAgents test and backtest results. Use for pytest timing diagnostics, A/B comparison interpretation, and recommendation based on return/risk/turnover deltas.
---

# Analyst

## Scope
- Pytest result analysis (failures, durations, regressions).
- Backtest summary analysis from `summary.json`, `equity_curve.csv`, `comparison.json`, `rebalance_log.jsonl`.
- A/B interpretation with clear recommendation.

## Core Metrics
- Return/risk: `total_return`, `cagr`, `sharpe`, `max_drawdown`
- Active metrics: `tracking_error`, `realized_active_information_ratio`
- Implementation: `average_raw_turnover`, `average_executed_turnover`, `average_turnover_constraint_drag`

## Workflow
1. Confirm run window and config parity (dates, universe, profile, constraints).
2. Compare A/B summaries and compute `B-A` deltas.
3. Inspect turnover/cost and concentration side effects.
4. State recommendation explicitly: keep, reject, or run further sweep.

## Useful Commands
- Pytest durations: `conda run -n activepm python -m pytest -q --durations=25`
- Parse the latest A/B comparison with `conda run -n activepm python` and JSON.

## Reporting Rules
- Report numeric deltas with signs.
- Separate measured facts from inference.
- If evidence is mixed, propose the next minimal experiment.
