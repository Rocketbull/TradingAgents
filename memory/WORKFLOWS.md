# Workflow Memory

## Common Commands
- Run CLI: `.conda/tradingagents/bin/python -m cli.main`
- Run quick script: `.conda/tradingagents/bin/python main.py`
- Run tests: `.conda/tradingagents/bin/python -m pytest -q`
- Run one test: `.conda/tradingagents/bin/python -m pytest -q tests/test_y_finance_history.py`
- Run portfolio/backtest tests: `.conda/tradingagents/bin/python -m pytest -q tests/test_portfolio_pipeline.py tests/test_backtest_engine.py`

## Validation Before Handoff
- Run targeted tests for touched modules.
- Broaden tests when shared behavior, portfolio accounting, or dataflow contracts change.
- If tests cannot run due to missing external dependencies, network, data, or keys, state that clearly.
- Do not fabricate test or backtest results.

## Market Data Workflow
When adding or updating market data scripts:
1. Check existing script behavior in `tools/download_market_data.py`.
2. Reuse `tradingagents/dataflows/market_data_store.py` for download/save/load operations.
3. Keep output under deterministic `data/market/` paths.

## S&P 500 Workflow
For constituent-driven downloads:
1. Use `tools/sp500_symbols.py` to fetch symbols.
2. Normalize Yahoo tickers by converting `.` to `-`.
3. Prefer combining with downloader `--sp500` and default `--years 5`.

## A/B Protocol
For model, optimizer, attribution, or backtest logic changes that can affect portfolio outputs:
1. Run matched A/B backtests with fixed config and dataset.
2. Save both output dirs under `eval_results/backtest/`.
3. Report at least `total_return`, `sharpe`, `max_drawdown`, `realized_active_information_ratio`, and turnover decomposition fields.

Docs, tests, pure refactors with no behavior change, and mechanical typing changes do not require A/B backtests.
