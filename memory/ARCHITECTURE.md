# Architecture Memory

## Module Landmarks
- `tools/`: local scripts such as market data downloaders and utilities.
- `activeportfolio/dataflows/`: vendor/data access and storage.
- `activeportfolio/alpha/`: alpha signal classes, registry, and IC-based combination.
- `activeportfolio/portfolio/`: risk, optimizer, rebalance, and attribution components.
- `activeportfolio/backtest/`: backtest engine, accounting, metrics, and local data loader.
- `activeportfolio/regime/`: rule-based regime model for optional alpha/profile routing.
- `activeportfolio/core/`: local technical indicator support.
- `vendor/TradingAgents/`: original TradingAgents repository pinned as a git submodule for reference.
- `research/`: repeatable research scripts and shared utilities.
- `notebooks/`: viewers for backtest and research outputs.
- `tests/`: unit and integration tests.

## Data And I/O Rules
- Market data output belongs under `data/market/`.
- Keep `data/` contents out of git except placeholders and metadata.
- For new downloader behavior, maintain deterministic output paths.
- Existing market history paths use `data/market/<SYMBOL>/history_<start>_<end>.parquet`.
- Preserve metadata sidecar generation for new market data paths.

## Portfolio Baseline
- Current baseline is benchmark-relative, long-only active construction.
- Backtest engine computes benchmark proxy weights and passes them to optimizer.
- Optimizer supports `active_weight_cap` and optional `tracking_error_target`.
- Attribution supports TC diagnostics using pre/post-constraint active weights.

For portfolio/backtest changes, inspect:
1. `activeportfolio/backtest/engine.py`
2. `activeportfolio/portfolio/optimizer.py`
3. `activeportfolio/portfolio/attribution.py`
4. `activeportfolio/default_config.py`
