---
name: refresh-market-data
description: Refresh TradingAgents universe files and local market-history data for recurring workflows such as sp500, a300, csi300, benchmark ETFs, universal data, or full market-data refreshes.
---

# Refresh Market Data

Use this skill when the user wants to refresh recurring market data in this repo, especially:

- `sp500` universe data
- `a300` or `csi300` universe data
- benchmark ETFs such as `SPY`, `QQQ`, `TLT`, `GLD`
- "universal data"
- full `data/market/` history refreshes

## Scope

This skill covers two refresh layers:

1. Universe files under `data/universe/`
2. Local history files under `data/market/`

Treat repo language as:

- `sp500` -> S&P 500 universe
- `a300` -> `csi300` in this repo
- benchmark ETFs -> tracked seed list in `data/universe/etf/current/etf_symbols.txt`

## Interpreter

Prefer `.conda/tradingagents/bin/python`.

If that path does not exist in the current checkout, use the working fallback interpreter already validated for this repo:

- `/home/rockebull/mambaforge/bin/python`

Report which interpreter you used.

## Default Refresh Behavior

If the user asks to "refresh the universal data" for `sp500` and `a300`, do all of the recurring benchmark inputs:

1. Refresh current universe membership files.
2. Refresh benchmark ETF history for the tracked ETF list.
3. Refresh full local market-history files for a fresh 5-year window ending today.

Use explicit dates for the history refresh rather than relying on implicit defaults. Keep the older dated history files; write the new dated window alongside them.

## Universe Refresh Commands

Refresh S&P 500 membership:

```bash
<python> tools/sp500_symbols.py
```

Refresh CSI300 membership and weights:

```bash
<python> tools/csi300_symbols.py
```

Expected outputs:

- `data/universe/sp500/current/sp500_symbols.txt`
- `data/universe/sp500/current/sp500_symbols.metadata.json`
- `data/universe/sp500/snapshots/sp500_membership_YYYY-MM-DD.csv`
- `data/universe/csi300/current/csi300_symbols.txt`
- `data/universe/csi300/current/csi300_symbols.metadata.json`
- `data/universe/csi300/current/csi300_weights.csv`
- `data/universe/csi300/snapshots/csi300_membership_YYYY-MM-DD.csv`
- `data/universe/csi300/weights/csi300_weights_YYYY-MM-DD.csv`
- `data/universe/etf/current/etf_symbols.txt`
- `data/universe/etf/current/etf_symbols.metadata.json`

## Full History Refresh Commands

Compute an explicit 5-year window ending today and run both download flows.

Benchmark ETFs:

```bash
<python> tools/download_market_data.py \
  --symbols-file data/universe/etf/current/etf_symbols.txt \
  --start-date <YYYY-MM-DD> \
  --end-date <YYYY-MM-DD> \
  --out-dir data/market \
  --overwrite \
  --continue-on-error
```

S&P 500:

```bash
<python> tools/download_market_data.py \
  --sp500 \
  --start-date <YYYY-MM-DD> \
  --end-date <YYYY-MM-DD> \
  --out-dir data/market \
  --overwrite \
  --continue-on-error
```

CSI300 / A300:

```bash
<python> tools/download_market_data.py \
  --vendor ashare \
  --csi300 \
  --start-date <YYYY-MM-DD> \
  --end-date <YYYY-MM-DD> \
  --out-dir data/market \
  --overwrite \
  --continue-on-error
```

## Workflow

1. Confirm whether the user wants universe-only refresh or universe plus full history.
2. Refresh the universe files first.
3. Inspect one representative existing symbol under `data/market/` to confirm the prior dated window pattern.
4. Refresh the tracked benchmark ETFs so benchmark and regime calendar symbols do not lag behind the main universes.
5. Run the main history refreshes in parallel when possible.
6. Wait for final summaries. Do not assume success mid-stream.
7. Spot-check one U.S. symbol and one A-share symbol to confirm the new dated files exist.
8. Spot-check `SPY` whenever a backtest benchmark or calendar issue is in scope.
9. Report symbol counts, explicit dates, interpreter used, and any shorter-history cases as normal rather than failures when caused by newer listings or ticker lineage changes.

## Reporting Rules

- Use exact dates in the final response.
- Distinguish universe refresh results from history refresh results.
- If the project-local interpreter is missing, say so briefly and note the fallback path you used.
- If a downloader finishes with warnings, report the affected symbols explicitly.
- Do not claim validation beyond the command outputs and spot-checks you actually ran.
