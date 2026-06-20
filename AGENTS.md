# Active Portfolio Agent Guide

This file is operating guidance for agents. Durable project knowledge lives in `memory/`.

## Start Here
- Read `memory/INDEX.md` first.
- Then read only the memory files relevant to the task.
- Use `.codex/skills/` when a task clearly matches a skill.
- Active portfolio runtime code lives in `activeportfolio/`; the original TradingAgents project is vendored as `vendor/TradingAgents`.
- Keep changes local, incremental, and consistent with existing module boundaries.

## First-Principles Workflow
Before changing code:
1. State the actual user outcome.
2. Identify the smallest behavior or interface that must change.
3. Inspect the existing implementation before designing anything new.
4. Prefer existing modules, helpers, and patterns.
5. Add abstraction only when current duplication or complexity proves it is needed.
6. Verify with the narrowest meaningful test.

## Overengineering Guard
Default to the smallest working change.

Before introducing a new abstraction, name:
- the repeated concrete problem,
- the existing simpler alternative,
- why the simpler alternative is insufficient,
- the tests or call sites that prove the abstraction is useful.

If those cannot be named, do not add the abstraction.

Do not add frameworks, registries, plugin systems, config layers, generic adapters, or new dependencies unless the current task cannot be solved cleanly without them.

## Environment
- Always run project commands in the `activepm` Conda environment.
- Use `conda run -n activepm python` for Python and pytest commands.
- Use `conda run -n activepm python -m pip` for dependency commands.
- Do not add dependencies unless required.

## Validation
- Run targeted tests for touched behavior.
- Broaden validation when shared behavior, dataflow contracts, or portfolio/backtest outputs can change.
- If validation cannot run because of missing data, network, dependencies, or keys, state that clearly.
- Do not fabricate command, test, or backtest results.

## Memory Updates
- Add project memory only when it is likely to help future work.
- Prefer updating an existing file in `memory/` over adding a new file.
- Use `scripts/reflect.py` for short lessons from completed work.
- Run `scripts/memory_guard.py` after memory changes.
