# Alpha Signal Registry Guide

Document type: user workflow guide.
For full backtest-baseline promotion and config-file workflow, see `docs/guides/backtest-config-workflow.md`.

## Purpose
Use `alpha_signal_registry` to define alpha signals from config instead of editing Python code.

If `alpha_signal_registry` is non-empty, `AlphaModel.from_config(...)` builds signals from it.
If it is empty, the built-in default signal set is used.

## Config Keys
- `alpha_signal_registry`: full signal definitions (type + params).
- `alpha_signals`: subset selection used during backtest rebalance.
  - Keep names in `alpha_signals` aligned with names produced by the registry.

## Supported Signal Types
- `momentum`: params `name`, `window`
- `reversal`: params `name`, `window`
- `low_vol`: params `name`, `window`
- `downside_vol`: params `name`, `window`
- `trend`: params `name`, `long_window`, `short_window`
- `breakout`: params `name`, `window`
- `vol_adj_momentum`: params `name`, `momentum_window`, `vol_window`
- `range_position`: params `name`, `window`
- `volume_shock`: params `name`, `price_window`, `vol_short_window`, `vol_long_window`
- `sector_momentum_top2`: params
  - `name`, `momentum_window` (default `63`)
  - `top_k_per_sector` (default `2`)
  - `sector_classification_cache` (default `data/market/metadata/yfinance_classification.csv`)
  - `fundamentals_csv` (optional path to fundamentals CSV with `symbol,sector`)
  - `min_sector_coverage` (default `0.70`)
- `btc_gld_corr`: params
  - `name`, `lookback_window` (default `120`)
  - `risk_symbol` (default `BTC-USD`)
  - `defensive_symbol` (default `GLD`)
  - `defensive_weight` (default `1.0`)
  - `risk_weight` (default `1.0`)
  - `flip_sign` (default `true`, preferred from research A/B)

All types support:
- `enabled` (optional, default `true`)

## Example: Custom Registry
Add this to your config (for example in a script before creating `BacktestEngine`):

```python
config["alpha_signal_registry"] = [
    {"type": "momentum", "name": "mom_1m", "window": 21},
    {"type": "momentum", "name": "mom_3m", "window": 63},
    {"type": "reversal", "name": "rev_1w", "window": 5},
    {"type": "low_vol", "name": "low_vol_3m", "window": 63},
    {"type": "trend", "name": "trend_12m_1m", "long_window": 252, "short_window": 21},
]

config["alpha_signals"] = [
    "mom_1m",
    "mom_3m",
    "rev_1w",
    "low_vol_3m",
    "trend_12m_1m",
]
```

## Runtime Usage
- Backtest path already uses registry loading:
  - `BacktestEngine` -> `AlphaModel.from_config(self.config)`
- Portfolio graph path already uses registry loading:
  - legacy `TradingAgentsGraph` integration -> `AlphaModel.from_config(self.config)`
- Demo script path already uses registry loading:
  - `tools/demo_portfolio_run.py`
- Backtest runner:
  - `tools/run_backtest.py`
- Primary import path:
  - `from activeportfolio.alpha import AlphaModel`

## Single-Alpha Run
To force a single alpha in backtest:

```python
config["alpha_signal_registry"] = [
    {
        "type": "sector_momentum_top2",
        "name": "sec_mom_top2",
        "momentum_window": 63,
        "top_k_per_sector": 2,
        "sector_classification_cache": "data/market/metadata/yfinance_classification.csv",
    }
]
config["alpha_signals"] = ["sec_mom_top2"]
```

CLI usage (single alpha selection by name):

```bash
.conda/tradingagents/bin/python tools/run_backtest.py \
  --start-date 2024-01-01 \
  --end-date 2025-12-31 \
  --alpha-signal sec_mom_top2
```

## Preset Profiles
You can start from built-in presets:
- `conservative`
- `momentum_heavy`
- `mean_reversion_heavy`
- `risk_on_crypto_anchor`
- `diversified_sp500_v1`

This is the alpha-only promotion layer.
If you want to promote a full backtest setup instead of just the signal mix, see:

- `docs/guides/backtest-config-workflow.md`

Example:

```python
from activeportfolio.default_config import DEFAULT_CONFIG
from activeportfolio.alpha import apply_alpha_profile

config = DEFAULT_CONFIG.copy()
config = apply_alpha_profile(config, "conservative")
```

Inspect available profiles:

```python
from activeportfolio.alpha import list_alpha_profiles, get_alpha_profile

print(list_alpha_profiles())
print(get_alpha_profile("momentum_heavy"))
```

Example using the new profile:

```python
from activeportfolio.default_config import DEFAULT_CONFIG
from activeportfolio.alpha import apply_alpha_profile

config = DEFAULT_CONFIG.copy()
config = apply_alpha_profile(config, "diversified_sp500_v1")
```

## Backtest Config Files
For full engine/backtest promotion, use repo-tracked JSON config files and run:

```bash
.conda/tradingagents/bin/python tools/run_backtest.py \
  --config-json research/configs/backtest_current_baseline.json
```

`--config-json` is the full backtest promotion layer:
- alpha profile/registry
- universe and snapshot settings
- liquidity filter
- rebalance cadence
- optimizer/risk constraints

CLI flags still override the JSON file when you need one-off changes.

## Research Script (SP500)
Use the profile research runner to evaluate per-factor and composite diagnostics on SP500 universe snapshots:

```bash
.conda/tradingagents/bin/python research/alpha_profile_sp500.py \
  --config-json research/configs/alpha_profile_sp500_diversified_v1.json
```

## Alphalens Adapter
For standard factor tear-sheet diagnostics (IC, quantiles, turnover/autocorr), use:

```bash
.conda/tradingagents/bin/python research/alpha_alphalens_adapter.py \
  --config-json research/configs/alpha_alphalens_mom3m_sample.json
```

Then render tearsheet figures:

```bash
.conda/tradingagents/bin/python research/alpha_alphalens_tearsheet.py \
  --factor-data research/output/<run_tag>/factor_data.parquet \
  --out-dir research/output/<run_tag>/tearsheet_png
```

See also: `docs/guides/alphalens-research-workflow.md`.

## Extending With a New Alpha Type
1. Add a new `AlphaSignal` subclass in `activeportfolio/alpha/signals.py`.
2. Register a builder in `activeportfolio/alpha/model.py` (`AlphaModel._init_builders()`) with a new `type` key.
3. Add tests in `tests/test_portfolio_pipeline.py`.
4. Add the new type to this guide.

## Common Errors
- `Unknown alpha signal type`:
  - `type` not registered in `AlphaModel._init_builders()`.
- `Duplicate alpha signal name`:
  - two registry entries used the same `name`.
- `Unknown alpha signals` during rebalance:
  - `alpha_signals` includes names not created by `alpha_signal_registry`.

## Signal Lifecycle Policy
Use this policy before removing signals from the registry.

1. Monitor:
- Track per-signal behavior from backtest logs:
  - `signal_ic` (cross-sectional IC by rebalance),
  - `alpha_weights` (effective allocation share),
  - per-signal diagnostics from `tools/alpha_signal_audit.py`.

2. Dynamic control first:
- Prefer IC weighting/gating to reduce weak signals before hard deletion.
- Keep `ic_gate_*` configurable and default conservative unless A/B confirms benefit.

3. Quarantine rule:
- If a signal shows persistently negative evidence across multiple windows
  (for example negative IC-IR and negative realized contribution proxy), move it to a
  quarantine profile instead of deleting immediately.

4. Remove only after matched A/B:
- Remove from `alpha_signal_registry` only when matched A/B tests with fixed data/config
  show stable improvement in key metrics (Sharpe, active IR, drawdown/turnover tradeoff).

5. Re-entry checks:
- Periodically re-test quarantined/removed signals because regime changes can restore usefulness.
