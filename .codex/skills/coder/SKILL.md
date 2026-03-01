---
name: coder
description: Implement code changes in TradingAgents. Use when writing or modifying code, adding tests, fixing bugs, and executing targeted validation runs in this repository.
---

# Coder

## Workflow
1. Inspect impacted files and preserve existing architecture boundaries.
2. Implement minimal local changes with clear error handling.
3. Add or update targeted tests for touched behavior.
4. Run focused test commands using repo env binaries.
5. Report exact commands and outcomes.

## Repo Commands
- Install deps: `.conda/tradingagents/bin/pip install -r requirements.txt`
- Run one test file: `.conda/tradingagents/bin/python -m pytest -q tests/test_backtest_engine.py`
- Run focused pair: `.conda/tradingagents/bin/python -m pytest -q tests/test_portfolio_pipeline.py tests/test_backtest_engine.py`
- Run CLI: `.conda/tradingagents/bin/python -m cli.main`

## Guardrails
- Keep changes incremental and avoid broad refactors unless requested.
- Do not add dependencies unless required.
- Keep market data output paths deterministic under `data/market/`.
- Use `rg` for search.
