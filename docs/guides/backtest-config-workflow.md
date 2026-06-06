# Backtest Config Workflow

Document type: user workflow guide.
For roadmap and implementation status, see `docs/plans/active-portfolio-plan.md`.

## Purpose
Use this workflow to run repeatable backtests from repo-tracked config files and to keep clear separation between:

1. alpha-profile promotion, and
2. full backtest baseline promotion.

## Config Precedence
For `tools/run_backtest.py`, effective settings are applied in this order:

1. `activeportfolio/default_config.py`
2. `--config-json <file>`
3. explicit CLI flags

This means a reusable JSON file can define the baseline, while a one-off CLI command can override only the fields you want to change.

## Current Reusable Baseline
The current repo-tracked full backtest baseline is:

- `research/configs/backtest_current_baseline.json`

It captures the stronger monthly, snapshot-aware, liquidity-filtered SP500 setup promoted from the saved A/B run.

## How To Run One Config

Run the current baseline exactly as saved:

```bash
.conda/tradingagents/bin/python tools/run_backtest.py \
  --config-json research/configs/backtest_current_baseline.json
```

Override only the date window:

```bash
.conda/tradingagents/bin/python tools/run_backtest.py \
  --config-json research/configs/backtest_current_baseline.json \
  --start-date 2022-01-01 \
  --end-date 2026-03-21
```

Override one constraint while keeping the rest of the baseline:

```bash
.conda/tradingagents/bin/python tools/run_backtest.py \
  --config-json research/configs/backtest_current_baseline.json \
  --max-weight 0.06 \
  --turnover-limit 0.35
```

## How To Run A/B Tests With Different Configs
`tools/run_ab_backtest_pair.py` already supports separate config files for both sides.

Example:

```bash
.conda/tradingagents/bin/python tools/run_ab_backtest_pair.py \
  --pair-name baseline_vs_candidate \
  --start-date 2021-03-01 \
  --end-date 2026-02-28 \
  --config-a-json research/configs/backtest_current_baseline.json \
  --config-b-json research/configs/backtest_candidate.json \
  --label-a current_baseline \
  --label-b candidate
```

Notes:
- Both config files are merged onto `DEFAULT_CONFIG`.
- The A/B runner rewrites `backtest_output_dir` for each run automatically.
- Warmup-aware start-date adjustment is handled inside the runner.

## Two Levels Of Promotion

### Level 1: Promote An Alpha Profile
Use this when you want to standardize only the alpha signal mix and alpha-layer settings.

Where:
- `activeportfolio/alpha/profiles.py`

What it changes:
- `alpha_signal_registry`
- `alpha_signals`
- alpha weighting knobs such as `alpha_corr_penalty`

What it does not change:
- universe construction
- rebalance cadence
- optimizer constraints
- benchmark/risk settings

This is the right level when the alpha idea should be reusable across many backtests.

### Level 2: Promote A Full Backtest Baseline
Use this when you want to standardize the whole research setup, not just the alpha mix.

Where:
- repo-tracked JSON under `research/configs/`

What it can change:
- alpha profile/registry
- universe source and size
- snapshot scheduling
- liquidity filter settings
- rebalance cadence
- portfolio constraints
- benchmark-relative controls
- output path defaults

This is the right level when you want repeatable portfolio/backtest runs with one named setup.

## When To Edit `DEFAULT_CONFIG`
Treat `DEFAULT_CONFIG` as the framework-wide fallback, not the place for every research baseline.

Only move settings into `activeportfolio/default_config.py` when you want them to become the general repo default for most runs.

In most cases:
- alpha-only standardization -> promote to `activeportfolio/alpha/profiles.py`
- full research baseline -> save JSON under `research/configs/`
- framework-wide default behavior change -> update `activeportfolio/default_config.py`

## How Alpha Weighting Works

The backtest engine does not treat every configured signal equally. It computes each signal cross-sectionally, measures how that signal has performed recently, then combines signals with IC-aware weighting inside `AlphaModel.ic_weighted_alpha()`.

Relevant code:
- `activeportfolio/alpha/model.py`
- `activeportfolio/backtest/engine.py`

At each rebalance, the engine:

1. Computes raw component scores for each signal in `alpha_signal_registry`.
2. Standardizes them cross-sectionally.
3. Looks up trailing realized IC history for each signal.
4. Builds signal weights from those trailing IC statistics.
5. Applies IC gates, correlation penalties, max-weight caps, and smoothing before combining the signals into one alpha score.

The main per-signal diagnostics are:

- `mean_ic`: trailing average information coefficient for that signal.
- `ic_hit_rate`: fraction of trailing observations where IC was positive.
- `ic_tstat`: trailing IC mean scaled by its dispersion and sample count.
- `ic_n`: number of usable trailing IC observations.

In `weighting_mode="positive"`, negative trailing IC is clipped to zero before the remaining weighting logic is applied. In `weighting_mode="signed"`, negative mean IC can remain negative and contribute with sign.

## What The IC Gate Does

The IC gate is a pre-filter on signal weights. A signal that fails the gate has its base signal weight set to zero before correlation penalty and normalization.

This is useful when a signal is present in the registry but has weak recent evidence. Without a gate, weak signals can still pollute the mix just by existing. With a gate, only signals that clear recent quality thresholds are allowed to compete for weight.

The key config knobs are:

- `ic_gate_min_mean`: minimum trailing mean IC required for the signal to stay active.
- `ic_gate_use_abs_mean`: if `true`, compare `abs(mean_ic)` to the threshold instead of signed mean IC.
- `ic_gate_min_tstat`: minimum trailing IC t-stat required.
- `ic_gate_min_hit_rate`: minimum share of positive IC observations required.
- `ic_gate_min_samples`: minimum number of trailing IC observations required before significance-style gates are allowed to pass.

Behavior notes:

- If `ic_gate_min_mean` is set, the signal must clear that mean-IC threshold.
- If `ic_gate_min_tstat` or `ic_gate_min_hit_rate` is set, the signal must also have at least `ic_gate_min_samples` observations.
- If all signals are gated out, the combiner falls back to equal nonzero base weights as a safety mechanism instead of producing a dead portfolio.

Plain-English interpretation:

- `min_mean`: "is this signal good enough on average?"
- `min_hit_rate`: "is it good often enough?"
- `min_tstat`: "is the evidence strong enough to trust?"
- `min_samples`: "do we have enough history to judge it at all?"

## Example: Why Gated Volume-Confirmed Momentum Helped

The recent SP500 baseline experiments are a useful example for new researchers.

Baseline config:
- `research/configs/backtest_current_baseline.json`

Stronger candidate family:
- `research/configs/backtest_current_baseline_vol_confirmed_for_breakout_gate.json`
- `research/configs/backtest_current_baseline_vol_confirmed_for_breakout_gate_smooth035.json`
- `research/configs/backtest_current_baseline_vol_confirmed_for_breakout_gate_te009.json`

What changed relative to the baseline:

- Removed `breakout_52w`.
- Added `vol_confirmed_mom_1m`.
- Raised `alpha_corr_penalty`.
- Lowered `alpha_max_signal_weight`.
- Turned on IC gating.

Why that can help:

- `vol_confirmed_mom_1m` only rewards short-horizon momentum when volume is expanding, so it is not just another plain momentum window.
- The gate shuts off weak sleeves when their recent IC evidence is poor.
- Higher correlation penalty and lower max signal weight reduce crowding among very similar momentum sleeves.
- Additional smoothing can stabilize signal-weight changes from one rebalance to the next.

For this reason, a gated replacement can outperform a larger ungated momentum stack even when the raw set of signals looks smaller or more restrictive.

## Recommended Workflow

1. Start from `research/configs/backtest_current_baseline.json`.
2. Copy it to a new candidate JSON under `research/configs/`.
3. Change only the fields you are testing.
4. Run `tools/run_ab_backtest_pair.py` with both files.
5. Promote:
   - to `alpha/profiles.py` if only the alpha layer should become standard,
   - or replace the baseline JSON if the full setup should become the new baseline.
