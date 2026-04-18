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

        avg_ic = self._safe_mean(equity_curve.get("metric_information_coefficient"))
        avg_breadth = self._safe_mean(equity_curve.get("metric_breadth_proxy"))
        avg_tc = self._safe_mean(equity_curve.get("metric_transfer_coefficient"))
        if pd.isna(avg_tc):
            avg_tc = self._safe_mean(equity_curve.get("metric_transfer_coefficient_proxy"))
        avg_tc_corrected = self._safe_mean(equity_curve.get("metric_transfer_coefficient_corrected"))
        if pd.isna(avg_tc_corrected):
            avg_tc_corrected = avg_tc
        avg_tc_legacy = self._safe_mean(equity_curve.get("metric_transfer_coefficient_legacy_proxy"))
        if pd.isna(avg_tc_legacy):
            avg_tc_legacy = self._safe_mean(equity_curve.get("metric_transfer_coefficient_proxy"))
        implied_ir = self._implied_ir(avg_ic, avg_breadth, avg_tc)
        realized_active_ir = self._active_ir(active_returns)

        raw_turnover_avg = self._safe_mean(equity_curve.get("raw_turnover"))
        executed_turnover_avg = self._safe_mean(equity_curve.get("executed_turnover"))
        turnover_drag_avg = self._safe_mean(equity_curve.get("turnover_constraint_drag"))

        horizon_summary = self._horizon_summary(equity_curve)

        summary = {
            "total_return": total_return,
            "cagr": cagr,
            "annualized_volatility": vol,
            "sharpe": sharpe,
            "max_drawdown": max_drawdown,
            "tracking_error": tracking_error,
            "average_ic": avg_ic,
            "average_breadth_proxy": avg_breadth,
            "average_transfer_coefficient": avg_tc,
            "average_transfer_coefficient_corrected": avg_tc_corrected,
            "average_transfer_coefficient_legacy_proxy": avg_tc_legacy,
            "average_transfer_coefficient_proxy": avg_tc,
            "implied_information_ratio": implied_ir,
            "realized_active_information_ratio": realized_active_ir,
            "average_raw_turnover": raw_turnover_avg,
            "average_executed_turnover": executed_turnover_avg,
            "average_turnover_constraint_drag": turnover_drag_avg,
        }
        summary.update(horizon_summary)
        return summary

    @staticmethod
    def _safe_mean(series: pd.Series | None) -> float:
        if series is None or len(series) == 0:
            return float("nan")
        s = pd.to_numeric(series, errors="coerce").dropna()
        if s.empty:
            return float("nan")
        return float(s.mean())

    def _active_ir(self, active_returns: pd.Series) -> float:
        std = float(active_returns.std(ddof=0))
        if std <= 0:
            return float("nan")
        return float((active_returns.mean() / std) * math.sqrt(self.periods_per_year))

    @staticmethod
    def _implied_ir(avg_ic: float, avg_breadth: float, avg_tc: float) -> float:
        if any(pd.isna(v) for v in (avg_ic, avg_breadth, avg_tc)):
            return float("nan")
        if avg_breadth <= 0:
            return float("nan")
        return float(avg_ic * math.sqrt(avg_breadth) * avg_tc)

    def _horizon_summary(self, equity_curve: pd.DataFrame) -> dict:
        result: dict[str, float] = {}
        # Detect columns like metric_ic_h1, metric_spread_h1, metric_hit_h1
        for col in equity_curve.columns:
            if col.startswith("metric_ic_h"):
                suffix = col.replace("metric_ic_h", "")
                ic_series = pd.to_numeric(equity_curve[col], errors="coerce").dropna()
                spread_col = equity_curve.get(f"metric_spread_h{suffix}")
                hit_col = equity_curve.get(f"metric_hit_h{suffix}")
                spread_series = (
                    pd.to_numeric(spread_col, errors="coerce").dropna()
                    if spread_col is not None
                    else pd.Series(dtype=float)
                )
                hit_series = (
                    pd.to_numeric(hit_col, errors="coerce").dropna()
                    if hit_col is not None
                    else pd.Series(dtype=float)
                )

                avg_ic = float(ic_series.mean()) if not ic_series.empty else float("nan")
                std_ic = float(ic_series.std(ddof=0)) if not ic_series.empty else float("nan")
                ir_ic = (
                    float((ic_series.mean() / ic_series.std(ddof=0)) * math.sqrt(self.periods_per_year))
                    if len(ic_series) > 0 and float(ic_series.std(ddof=0)) > 0
                    else float("nan")
                )
                result[f"h{suffix}_average_ic"] = avg_ic
                result[f"h{suffix}_ic_std"] = std_ic
                result[f"h{suffix}_ic_ir"] = ir_ic
                result[f"h{suffix}_average_spread"] = (
                    float(spread_series.mean()) if not spread_series.empty else float("nan")
                )
                result[f"h{suffix}_hit_rate"] = (
                    float(hit_series.mean()) if not hit_series.empty else float("nan")
                )
        return result
