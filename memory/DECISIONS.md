# Decisions

## 2026-04-17: Keep AGENTS.md Operational
`AGENTS.md` should stay short and behavioral. Durable project context belongs in `memory/` so agents can read only the context needed for a task.

## 2026-04-17: Prefer First-Principles Changes
Agents should identify the smallest behavior that must change, inspect existing code first, and avoid abstractions unless a concrete repeated problem proves the need.

## 2026-04-17: Use Repo Environment Binaries
Python, pip, and pytest commands should use `.conda/tradingagents/bin/` to avoid environment drift.
