# Documentation Map

Use this index to separate runnable user workflows from implementation planning.

## Start Here

If you want to run or configure the portfolio/backtest stack, start with:

- `docs/guides/backtest-config-workflow.md`
- `docs/guides/alpha-signal-registry-guide.md`
- `docs/guides/sp500-snapshot-pipeline.md`

If you want project status, architecture direction, or next implementation phases, start with:

- `docs/plans/active-portfolio-plan.md`

## Document Types

### User Guides And Workflows
These documents explain how to run existing tooling and research workflows.

- `docs/guides/backtest-config-workflow.md`
- `docs/guides/alpha-signal-registry-guide.md`
- `docs/guides/sp500-snapshot-pipeline.md`
- `docs/guides/alphalens-research-workflow.md`
- `docs/guides/alpha-flat-volume-breakout-research-workflow.md`
- `docs/guides/btc-gld-ic-gating-stats-guide.md`
- `docs/guides/hypothesis-threshold-research-guide.md`
- `docs/guides/signal-sector-momentum-top2-research-guide.md`

Naming rule:
- `*-workflow.md` and `*-guide.md` are user-facing operational docs.

### Project Plans And Status
These documents track implementation status, architecture decisions, gaps, and future phases.

- `docs/plans/active-portfolio-plan.md`

Naming rule:
- `*-plan.md` is a living implementation/status document, not a runbook.

### Reference Inputs And Scratch Notes
These are not primary source-of-truth runbooks.

- `docs/reference/suggestions.md`

Use these as supporting context, then fold any accepted decisions back into a workflow guide or plan doc.

## Recommended Reading Paths

### Running Backtests
1. `docs/guides/backtest-config-workflow.md`
2. `docs/guides/alpha-signal-registry-guide.md`
3. `docs/guides/sp500-snapshot-pipeline.md`

### Evaluating Research Signals
1. `docs/guides/alpha-signal-registry-guide.md`
2. `docs/guides/alphalens-research-workflow.md`
3. `docs/guides/alpha-flat-volume-breakout-research-workflow.md`

### Understanding Architecture And Roadmap
1. `docs/plans/active-portfolio-plan.md`
2. `docs/guides/backtest-config-workflow.md`

## Promotion Rules

There are two different promotion levels in this repo:

1. Alpha-only promotion:
   - update `tradingagents/alpha/profiles.py`
2. Full backtest baseline promotion:
   - save a repo-tracked config JSON under `research/configs/`

Use `docs/guides/backtest-config-workflow.md` for the operational details.
