# Pitfalls

Use this file for recurring traps that agents should avoid.

## Current Pitfalls
- Do not let `AGENTS.md` grow into project memory. Keep durable context in `memory/`.
- Do not copy architecture, command, or workflow detail back into skill files. Skills should point to memory.
- Do not introduce abstractions, dependencies, or generic layers unless a concrete repeated problem proves they are needed.
