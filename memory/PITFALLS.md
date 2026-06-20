# Pitfalls

Use this file for recurring traps that agents should avoid.

## Current Pitfalls
- Do not let `AGENTS.md` grow into project memory. Keep durable context in `memory/`.
- Do not copy architecture, command, or workflow detail back into skill files. Skills should point to memory.
- Do not introduce abstractions, dependencies, or generic layers unless a concrete repeated problem proves they are needed.
- Do not use checkout-specific interpreter paths or alternate environments. Run project commands through `conda run -n activepm`.
- Do not patch a backtest viewer to prefer a new artifact until the intended default run directories have been regenerated with that artifact. First verify the artifact contract on the concrete target run, especially when mutable aliases like `current_baseline` coexist with dated snapshots like `current_baseline_YYYYMMDD`.
