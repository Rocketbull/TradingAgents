from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import pandas as pd

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.portfolio import (
    AlphaModel,
    AttributionEngine,
    PortfolioOptimizer,
    Rebalancer,
    RiskModel,
)

from .accounting import PortfolioAccountant
from .data_loader import LocalParquetDataLoader
from .metrics import BacktestMetrics


@dataclass
class BacktestEngine:
    config: Dict[str, Any]

    def __post_init__(self) -> None:
        merged = DEFAULT_CONFIG.copy()
        merged.update(self.config or {})
        self.config = merged

        self.alpha_model = AlphaModel()
        self.risk_model = RiskModel(lookback_days=int(self.config.get("alpha_lookback_days", 252)))
        self.optimizer = PortfolioOptimizer(
            risk_aversion=float(self.config.get("risk_aversion", 3.0)),
            max_weight=float(self.config.get("max_weight", 0.05)),
            turnover_limit=float(self.config.get("turnover_limit", 0.20)),
        )
        self.rebalancer = Rebalancer(
            transaction_cost_bps=float(self.config.get("transaction_cost_bps", 5.0))
        )
        self.attribution = AttributionEngine()
        self.accounting = PortfolioAccountant(
            transaction_cost_bps=float(self.config.get("transaction_cost_bps", 5.0)),
            slippage_bps=float(self.config.get("slippage_bps", 0.0)),
            min_trade_notional=float(self.config.get("min_trade_notional", 0.0)),
        )
        self.metrics = BacktestMetrics(
            periods_per_year=self._periods_per_year(str(self.config.get("rebalance_frequency", "weekly")))
        )
        self.data_loader = LocalParquetDataLoader(
            data_root=Path(self.config.get("data_root", "data/market")),
            symbol_file=Path(self.config.get("symbol_file", "data/market/sp500_symbols.txt")),
        )

    def run(
        self,
        fallback_symbol: str = "SPY",
        close_prices: Optional[pd.DataFrame] = None,
    ) -> dict:
        start_date = self.config.get("backtest_start_date")
        end_date = self.config.get("backtest_end_date")
        if not start_date or not end_date:
            raise ValueError("backtest_start_date and backtest_end_date are required")

        start_dt = datetime.strptime(str(start_date), "%Y-%m-%d")
        end_dt = datetime.strptime(str(end_date), "%Y-%m-%d")
        warmup_days = max(
            int(self.risk_model.lookback_days) + 1,
            int(self.alpha_model.long_lookback) + 1,
            int(self.alpha_model.vol_lookback) + 2,
        ) * 2

        if close_prices is None:
            symbols = self.data_loader.load_symbols(
                universe_source=str(self.config.get("universe_source", "single_symbol")),
                portfolio_universe=list(self.config.get("portfolio_universe", [])),
                portfolio_universe_size=int(self.config.get("portfolio_universe_size", 50)),
                benchmark_symbol=str(self.config.get("benchmark_symbol", "SPY")),
                fallback_symbol=fallback_symbol,
            )
            load_start = (start_dt - timedelta(days=warmup_days)).strftime("%Y-%m-%d")
            close_prices = self.data_loader.load_close_matrix(symbols, load_start, end_date)
        else:
            close_prices = close_prices.sort_index().copy()
            close_prices = close_prices.loc[close_prices.index <= pd.Timestamp(end_dt)]

        rebalance_dates = [
            d for d in self._rebalance_dates(close_prices.index)
            if pd.Timestamp(start_dt) <= d <= pd.Timestamp(end_dt)
        ]
        if len(rebalance_dates) < 2:
            raise ValueError("Need at least 2 rebalance dates in backtest window")

        benchmark_symbol = str(self.config.get("benchmark_symbol", "SPY")).upper()
        initial_capital = float(self.config.get("initial_capital", self.config.get("portfolio_value", 1_000_000.0)))
        current_weights = self._equal_weights(close_prices.columns)
        nav = initial_capital

        equity_rows: list[dict] = []
        rebalance_log: list[dict] = []
        orders_rows: list[dict] = []
        weights_rows: list[dict] = []
        warmup_rows = max(
            int(self.risk_model.lookback_days) + 1,
            int(self.alpha_model.long_lookback) + 1,
            int(self.alpha_model.vol_lookback) + 2,
        )

        for i in range(len(rebalance_dates) - 1):
            rebalance_date = rebalance_dates[i]
            next_date = rebalance_dates[i + 1]

            history = close_prices.loc[:rebalance_date]
            if history.shape[0] < warmup_rows:
                continue
            alpha_scores = self.alpha_model.score(history)
            covariance = self.risk_model.covariance(history)

            benchmark_weights = pd.Series(0.0, index=alpha_scores.index)
            if benchmark_symbol in benchmark_weights.index:
                benchmark_weights.loc[benchmark_symbol] = 1.0
            else:
                benchmark_weights[:] = 1.0 / len(benchmark_weights)

            target_weights = self.optimizer.optimize(
                alpha_scores=alpha_scores,
                covariance=covariance,
                current_weights=current_weights,
                benchmark_weights=benchmark_weights.to_dict(),
            )
            orders = self.rebalancer.generate_orders(
                current_weights=current_weights,
                target_weights=target_weights,
                portfolio_value=nav,
            )
            nav_after_costs, effective_weights, turnover, total_cost = self.accounting.apply_rebalance(
                nav_before=nav,
                current_weights=current_weights,
                target_weights=target_weights,
            )

            price_now = close_prices.loc[rebalance_date].reindex(alpha_scores.index).astype(float)
            price_next = close_prices.loc[next_date].reindex(alpha_scores.index).astype(float)
            symbol_returns = ((price_next / price_now) - 1.0).replace([pd.NA], 0.0).fillna(0.0).to_dict()
            nav_after_period, portfolio_return = self.accounting.step_nav(
                nav_after_rebalance=nav_after_costs,
                weights=effective_weights,
                symbol_returns=symbol_returns,
            )
            benchmark_return = float(symbol_returns.get(benchmark_symbol, 0.0))
            metrics = self.attribution.diagnostics(
                alpha_scores=alpha_scores,
                realized_returns=pd.Series(symbol_returns).reindex(alpha_scores.index).fillna(0.0),
                target_weights=effective_weights,
            )

            row = {
                "trade_date": rebalance_date.strftime("%Y-%m-%d"),
                "next_date": next_date.strftime("%Y-%m-%d"),
                "nav": nav_after_period,
                "portfolio_return": portfolio_return,
                "benchmark_return": benchmark_return,
                "turnover": turnover,
                "cost": total_cost,
            }
            row.update({f"metric_{k}": float(v) for k, v in metrics.items()})
            equity_rows.append(row)

            rebalance_log.append(
                {
                    "trade_date": row["trade_date"],
                    "next_date": row["next_date"],
                    "nav_before": nav,
                    "nav_after_costs": nav_after_costs,
                    "nav_after_period": nav_after_period,
                    "turnover": turnover,
                    "cost": total_cost,
                    "orders_count": len(orders),
                    "target_weights": {k: float(v) for k, v in effective_weights.items()},
                    "portfolio_metrics": metrics,
                }
            )
            for order in orders:
                enriched = dict(order)
                enriched["trade_date"] = row["trade_date"]
                orders_rows.append(enriched)
            weights_rows.append({"trade_date": row["trade_date"], **{k: float(v) for k, v in effective_weights.items()}})

            current_weights = effective_weights
            nav = nav_after_period

        if not equity_rows:
            raise ValueError(
                "Backtest produced no rebalance points after warmup; extend date range or reduce lookbacks."
            )

        equity_curve = pd.DataFrame(equity_rows)
        summary = self.metrics.summarize(equity_curve)
        summary["start_date"] = start_date
        summary["end_date"] = end_date
        summary["rebalance_points"] = len(equity_curve)
        summary["final_nav"] = float(equity_curve["nav"].iloc[-1])
        summary["initial_capital"] = initial_capital

        out_dir = self._output_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        equity_curve.to_csv(out_dir / "equity_curve.csv", index=False)
        pd.DataFrame(weights_rows).to_csv(out_dir / "weights_history.csv", index=False)
        pd.DataFrame(orders_rows).to_csv(out_dir / "orders_history.csv", index=False)
        with open(out_dir / "rebalance_log.jsonl", "w", encoding="utf-8") as fh:
            for row in rebalance_log:
                fh.write(json.dumps(row) + "\n")
        (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

        return {
            "summary": summary,
            "equity_curve": equity_curve,
            "rebalance_log": rebalance_log,
            "output_dir": str(out_dir),
        }

    def _rebalance_dates(self, trading_index: pd.Index) -> list[pd.Timestamp]:
        freq = str(self.config.get("rebalance_frequency", "weekly")).lower()
        dates = pd.DatetimeIndex(trading_index).sort_values().unique()
        if freq == "daily":
            return list(dates)
        if freq == "monthly":
            grouped = pd.Series(dates, index=dates).groupby([dates.year, dates.month]).last()
            return list(pd.DatetimeIndex(grouped.values))
        # weekly default: last trading day of each ISO week
        iso = dates.isocalendar()
        grouped = pd.Series(dates, index=dates).groupby([iso.year, iso.week]).last()
        return list(pd.DatetimeIndex(grouped.values))

    @staticmethod
    def _equal_weights(symbols: Iterable[str]) -> Dict[str, float]:
        syms = list(symbols)
        w = 1.0 / len(syms)
        return {s: w for s in syms}

    def _output_dir(self) -> Path:
        configured = self.config.get("backtest_output_dir")
        if configured:
            return Path(configured)
        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        return Path("eval_results/backtest") / f"run_{stamp}"

    @staticmethod
    def _periods_per_year(freq: str) -> int:
        f = freq.lower()
        if f == "daily":
            return 252
        if f == "monthly":
            return 12
        return 52
