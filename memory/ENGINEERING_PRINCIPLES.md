# Engineering Principles

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

Before introducing a new abstraction, be able to name:
- the repeated concrete problem,
- the existing simpler alternative,
- why the simpler alternative is insufficient,
- the tests or call sites that prove the abstraction is useful.

If those cannot be named, do not add the abstraction.

Avoid adding frameworks, registries, plugin systems, config layers, generic adapters, or new dependencies unless the current task cannot be solved cleanly without them.

## Code Standards
- Keep functions small and focused.
- Prefer explicit errors over silent fallbacks.
- Add type hints on new or modified public functions.
- Use `rg` for searches.
- Keep ASCII unless a file already uses Unicode or the task needs it.
