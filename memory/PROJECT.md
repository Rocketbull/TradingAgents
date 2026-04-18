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
- Dependency install command: `.conda/tradingagents/bin/pip install -r requirements.txt`.
- Optional editable install: `.conda/tradingagents/bin/pip install -e .`.

## Agent Skills
- `coder`: implementation, tests, dataflow, research workflow changes, and validation.
- `reviewer`: design, architecture, regression risk, and test coverage review.
- `analyst`: pytest and backtest result analysis.
- `tradingagents-test-performance-diagnostics`: slow or regressed pytest diagnostics.
