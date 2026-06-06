# Reflections

Use this file for short lessons that should inform future work. Promote durable architecture decisions to `DECISIONS.md`.

## 2026-04-17: Seed project memory
Moved the substance of the previous `AGENTS.md` into `memory/` so `AGENTS.md` can focus on agent operating rules. Keep memory concise and update it only with lessons that should affect future work.

## 2026-04-17: Keep skills behavioral [codex,memory]
Skill files should describe task behavior and point to memory for durable repo facts. When a skill accumulates architecture, command, or workflow detail, move that detail into memory and keep the skill focused.

## 2026-05-20: Remember validated fallback interpreter [env,tooling]
When .conda/tradingagents/bin/python is absent in this checkout, use /home/rockebull/mambaforge/bin/python as the validated fallback for repo Python commands and reuse it for the rest of the task instead of re-probing interpreters.

## 2026-06-06: Align viewer changes with backtest artifacts [backtest,viewer,memory]
When a backtest viewer starts depending on a new artifact such as daily_market_value.csv, update the producing backtest runs before changing default notebook selection. Validate the target run directory, not just the notebook code: confirm the artifact exists, confirm row density matches the intended cadence, and prefer immutable dated snapshot runs over mutable aliases like current_baseline when auto-selecting defaults.
