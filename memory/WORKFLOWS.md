# Workflow Memory

## Common Commands
- Run backtest: `conda run -n activepm python tools/run_backtest.py --config-json <config>`
- Run A/B backtest pair: `conda run -n activepm python tools/run_ab_backtest_pair.py --baseline-config <config> --candidate-config <config>`
- Build backtest history index: `conda run -n activepm python tools/build_backtest_index.py`
- Run tests: `conda run -n activepm python -m pytest -q`
- Run one test: `conda run -n activepm python -m pytest -q tests/test_y_finance_history.py`
- Run portfolio/backtest tests: `conda run -n activepm python -m pytest -q tests/test_portfolio_pipeline.py tests/test_backtest_engine.py`

## Validation Before Handoff
- Run targeted tests for touched modules.
- Broaden tests when shared behavior, portfolio accounting, or dataflow contracts change.
- If tests cannot run due to missing external dependencies, network, data, or keys, state that clearly.
- Do not fabricate test or backtest results.

## Market Data Workflow
When adding or updating market data scripts:
1. Check existing script behavior in `tools/download_market_data.py`.
2. Reuse `activeportfolio/dataflows/market_data_store.py` for download/save/load operations.
3. Keep output under deterministic `data/market/` paths.

## S&P 500 Workflow
For constituent-driven downloads:
1. Use `tools/sp500_symbols.py` to fetch symbols.
2. Normalize Yahoo tickers by converting `.` to `-`.
3. Prefer combining with downloader `--sp500` and default `--years 5`.

## Benchmark ETF Workflow
For benchmark and regime context symbols:
1. Keep the tracked ETF seed list in `data/universe/etf/current/etf_symbols.txt`.
2. Refresh ETF history with `tools/download_market_data.py --symbols-file data/universe/etf/current/etf_symbols.txt`.
3. Include `SPY` at minimum so backtest benchmark/calendar data does not lag the main equity universe.

## A/B Protocol
For model, optimizer, attribution, or backtest logic changes that can affect portfolio outputs:
1. Run matched A/B backtests with fixed config and dataset.
2. Save both output dirs under `eval_results/backtest/`.
3. Report at least `total_return`, `sharpe`, `max_drawdown`, `realized_active_information_ratio`, and turnover decomposition fields.

Docs, tests, pure refactors with no behavior change, and mechanical typing changes do not require A/B backtests.
