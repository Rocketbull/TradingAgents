from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd


@dataclass
class BacktestMetrics:
    periods_per_year: int = 52

    def summarize(self, equity_curve: pd.DataFrame) -> dict:
        if equity_curve.empty:
            raise ValueError("equity_curve is empty")

        nav = equity_curve["nav"].astype(float)
        portfolio_returns = equity_curve["portfolio_return"].astype(float).fillna(0.0)
        benchmark_returns = equity_curve["benchmark_return"].astype(float).fillna(0.0)
        active_returns = portfolio_returns - benchmark_returns

        total_return = float(nav.iloc[-1] / nav.iloc[0] - 1.0)
        years = max(len(nav) / float(self.periods_per_year), 1.0 / self.periods_per_year)
        cagr = float((nav.iloc[-1] / nav.iloc[0]) ** (1.0 / years) - 1.0)

        vol = float(portfolio_returns.std(ddof=0) * math.sqrt(self.periods_per_year))
        sharpe = float(
            (portfolio_returns.mean() / portfolio_returns.std(ddof=0)) * math.sqrt(self.periods_per_year)
        ) if portfolio_returns.std(ddof=0) > 0 else float("nan")
        tracking_error = float(active_returns.std(ddof=0) * math.sqrt(self.periods_per_year))

        running_max = nav.cummax()
        drawdown = nav / running_max - 1.0
        max_drawdown = float(drawdown.min())

        return {
            "total_return": total_return,
            "cagr": cagr,
            "annualized_volatility": vol,
            "sharpe": sharpe,
            "max_drawdown": max_drawdown,
            "tracking_error": tracking_error,
        }

