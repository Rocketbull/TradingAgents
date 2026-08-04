# Reflections

Use this file for short lessons that should inform future work. Promote durable architecture decisions to `DECISIONS.md`.

## 2026-04-17: Seed project memory
Moved the substance of the previous `AGENTS.md` into `memory/` so `AGENTS.md` can focus on agent operating rules. Keep memory concise and update it only with lessons that should affect future work.

## 2026-04-17: Keep skills behavioral [codex,memory]
Skill files should describe task behavior and point to memory for durable repo facts. When a skill accumulates architecture, command, or workflow detail, move that detail into memory and keep the skill focused.

## 2026-06-06: Align viewer changes with backtest artifacts [backtest,viewer,memory]
When a backtest viewer starts depending on a new artifact such as daily_market_value.csv, update the producing backtest runs before changing default notebook selection. Validate the target run directory, not just the notebook code: confirm the artifact exists, confirm row density matches the intended cadence, and prefer immutable dated snapshot runs over mutable aliases like current_baseline when auto-selecting defaults.

## 2026-06-20: Attach lifecycle metadata at artifact creation [artifacts,tooling,cleanup]
Disposable backtest and research outputs are hard to prune safely after the fact. Write manifest status/keep metadata when runs are created, and let pruning tools fall back to explicit decision registries only for older historical runs.

## 2026-07-04: SPY fragility v2 rule [fragility,regime]
SPY fragility dashboard v2 risk_off now uses macro_score >= 2 or event_score >= 3; the prior confirmation-heavy rule is retained as fragility_regime_v1 for comparison.

## 2026-07-17: Daily backtest carry-forward [backtest,artifacts]
Daily market value artifacts should carry latest rebalance weights forward through the latest available tradable date, even when monthly rebalance logic skips an incomplete month. Partial-month commentary should prefer daily_market_value over equity_curve so active return includes the current stub period.

## 2026-07-30: True sector benchmark weights [optimizer,backtest]
Sector-active caps should compare portfolio sector totals against full-universe benchmark sector totals, not benchmark weights re-normalized inside the liquid optimization subset. Keep liquid-normalized benchmark weights for per-name active and tracking-error constraints, and pass separate sector benchmark totals for sector-active constraints and audit logs.
