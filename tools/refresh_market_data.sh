#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."
if [[ -n "${PYTHON_BIN:-}" ]]; then
  PYTHON_CMD=("$PYTHON_BIN")
else
  PYTHON_CMD=(conda run -n activepm python)
fi
START_DATE="${1:-2020-01-01}"
END_DATE="${2:-$(date +%F)}"
OUT_DIR="${3:-data/market}"

if ! command -v "${PYTHON_CMD[0]}" > /dev/null; then
  echo "Python launcher not found: ${PYTHON_CMD[0]}"
  echo "Install Conda with the activepm environment, or set PYTHON_BIN explicitly."
  exit 1
fi

pushd "$REPO_ROOT" > /dev/null

echo "[step] refresh sp500 symbol source"
"${PYTHON_CMD[@]}" tools/sp500_symbols.py \
  --out data/universe/sp500/current/sp500_symbols.txt \
  --snapshot-dir data/universe/sp500/snapshots

echo "[step] refresh market history (${START_DATE}..${END_DATE})"
"${PYTHON_CMD[@]}" tools/download_market_data.py \
  --sp500 \
  --crypto \
  --commodities \
  --start-date "$START_DATE" \
  --end-date "$END_DATE" \
  --out-dir "$OUT_DIR" \
  --overwrite

popd > /dev/null

echo "[done] market data refreshed through $END_DATE"
