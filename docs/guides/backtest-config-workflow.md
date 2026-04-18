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

## Recommended Workflow

1. Start from `research/configs/backtest_current_baseline.json`.
2. Copy it to a new candidate JSON under `research/configs/`.
3. Change only the fields you are testing.
4. Run `tools/run_ab_backtest_pair.py` with both files.
5. Promote:
   - to `alpha/profiles.py` if only the alpha layer should become standard,
   - or replace the baseline JSON if the full setup should become the new baseline.
