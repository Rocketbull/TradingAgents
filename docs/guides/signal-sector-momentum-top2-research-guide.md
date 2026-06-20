# Signal Research Guide: Sector Momentum Top-2

This research combines:

- Repo-native diagnostics (`GrinoldDiagnostics`)
- Alphalens diagnostics

for the signal built from:

- 3M momentum (`63` trading days),
- top-2 names per sector,
- monthly rebalance schedule.

## 1) Run Combined Signal Research

```bash
conda run -n activepm python research/signal_sector_momentum_top2.py \
  --start-date 2021-03-01 \
  --end-date 2026-02-28 \
  --universe-source sp500_snapshot \
  --universe-size 500 \
  --symbol-file data/universe/sp500/current/sp500_symbols.txt \
  --snapshot-dir data/universe/sp500/snapshots \
  --data-root data/market \
  --fundamentals-dir data/fundamentals/sp500 \
  --top-k-per-sector 2 \
  --momentum-lookback-days 63 \
  --forward-steps 1,2,4 \
  --alphalens-periods 21,63 \
  --run-tag sig_sector_mom_top2_demo \
  --out-dir research/output \
  --save-factor-data
```

Outputs under `research/output/<run_tag>/`:

- `repo_summary.csv`
- `repo_by_date.csv` (if generated)
- `alphalens_summary.csv`
- `alphalens_ic_by_date.csv`
- `alphalens_mean_return_by_quantile.csv`
- `alphalens_std_error_by_quantile.csv`
- `alphalens_turnover_autocorr.csv`
- optional `factor_data.parquet`
- `params.json`
- `manifest.json`

## 2) Notebook Viewer (Generic)

Open:

- `notebooks/signal_research_viewer.ipynb`

Features:

- auto-detects compatible signal-research run directories
- side-by-side repo diagnostics and Alphalens summary plots
- optional time-series view from `repo_by_date.csv` or `by_date.csv`

## 3) Optional Tearsheet Notebook

If `factor_data.parquet` is present, you can also use:

- `notebooks/alphalens_tearsheet_viewer.ipynb`

for full tear-sheet plots and optional PNG export.
