# Portfolio Analyst Agent

A lightweight starter project for an AI portfolio analyst copilot.

This module is intentionally separate from the existing TradingAgents framework so it can be developed, tested, or removed without disturbing the current research trading workflow.

## Goal

Build a portfolio analyst assistant that can:

- load a portfolio snapshot,
- calculate basic exposures and risk flags,
- create a structured morning brief,
- later add market/news context,
- later add document retrieval over investment notes,
- later add scenario analysis.

Version 1 is a copilot, not an autonomous trader.

## First workflow

The first workflow is a deterministic **morning brief**.

It produces:

1. total market value,
2. asset-class exposure,
3. sector exposure,
4. top positions,
5. risk flags,
6. suggested follow-ups.

## Run

From the repository root:

```bash
python -m portfolio_analyst.graphs.morning_brief_graph
```

## Design rule

> Agents decide what to do. Tools do the math. Reports explain the result.

The LLM layer should be added only after the deterministic analytics path is stable.
