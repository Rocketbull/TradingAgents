# Worklog

Use this file for compact task history that may help future agents understand recent context. Keep entries short and factual.

## 2026-04-17
- Created a project memory structure under `memory/`.
- Replaced `AGENTS.md` with a compact agent operating guide.
- Added `scripts/reflect.py` and `scripts/memory_guard.py`.
- Cleaned `coder` and `reviewer` skills so durable project facts live in memory.
- Refreshed `research/output/xlk_xle_quarterly_50_50` through requested end date `2026-04-17` after downloading XLK/XLE market data for `2021-03-01..2026-04-17`.

## 2026-06-13
- Refreshed the `baseline_vs_defensive_sleeve_v2` A/B backtest through `2026-06-10`; defensive sleeve v2 beat baseline on total return, Sharpe, drawdown, and tracking error.
- Added `tools/build_backtest_index.py` plus `research/configs/backtest_decisions.json` to index backtest history and track manual keep/candidate/rejected config decisions.

## 2026-07-17
- Refreshed S&P 500 membership and five-year S&P/ETF market data for `2021-07-17..2026-07-17`; spot checks showed latest market rows through `2026-07-16`.
- Rebuilt SPY fragility dashboard data through `2026-07-16`; latest regime was `normal`.
- Reran `current_baseline` and `current_baseline_defensive_sleeve_v2` backtests with end date `2026-07-17` and rebuilt the backtest index.
- Split the single backtest viewer workflow into baseline and development notebooks, with shared run discovery/loading helpers in `research/common/backtest_viewer.py`.
