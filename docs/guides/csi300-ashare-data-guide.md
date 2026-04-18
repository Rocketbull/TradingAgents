# CSI300 And A-Share Data Guide

This guide documents the China A-share market data workflow that now lives in this repo.

It covers:

- downloading the latest CSI300 constituent list and weights from the official CSIndex workbook
- downloading 5 years of daily A-share history into repo-standard parquet files under `data/market/`
- using local parquet history with `MyTT` technical indicators

## Official Source

CSI300 membership and weights are pulled from the official CSIndex files:

- detail page: `https://www.csindex.com.cn/zh-CN/indices/index-detail/000300`
- weights workbook: `https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/autofile/closeweight/000300closeweight.xls`

The workbook includes all current constituents and their weights, so one source powers both the symbol list and the weights snapshot.

## Generated Files

Current CSI300 universe files:

- `data/universe/csi300/current/csi300_symbols.txt`
- `data/universe/csi300/current/csi300_symbols.metadata.json`
- `data/universe/csi300/current/csi300_weights.csv`

Dated snapshots:

- `data/universe/csi300/snapshots/csi300_membership_YYYY-MM-DD.csv`
- `data/universe/csi300/weights/csi300_weights_YYYY-MM-DD.csv`

Local market history:

- `data/market/<SYMBOL>/history_<start>_<end>.parquet`
- `data/market/<SYMBOL>/history_<start>_<end>.json`

Examples:

- `data/universe/csi300/current/csi300_symbols.txt`
- `data/universe/csi300/current/csi300_weights.csv`
- `data/market/SZ000001/history_2021-03-22_2026-03-21.parquet`
- `data/market/SH600519/history_2021-03-22_2026-03-21.parquet`

## Refresh CSI300 Constituents And Weights

Run:

```bash
.conda/tradingagents/bin/python tools/csi300_symbols.py
```

This writes:

- the current symbol list
- the current weights CSV
- a dated membership snapshot
- a dated weights snapshot

The downloader normalizes symbols into the repo’s A-share format:

- Shenzhen: `SZ000001`
- Shanghai: `SH600519`

## Download A-Share History To Parquet

The shared market downloader now supports:

- `--vendor ashare`
- `--csi300`
- `--symbols-file`
- `--continue-on-error`

Download all current CSI300 constituents for the last 5 years:

```bash
.conda/tradingagents/bin/python tools/download_market_data.py \
  --vendor ashare \
  --symbols-file data/universe/csi300/current/csi300_symbols.txt \
  --years 5 \
  --continue-on-error
```

Equivalent direct universe fetch:

```bash
.conda/tradingagents/bin/python tools/download_market_data.py \
  --vendor ashare \
  --csi300 \
  --years 5 \
  --continue-on-error
```

Download a smaller manual set:

```bash
.conda/tradingagents/bin/python tools/download_market_data.py \
  --vendor ashare \
  --symbols SZ000001 SH600519 \
  --start-date 2024-01-01 \
  --end-date 2024-03-01
```

Notes:

- output always follows the existing repo parquet layout under `data/market/`
- metadata sidecars record `source: "ashare"`
- newer constituents may naturally have fewer rows than a full 5-year window

## Use MyTT With Local Parquet Data

`tradingagents/core/MyTT.py` now supports local parquet-backed indicator calculation.

Direct Python usage:

```python
from tradingagents.core.MyTT import calculate_indicator_from_parquet, get_mytt_indicators_window

macd = calculate_indicator_from_parquet(
    symbol="SH600519",
    indicator="macd",
    start_date="2024-01-01",
    end_date="2024-03-01",
)

window = get_mytt_indicators_window(
    symbol="SZ000001",
    indicator="rsi",
    curr_date="2026-03-21",
    look_back_days=10,
)
```

Supported symbols can be passed in repo A-share formats such as:

- `SH600519`
- `SZ000001`
- `600519.XSHG`
- `000001.XSHE`

## Route Technical Indicators Through MyTT

The technical indicator vendor can be switched from `yfinance` to `mytt`.

Example:

```python
from tradingagents.dataflows.config import set_config

set_config({
    "data_root": "data/market",
    "tool_vendors": {
        "get_indicators": "mytt",
    },
})
```

After that, calls routed through `route_to_vendor("get_indicators", ...)` will use local parquet history plus `MyTT`.

## Relevant Files

- `tools/csi300_symbols.py`
- `tools/download_market_data.py`
- `tradingagents/dataflows/ashare.py`
- `tradingagents/core/MyTT.py`
- `tradingagents/dataflows/interface.py`
