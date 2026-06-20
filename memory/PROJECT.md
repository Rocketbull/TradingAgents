# Project Memory

## Purpose
Active Portfolio is a Python project for market data workflows, alpha research, portfolio construction, backtesting, and repeatable analysis. The original TradingAgents project is retained as a reference submodule under `vendor/TradingAgents`.

## Development Priorities
- Prefer local and incremental changes.
- Preserve existing architecture and module boundaries.
- Avoid new dependencies unless the task cannot be solved cleanly without them.
- Keep market data outputs deterministic and reproducible.
- Validate touched behavior with targeted tests.

## Environment
- Python requirement: `>=3.10`.
- Use project environment binaries directly from `.conda/tradingagents/bin/`.
- If `.conda/tradingagents/bin/` is missing in the current checkout, use the validated fallback interpreter at `/home/rockebull/miniconda3/envs/tradingagents/bin/python`.
- When the fallback path is needed once in a task, reuse it for the rest of the repo work instead of re-probing interpreters.
- Dependency install command: `.conda/tradingagents/bin/pip install -r requirements.txt`.
- Optional editable install: `.conda/tradingagents/bin/pip install -e .`.

## Agent Skills
- `coder`: implementation, tests, dataflow, research workflow changes, and validation.
- `reviewer`: design, architecture, regression risk, and test coverage review.
- `analyst`: pytest and backtest result analysis.
- `backtest-position-report`: latest top 20 holdings, month-over-month deltas, additions/removals, and sector rollup for a saved backtest run.
- `monthly-investor-commentary`: on-demand GenAI investor commentary using the latest completed one-month run context plus live market/news research.
- `refresh-market-data`: refresh recurring `sp500` and `a300`/`csi300` universe files plus local `data/market/` histories.
- `tradingagents-test-performance-diagnostics`: slow or regressed pytest diagnostics.
