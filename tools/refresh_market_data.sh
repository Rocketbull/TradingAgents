#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."
PYTHON_BIN="${PYTHON_BIN:-.conda/tradingagents/bin/python}"
START_DATE="${1:-2020-01-01}"
END_DATE="${2:-$(date +%F)}"
OUT_DIR="${3:-data/market}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python binary not found at $PYTHON_BIN"
  echo "Set PYTHON_BIN to your TradingAgents environment executable and retry."
  exit 1
fi

pushd "$REPO_ROOT" > /dev/null

echo "[step] refresh sp500 symbol source"
"$PYTHON_BIN" tools/sp500_symbols.py \
  --out data/universe/sp500/current/sp500_symbols.txt \
  --snapshot-dir data/universe/sp500/snapshots

echo "[step] refresh market history (${START_DATE}..${END_DATE})"
"$PYTHON_BIN" tools/download_market_data.py \
  --sp500 \
  --crypto \
  --commodities \
  --start-date "$START_DATE" \
  --end-date "$END_DATE" \
  --out-dir "$OUT_DIR" \
  --overwrite

popd > /dev/null

echo "[done] market data refreshed through $END_DATE"
