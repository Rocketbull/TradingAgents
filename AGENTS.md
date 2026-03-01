# TradingAgents Codex Guide

This repository is configured for Codex-first development.

## Scope
- Prefer changes that are local and incremental.
- Preserve existing architecture and module boundaries.
- Do not add new dependencies unless required.

## Environment
- Python: `>=3.10` (see `pyproject.toml`)
- Use project env binaries directly from `.conda/tradingagents/bin/`.
- Install deps: `.conda/tradingagents/bin/pip install -r requirements.txt`
- Optional editable install: `.conda/tradingagents/bin/pip install -e .`

## Common Commands
- Run CLI: `.conda/tradingagents/bin/python -m cli.main`
- Run quick script: `.conda/tradingagents/bin/python main.py`
- Run tests: `.conda/tradingagents/bin/python -m pytest -q`
- Run one test: `.conda/tradingagents/bin/python -m pytest -q tests/test_y_finance_history.py`

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

## Skills
- `coder`: implement code changes and targeted tests in this repo. (file: `/home/rockebull/proj/TradingAgents/.codex/skills/coder/SKILL.md`)
- `reviewer`: architecture/design/code-review agent for risk and regression findings. (file: `/home/rockebull/proj/TradingAgents/.codex/skills/reviewer/SKILL.md`)
- `analyst`: test/backtest results analysis agent for A/B deltas and recommendations. (file: `/home/rockebull/proj/TradingAgents/.codex/skills/analyst/SKILL.md`)
- `tradingagents-dev`: repo-specific coding workflow skill. (file: `/home/rockebull/proj/TradingAgents/.codex/skills/tradingagents-dev/SKILL.md`)
- `tradingagents-test-performance-diagnostics`: diagnose pytest performance regressions. (file: `/home/rockebull/proj/TradingAgents/.codex/skills/tradingagents-test-performance-diagnostics/SKILL.md`)
