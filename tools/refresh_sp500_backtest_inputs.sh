#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."
if [[ -n "${PYTHON_BIN:-}" ]]; then
  PYTHON_CMD=("$PYTHON_BIN")
else
  PYTHON_CMD=(conda run -n activepm python)
fi

if ! command -v "${PYTHON_CMD[0]}" > /dev/null; then
  echo "Python launcher not found: ${PYTHON_CMD[0]}"
  echo "Install Conda with the activepm environment, or set PYTHON_BIN explicitly."
  exit 1
fi

pushd "$REPO_ROOT" > /dev/null
"${PYTHON_CMD[@]}" tools/refresh_sp500_backtest_inputs.py "$@"
popd > /dev/null
