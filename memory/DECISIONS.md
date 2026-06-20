# Decisions

## 2026-04-17: Keep AGENTS.md Operational
`AGENTS.md` should stay short and behavioral. Durable project context belongs in `memory/` so agents can read only the context needed for a task.

## 2026-04-17: Prefer First-Principles Changes
Agents should identify the smallest behavior that must change, inspect existing code first, and avoid abstractions unless a concrete repeated problem proves the need.

## 2026-06-20: Use the activepm Conda Environment
Python, pip, and pytest commands should run through `conda run -n activepm` to avoid environment drift and checkout-specific paths.
