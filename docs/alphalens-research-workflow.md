# Alphalens Research Workflow

This project now includes an Alphalens adapter to validate individual factors using the same local data and profile setup used by TradingAgents research scripts.

## 1) Run Adapter for One Factor

Example (`mom_3m` on `diversified_sp500_v2_tilt`):

```bash
.conda/tradingagents/bin/python research/alpha_alphalens_adapter.py \
  --config-json research/configs/alpha_alphalens_mom3m_sample.json \
  --run-tag alphalens_mom3m_sample
```

Outputs are written to:

- `research/output/<run_tag>/summary.csv`
- `research/output/<run_tag>/ic_by_date.csv`
- `research/output/<run_tag>/mean_return_by_quantile.csv`
- `research/output/<run_tag>/std_error_by_quantile.csv`
- `research/output/<run_tag>/turnover_autocorr.csv`
- optional `research/output/<run_tag>/factor_data.parquet`

## 2) View / Save Tearsheet Plots

Use the tearsheet script on the generated `factor_data.parquet`:

```bash
.conda/tradingagents/bin/python research/alpha_alphalens_tearsheet.py \
  --factor-data research/output/alphalens_mom3m_sample/factor_data.parquet \
  --out-dir research/output/alphalens_mom3m_sample/tearsheet_png
```

Optional interactive display:

```bash
.conda/tradingagents/bin/python research/alpha_alphalens_tearsheet.py \
  --factor-data research/output/alphalens_mom3m_sample/factor_data.parquet \
  --show
```

## Notes

- Use `--date-step 1` in the adapter for reliable Alphalens forward-return frequency alignment.
- The environment should keep `pandas < 3.0` for `alphalens-reloaded` compatibility.
- If turnover tearsheet plotting is skipped due upstream compatibility issues, use adapter outputs (`turnover_autocorr.csv`) as the fallback turnover diagnostic.
