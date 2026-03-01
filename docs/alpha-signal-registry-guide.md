# Alpha Signal Registry Guide

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
  - `TradingAgentsGraph` -> `AlphaModel.from_config(self.config)`
- Demo script path already uses registry loading:
  - `tools/demo_portfolio_run.py`
- Primary import path:
  - `from tradingagents.alpha import AlphaModel`

## Preset Profiles
You can start from built-in presets:
- `conservative`
- `momentum_heavy`
- `mean_reversion_heavy`
- `risk_on_crypto_anchor`

Example:

```python
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.alpha import apply_alpha_profile

config = DEFAULT_CONFIG.copy()
config = apply_alpha_profile(config, "conservative")
```

Inspect available profiles:

```python
from tradingagents.alpha import list_alpha_profiles, get_alpha_profile

print(list_alpha_profiles())
print(get_alpha_profile("momentum_heavy"))
```

Example using the new profile:

```python
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.alpha import apply_alpha_profile

config = DEFAULT_CONFIG.copy()
config = apply_alpha_profile(config, "risk_on_crypto_anchor")
```

## Extending With a New Alpha Type
1. Add a new `AlphaSignal` subclass in `tradingagents/alpha/signals.py`.
2. Register a builder in `tradingagents/alpha/model.py` (`AlphaModel._init_builders()`) with a new `type` key.
3. Add tests in `tests/test_portfolio_pipeline.py`.
4. Add the new type to this guide.

## Common Errors
- `Unknown alpha signal type`:
  - `type` not registered in `AlphaModel._init_builders()`.
- `Duplicate alpha signal name`:
  - two registry entries used the same `name`.
- `Unknown alpha signals` during rebalance:
  - `alpha_signals` includes names not created by `alpha_signal_registry`.
