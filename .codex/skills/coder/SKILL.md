---
name: coder
description: Implement TradingAgents code changes, tests, fixes, dataflow work, safe Python refactors, and targeted validation while using project memory for repo-specific context.
---

# Coder

Use this skill for implementation tasks in this repository. Keep this file focused on execution behavior; durable repo context lives in `memory/`.

## Workflow
1. Read `memory/INDEX.md`, then only the memory files relevant to the task.
2. State the smallest behavior or interface that must change.
3. Inspect the existing implementation before designing new code.
4. Implement the smallest local change that preserves module boundaries.
5. Add or update targeted tests for touched behavior.
6. Run focused validation using `conda run -n activepm python`.
7. Report exact commands and outcomes.
8. If the task produced a durable lesson, run `scripts/reflect.py`, then run `scripts/memory_guard.py`.

## Guardrails
- Follow `memory/ENGINEERING_PRINCIPLES.md` before adding abstractions or dependencies.
- Use `memory/ARCHITECTURE.md` for module boundaries and data/I/O rules.
- Use `memory/WORKFLOWS.md` for repo commands, validation, and A/B expectations.
- Do not duplicate durable project facts here; update `memory/` instead.
