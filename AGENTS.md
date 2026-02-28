# TradingAgents Codex Guide

This repository is configured for Codex-first development.

## Scope
- Prefer changes that are local and incremental.
- Preserve existing architecture and module boundaries.
- Do not add new dependencies unless required.

## Environment
- Python: `>=3.10` (see `pyproject.toml`)
- Always activate project env first: `source .conda/tradingagents/bin/activate`
- Install deps: `source .conda/tradingagents/bin/activate && pip install -r requirements.txt`
- Optional editable install: `source .conda/tradingagents/bin/activate && pip install -e .`

## Common Commands
- Run CLI: `source .conda/tradingagents/bin/activate && python -m cli.main`
- Run quick script: `source .conda/tradingagents/bin/activate && python main.py`
- Run tests: `source .conda/tradingagents/bin/activate && pytest -q`
- Run one test: `source .conda/tradingagents/bin/activate && pytest -q tests/test_y_finance_history.py`

## Code Standards
- Keep functions small and focused.
- Prefer explicit errors over silent fallbacks.
- Add type hints on new/modified public functions.
- Use `rg` for searches; avoid slower recursive grep where possible.

## Data & I/O Rules
- Market data output belongs under `data/market/`.
- Keep `data/` contents out of git except placeholders/metadata.
- For new downloader behavior, maintain deterministic output paths.

## Validation Before Handoff
- Run targeted tests for touched modules.
- If tests cannot run due to missing external deps/keys, state that clearly.
