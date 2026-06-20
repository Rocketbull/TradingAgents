# Flat-Volume Breakout Research Workflow

Document type: user workflow guide.
For the larger implementation roadmap, see `docs/plans/active-portfolio-plan.md`.

This research runner now supports Grinold-style diagnostics and reproducible runs.

## Run with frozen config

```bash
PYTHONPATH=. conda run -n activepm python research/alpha_flat_volume_breakout.py \
  --config-json research/configs/alpha_flat_volume_breakout_default.json \
  --run-tag smoke_grinold_fvb \
  --save-by-date
```

## Key diagnostics in `summary.csv`

- `avg_rank_ic`: cross-sectional rank IC mean
- `ic_std`: IC volatility
- `ic_ir`: IC information ratio proxy (`mean(IC)/std(IC)`)
- `avg_tc_proxy`: transfer coefficient proxy (rank corr of score vs research weights)
- `avg_breadth_proxy`: effective breadth proxy (`1/sum(w^2)`)
- `implied_ir`: Grinold-style implied IR proxy (`IC * sqrt(BR) * TC`)
- `realized_active_ir`: realized active-return IR of the research portfolio

## Reproducibility artifacts

Each run writes to `research/output/<run_tag>/`:

- `summary.csv`: horizon-level metrics
- `by_date.csv`: date-level diagnostics (if `--save-by-date`)
- `params.json`: exact experiment parameters
- `manifest.json`: command, Python version, git SHA, artifact paths

If `--run-tag` is not set, the script creates a deterministic tag from hashed parameters.
