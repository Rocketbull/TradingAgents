---
name: reviewer
description: Review TradingAgents design and code quality. Use for architecture decisions, code review findings, regression risk checks, and test coverage gaps while using project memory for repo-specific context.
---

# Reviewer

Use this skill for review tasks. Keep this file focused on review behavior; durable repo context lives in `memory/`.

## Context
1. Read `memory/INDEX.md`, then only the memory files relevant to the review.
2. Use `memory/ENGINEERING_PRINCIPLES.md` for overengineering and first-principles checks.
3. Use `memory/ARCHITECTURE.md` and `memory/WORKFLOWS.md` for module boundaries, validation, and A/B expectations.

## Review Priorities
1. Correctness and regressions first.
2. Risk and architecture boundary violations second.
3. Missing tests and observability gaps third.
4. Style concerns last.

## Review Output Format
1. Findings ordered by severity with file references.
2. Open questions/assumptions.
3. Short change summary.

## Validation Expectations
- Ask for targeted tests if absent.
- Flag when performance, turnover, or risk metrics may shift unexpectedly.

## Memory Follow-Up
- If the review discovers a durable lesson, decision, or recurring risk, suggest or record it with `scripts/reflect.py`.
- Run `scripts/memory_guard.py` after changing memory.
- Do not duplicate durable project facts here; update `memory/` instead.
