---
name: monthly-investor-commentary
description: Generate on-demand investor-facing monthly portfolio commentary for a TradingAgents backtest run using the latest completed one-month portfolio performance plus live web research on broad market conditions, macro context, and relevant news.
---

# Monthly Investor Commentary

Use this skill when the user wants a GenAI-written monthly investor update, especially:

- latest one-month portfolio commentary
- investor-facing rebalance recap
- portfolio performance plus market/news context
- broad market, macro, and headline-aware narrative tied to the latest run

## Scope

This is an on-demand analysis workflow. It is not the default deterministic backtest artifact.

Use it to combine:

1. local backtest facts from the latest completed month
2. current web research on market backdrop and relevant news
3. a concise investor-facing narrative

## Local Context

First extract the portfolio facts:

```bash
<python> tools/monthly_commentary_context.py
```

If the user names a run explicitly, pass `--run-dir <path>`.

The tool returns:

- period start and end dates
- portfolio, benchmark, and active return
- latest rebalance turnover and costs
- top adds and trims
- top post-rebalance holdings
- current signal emphasis and regime

## Web Research

After loading the local context, browse for the latest relevant external context.

Always:

- use the exact portfolio month from the tool output in your framing
- include concrete dates, not only "last month" or "recently"
- separate sourced facts from your inference
- cite links for the market/news sources you used

Focus the research on:

- broad index performance and market regime over the period
- macro drivers such as rates, inflation, Fed messaging, growth, or risk sentiment when relevant
- major news relevant to the portfolio’s largest holdings, largest adds, largest trims, or dominant sectors

Avoid forced causality. If the portfolio moved differently from the market, say it is consistent with the holdings or sector tilts only when the evidence supports that claim.

## Output

Default structure:

1. Executive summary
2. Market backdrop
3. Portfolio performance
4. Rebalance decisions
5. Risks and watch items

Style requirements:

- audience is potential investors
- concise, polished, and plain English
- confident but not promotional
- no invented facts
- mention exact portfolio and benchmark returns from local artifacts

If the user asks to save the analysis, write it into the run directory as `monthly_commentary_ai.md`.

If they only ask for the commentary, answer in chat and include source links.
