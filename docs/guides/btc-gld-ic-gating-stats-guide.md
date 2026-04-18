# BTC/GLD Risk-On Research: IC Gating Statistics Guide

This note explains the new IC-gating statistics added in `research/common/grinold.py` and how to read them using the BTC/GLD correlation research run.

## Example Run

Run command used:

```bash
PYTHONPATH=. .conda/tradingagents/bin/python research/alpha_btc_gld_correlation.py \
  --start-date 2024-01-01 \
  --end-date 2026-02-12 \
  --universe-source sp500_snapshot \
  --universe-size 500 \
  --corr-lookback-days 120 \
  --top-quantile 0.2 \
  --forward-days 5,20 \
  --weighting-mode long_short \
  --top-k 25 \
  --ic-gate-lookback 26 \
  --ic-gate-min-mean 0.005 \
  --ic-gate-min-tstat 0.5 \
  --ic-gate-min-hit-rate 0.5 \
  --ic-gate-min-samples 12 \
  --save-by-date \
  --run-tag btc_gld_ic_gate_demo \
  --out-dir research/output
```

Artifacts:
- `research/output/btc_gld_ic_gate_demo/summary.csv`
- `research/output/btc_gld_ic_gate_demo/by_date.csv`

## New Summary Fields

Added to each horizon row in `summary.csv`:

- `ic_gate_lookback`
- `ic_gate_min_samples`
- `ic_gate_min_mean`
- `ic_gate_use_abs_mean`
- `ic_gate_min_tstat`
- `ic_gate_min_hit_rate`
- `ic_gate_effective_points`
- `ic_gate_pass_rate`
- `ic_gate_fallback_rate`

Interpretation:

- `ic_gate_pass_rate`: fraction of evaluation dates where trailing IC stats meet configured gate thresholds.
- `ic_gate_fallback_rate`: `1 - pass_rate` (when gate thresholds are active). High value means gate often rejects the signal.
- `ic_gate_effective_points`: number of dates where gate logic is considered active and evaluated.

## New By-Date Fields

Added to `by_date.csv`:

- `ic_hist_n`
- `ic_hist_mean`
- `ic_hist_std`
- `ic_hist_tstat`
- `ic_hist_hit_rate`
- `ic_gate_is_effective`
- `ic_gate_pass`
- `ic_gate_fallback`

Interpretation:

- `ic_hist_*` columns are trailing diagnostics computed from prior IC values (lookback window).
- `ic_gate_pass=1` means the date passes all configured IC gate checks.
- `ic_gate_fallback=1` means the date fails the configured gate checks.

## How To Read The Demo Results

From `btc_gld_ic_gate_demo/summary.csv`:

- Horizon 5:
  - `avg_rank_ic=-0.0249`, `ic_ir=-0.1271`
  - `ic_gate_pass_rate=0.2848`, `ic_gate_fallback_rate=0.7152`
- Horizon 20:
  - `avg_rank_ic=-0.0566`, `ic_ir=-0.3044`
  - `ic_gate_pass_rate=0.3210`, `ic_gate_fallback_rate=0.6790`

Reading:

1. IC is negative on average in this window for both horizons.
2. Gate pass rate is low (~28% to 32%), so most dates fail gate criteria.
3. High fallback rate indicates this signal is not IC-stable under current thresholds and sample window.
