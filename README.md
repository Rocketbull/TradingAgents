# Active Portfolio

This repository is now focused on active portfolio management research: local market data workflows, alpha signal experiments, benchmark-relative portfolio construction, and repeatable backtests.

The project started as a fork of TradingAgents. The original TradingAgents code is kept as a pinned git submodule at `vendor/TradingAgents` for reference and future upstream comparison. The active portfolio runtime lives in the `activeportfolio` Python package.

## Repository Layout

- `activeportfolio/alpha/`: alpha signal classes, signal registry, and profile helpers.
- `activeportfolio/portfolio/`: risk model, optimizer, rebalancer, discretionary portfolio helpers, and attribution.
- `activeportfolio/backtest/`: local parquet data loader, accounting, metrics, and backtest engine.
- `activeportfolio/dataflows/`: market data download, local storage, vendor routing, and classification helpers.
- `activeportfolio/regime/`: rule-based regime model for optional alpha/profile routing.
- `activeportfolio/core/`: local technical indicator support.
- `research/`: repeatable research scripts and experiment utilities.
- `tools/`: command-line utilities for data refreshes, backtests, audits, and demos.
- `notebooks/`: viewers for research and backtest outputs.
- `docs/`: runbooks, guides, and implementation plans.
- `vendor/TradingAgents/`: upstream TradingAgents submodule.

## Setup

Use the existing project environment when working in this checkout:

```bash
.conda/tradingagents/bin/pip install -r requirements.txt
.conda/tradingagents/bin/pip install -e .
```

For a fresh environment:

```bash
conda create -n activeportfolio python=3.13
conda activate activeportfolio
pip install -r requirements.txt
pip install -e .
```

Clone with the TradingAgents reference submodule:

```bash
git clone --recurse-submodules <repo-url>
```

Initialize the submodule in an existing checkout:

```bash
git submodule update --init --recursive
```

## Backtest Workflow

Run a configured backtest:

```bash
.conda/tradingagents/bin/python tools/run_backtest.py \
  --config-json research/configs/backtest_csi300_baseline_relaxed.json
```

Run a matched A/B backtest pair:

```bash
.conda/tradingagents/bin/python tools/run_ab_backtest_pair.py \
  --baseline-config research/configs/signal_daily_laggard_band_default.json \
  --candidate-config research/configs/signal_trailing_1y_worst50.json
```

## Market Data Workflows

Refresh the current CSI300 universe:

```bash
.conda/tradingagents/bin/python tools/csi300_symbols.py
```

Download five years of CSI300 A-share history:

```bash
.conda/tradingagents/bin/python tools/download_market_data.py \
  --vendor ashare \
  --symbols-file data/universe/csi300/current/csi300_symbols.txt \
  --years 5 \
  --continue-on-error
```

If technical indicators should use local parquet history instead of online `yfinance`, set:

```python
config["tool_vendors"]["get_indicators"] = "mytt"
config["data_root"] = "data/market"
```

See [docs/guides/csi300-ashare-data-guide.md](docs/guides/csi300-ashare-data-guide.md) for the full A-share workflow and output layout.

## Docs

Start with [docs/README.md](docs/README.md).

Useful guides:

- [Backtest config workflow](docs/guides/backtest-config-workflow.md)
- [Alpha signal registry guide](docs/guides/alpha-signal-registry-guide.md)
- [CSI300 A-share data guide](docs/guides/csi300-ashare-data-guide.md)
- [Active portfolio plan](docs/plans/active-portfolio-plan.md)

## Validation

Run the full test suite:

```bash
.conda/tradingagents/bin/python -m pytest -q
```

Run the portfolio/backtest subset:

```bash
.conda/tradingagents/bin/python -m pytest -q tests/test_portfolio_pipeline.py tests/test_backtest_engine.py
```

## TradingAgents Reference

The original TradingAgents project remains available as a submodule:

```bash
git -C vendor/TradingAgents status
```

Keep active portfolio code in `activeportfolio/`. Use the submodule for reference, comparison, or deliberate upstream sync work.
