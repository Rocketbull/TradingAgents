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
- `tradingagents/agents/utils/`: tools exposed to agent workflows
- `tests/`: unit/integration tests

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

## Editing Rules
- Keep ASCII unless file already uses Unicode.
- Avoid broad refactors unless requested.
- Keep changes minimal and consistent with current style.
- For Python/pip/pytest commands, use `.conda/tradingagents/bin/python` and `.conda/tradingagents/bin/pip`.
