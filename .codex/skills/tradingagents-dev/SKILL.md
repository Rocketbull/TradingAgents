---
name: tradingagents-dev
description: Use when working on this TradingAgents repo for market-data tooling, dataflow changes, tests, and safe Python refactors with repo-specific commands and constraints.
---

# TradingAgents Dev Skill

Use this skill for coding tasks in this repository.

## Quick Start
1. Use env binaries from `.conda/tradingagents/bin/`.
2. Install dependencies: `.conda/tradingagents/bin/pip install -r requirements.txt`
3. Run tests: `.conda/tradingagents/bin/python -m pytest -q`
4. Run CLI: `.conda/tradingagents/bin/python -m cli.main`

## Repo Landmarks
- `tools/`: local scripts (market data downloaders, utilities)
- `tradingagents/dataflows/`: vendor/data access and storage
- `tradingagents/alpha/`: alpha signal classes, registry, and IC-based combination
- `tradingagents/portfolio/`: risk/optimizer/rebalance/attribution components
- `tradingagents/backtest/`: backtest engine, accounting, metrics, and local data loader
- `tradingagents/agents/utils/`: tools exposed to agent workflows
- `tests/`: unit/integration tests
- `research/`: repeatable research scripts and shared utilities
- `notebooks/`: viewers for backtest and research outputs

## Market Data Workflow
When asked to add or update market data scripts:
1. Check existing script behavior in `tools/download_market_data.py`.
2. Reuse `tradingagents/dataflows/market_data_store.py` for download/save/load operations.
3. Keep output under `data/market/<SYMBOL>/history_<start>_<end>.parquet`.
4. Preserve metadata sidecar generation (`.json`) for new paths.

## S&P 500 Workflow
For constituent-driven downloads:
1. Use `tools/sp500_symbols.py` to fetch the latest symbols.
2. Normalize Yahoo tickers (`.` to `-`).
3. Prefer combining with downloader `--sp500` and default `--years 5`.

## Testing Guidance
- Run targeted tests first for touched modules, then broader suite if needed.
- For network-dependent tests/scripts, report what could not be fully verified.
- Do not fabricate results; include exact command outcomes.
- For portfolio/backtest changes, run:
  - `.conda/tradingagents/bin/python -m pytest -q tests/test_portfolio_pipeline.py tests/test_backtest_engine.py`

## Portfolio Workflow (Current Baseline)
- Current baseline is benchmark-relative, long-only active construction.
- Backtest engine computes benchmark proxy weights and passes them to optimizer.
- Optimizer supports:
  - `active_weight_cap`
  - optional `tracking_error_target`
- Attribution supports TC diagnostics using pre/post-constraint active weights.

When editing these paths, check:
1. `tradingagents/backtest/engine.py`
2. `tradingagents/portfolio/optimizer.py`
3. `tradingagents/portfolio/attribution.py`
4. `tradingagents/default_config.py`

## Required A/B Protocol After Material Enhancements
For any material model/optimizer/attribution/backtest change:
1. Run matched A/B backtests (pre-change vs post-change) with fixed config + dataset.
2. Save both output dirs under `eval_results/backtest/`.
3. Report key deltas at minimum:
   - `total_return`, `sharpe`, `max_drawdown`
   - `realized_active_information_ratio`
   - turnover decomposition fields
4. Treat this as required, not optional.

## Research Workflow (Repeatable)
- Shared research utilities now live in:
  - `research/common/run_manager.py`
  - `research/common/grinold.py`
- Use config-driven runs and persist:
  - `summary.csv`
  - optional `by_date.csv`
  - `params.json`
  - `manifest.json`
- Prefer reusable viewer notebook:
  - `notebooks/research_run_viewer.ipynb`

## Editing Rules
- Keep ASCII unless file already uses Unicode.
- Avoid broad refactors unless requested.
- Keep changes minimal and consistent with current style.
- For Python/pip/pytest commands, use `.conda/tradingagents/bin/python` and `.conda/tradingagents/bin/pip`.
