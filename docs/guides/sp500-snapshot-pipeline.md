# SP500 Snapshot Pipeline

Document type: user workflow guide.
For the broader portfolio/backtest config workflow, see `docs/guides/backtest-config-workflow.md`.

This project now supports a snapshot-building workflow for `data/universe/sp500/snapshots`.

## Current Runtime Default

Date-aware snapshot scheduling is currently **disabled** by default:

- `snapshot_schedule_enabled = False`

So `universe_source=sp500_snapshot` uses one latest available snapshot across all rebalance dates.

## Why This Exists

Historical point-in-time membership is required to avoid survivorship bias.  
If you do not have historical constituent changes yet, this pipeline still lets you generate dated snapshots using the latest membership as a placeholder.

## Tool

- `tools/build_sp500_snapshots.py`

It builds `sp500_membership_YYYY-MM-DD.csv` files from:

1. a base snapshot file, and
2. optional membership-change events (`add` / `remove`).

## Event Format (CSV)

Required columns:

- `effective_date` (`YYYY-MM-DD`)
- `symbol` (ticker)
- `action` (`add` or `remove`)

## Example Commands

Generate weekly snapshots with constant latest membership (placeholder mode):

```bash
conda run -n activepm python tools/build_sp500_snapshots.py \
  --start-date 2020-01-01 \
  --end-date 2026-03-01 \
  --freq W-FRI \
  --events-source none \
  --write-manifest
```

Generate snapshots using your own events CSV:

```bash
conda run -n activepm python tools/build_sp500_snapshots.py \
  --start-date 2020-01-01 \
  --end-date 2026-03-01 \
  --freq W-FRI \
  --events-source csv \
  --events-csv data/universe/sp500/events/sp500_membership_events.csv \
  --write-manifest
```

Generate snapshots from Wikipedia recent changes table (limited history):

```bash
conda run -n activepm python tools/build_sp500_snapshots.py \
  --start-date 2020-01-01 \
  --end-date 2026-03-01 \
  --freq W-FRI \
  --events-source wikipedia_recent \
  --write-manifest
```

## Enabling Date-Aware Runtime Later

When you trust your historical snapshot coverage, set:

- `universe_source = "sp500_snapshot"`
- `snapshot_schedule_enabled = True`

Then each rebalance date uses the membership snapshot as of that date.
