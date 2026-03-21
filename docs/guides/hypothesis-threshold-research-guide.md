# Hypothesis + Threshold Sweep Guide

This guide covers:

1. `research/hypothesis_analysis.py` (single hypothesis run)
2. `research/threshold_sweep.py` (parameter sweep)
3. `tools/demo_hypothesis_threshold.py` (demo runner for both)

## Environment

Use project Python:

```bash
.conda/tradingagents/bin/python --version
```

All examples below assume execution from repo root.

## 1) Run Hypothesis Analysis

Example:

```bash
.conda/tradingagents/bin/python research/hypothesis_analysis.py \
  --start-date 2024-01-01 \
  --end-date 2025-12-31 \
  --spy-symbol SPY \
  --lead-symbol TSLA \
  --spy-threshold-pct -0.25 \
  --lead-threshold-pct 1.5 \
  --next-spy-drop-pct -1.0 \
  --run-tag demo_hypothesis \
  --output-dir research/output
```

Outputs:

- `research/output/demo_hypothesis/summary.csv`
- `research/output/demo_hypothesis/signal_days.csv`
- `research/output/demo_hypothesis/params.json`
- `research/output/demo_hypothesis/manifest.json`

## 2) Run Threshold Sweep

Example:

```bash
.conda/tradingagents/bin/python research/threshold_sweep.py \
  --start-date 2024-01-01 \
  --end-date 2025-12-31 \
  --spy-symbol SPY \
  --lead-symbol TSLA \
  --spy-thresholds-pct=-0.50,-0.25,0.00 \
  --lead-thresholds-pct=0.50,1.00,1.50 \
  --next-spy-drop-thresholds-pct=-1.50,-1.00,-0.50 \
  --min-signal-days 20 \
  --run-tag demo_threshold_sweep \
  --output-dir research/output
```

Outputs:

- `research/output/demo_threshold_sweep/summary.csv`
- `research/output/demo_threshold_sweep/params.json`
- `research/output/demo_threshold_sweep/manifest.json`

## 3) Run Combined Demo (Both Features)

This runs both scripts with one command and fixed demo defaults:

```bash
.conda/tradingagents/bin/python tools/demo_hypothesis_threshold.py \
  --start-date 2024-01-01 \
  --end-date 2025-12-31 \
  --run-tag-prefix demo_hypothesis_threshold \
  --output-dir research/output \
  --build-registry
```

Outputs:

- `research/output/demo_hypothesis_threshold_hypothesis/`
- `research/output/demo_hypothesis_threshold_sweep/`
- `research/output/experiment_registry.csv` (if `--build-registry`)
- `research/output/experiment_comparison.csv` (if `--build-registry`)

Behavior note:

- If exact parquet files for your requested dates do not exist for both symbols,
  the demo auto-selects the latest common available `history_<start>_<end>.parquet` range.
- Disable this fallback with `--no-auto-resolve-date-range`.

## 4) Build Cross-Run Registry Directly

```bash
.conda/tradingagents/bin/python research/build_experiment_registry.py \
  --runs-root research/output \
  --registry-csv research/output/experiment_registry.csv \
  --comparison-csv research/output/experiment_comparison.csv \
  --top-k 20
```

## Notes

- Data is read from `data/market` by default.
- Use `--config-json` on the research scripts (or demo runner) to record a config path in `manifest.json`.
- The run directory is deterministic when `--run-tag` is not provided.
