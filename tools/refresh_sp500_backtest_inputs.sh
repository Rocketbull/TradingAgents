#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."
PYTHON_BIN="${PYTHON_BIN:-.conda/tradingagents/bin/python}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python binary not found at $PYTHON_BIN"
  echo "Set PYTHON_BIN to your Active Portfolio environment executable and retry."
  exit 1
fi

pushd "$REPO_ROOT" > /dev/null
"$PYTHON_BIN" tools/refresh_sp500_backtest_inputs.py "$@"
popd > /dev/null
