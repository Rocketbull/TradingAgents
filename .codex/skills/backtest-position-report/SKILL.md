---
name: backtest-position-report
description: Summarize a TradingAgents single backtest run after completion with latest top 20 positions, previous-month deltas, top additions/removals, and sector rollup.
---

# Backtest Position Report

Use this skill when the user wants the post-run position review for a single backtest, especially:

- top 20 latest positions
- latest vs previous-month deltas
- biggest additions and reductions
- sector rollup after a backtest

## Scope

This skill is for single-run postmortems from saved backtest artifacts under `eval_results/backtest/`.

It reads:

- `weights_history.csv`
- `summary.json`
- `data/market/metadata/yfinance_classification.csv`

## Default Tool

Use:

```bash
<python> tools/backtest_position_report.py
```

If the user names a run explicitly, pass `--run-dir <path>`.

If they do not, let the tool auto-select the latest valid run using actual run dates instead of only file modification times.

## Reporting Rules

Always report:

1. latest trade date
2. previous trade date
3. latest top 20 positions with previous weight and delta
4. biggest increases
5. biggest decreases
6. sector rollup with latest weight, previous weight, and delta

Keep interpretations short and tie them to the reported weights rather than broad claims.
