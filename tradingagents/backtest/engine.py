from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import pandas as pd

from tradingagents.alpha import AlphaModel
from tradingagents.dataflows.yfinance_classification import build_symbol_maps
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.portfolio import (
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

        self.alpha_model = AlphaModel.from_config(self.config)
        self.risk_model = RiskModel(lookback_days=int(self.config.get("alpha_lookback_days", 252)))
        self.optimizer = PortfolioOptimizer(
            risk_aversion=float(self.config.get("risk_aversion", 3.0)),
            max_weight=float(self.config.get("max_weight", 0.05)),
            active_weight_cap=(
                float(self.config["active_weight_cap"])
                if self.config.get("active_weight_cap") is not None
                else None
            ),
            tracking_error_target=(
                float(self.config["tracking_error_target"])
                if self.config.get("tracking_error_target") is not None
                else None
            ),
            turnover_limit=float(self.config.get("turnover_limit", 0.20)),
            sector_cap=float(self.config.get("sector_cap", 0.25)),
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
            universe_snapshot_dir=Path(
                self.config.get("universe_snapshot_dir", "data/market/universe")
            ),
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
        volume_matrix: Optional[pd.DataFrame] = None

        if close_prices is None:
            symbols = self.data_loader.load_symbols(
                universe_source=str(self.config.get("universe_source", "single_symbol")),
                portfolio_universe=list(self.config.get("portfolio_universe", [])),
                portfolio_universe_size=int(self.config.get("portfolio_universe_size", 50)),
                benchmark_symbol=str(self.config.get("benchmark_symbol", "SPY")),
                fallback_symbol=fallback_symbol,
                asof_date=start_date,
            )
            load_start = (start_dt - timedelta(days=warmup_days)).strftime("%Y-%m-%d")
            close_prices = self.data_loader.load_close_matrix(symbols, load_start, end_date)
            try:
                volume_matrix = self.data_loader.load_volume_matrix(symbols, load_start, end_date)
            except Exception:
                volume_matrix = None
        else:
            close_prices = close_prices.sort_index().copy()
            close_prices = close_prices.loc[close_prices.index <= pd.Timestamp(end_dt)]
            volume_matrix = None

        benchmark_symbol = str(self.config.get("benchmark_symbol", "SPY")).upper()
        benchmark_series = (
            close_prices[benchmark_symbol].copy()
            if benchmark_symbol in close_prices.columns
            else pd.Series(0.0, index=close_prices.index)
        )
        tradable_prices = close_prices.drop(columns=[benchmark_symbol], errors="ignore")
        tradable_volumes = (
            volume_matrix.drop(columns=[benchmark_symbol], errors="ignore")
            if volume_matrix is not None
            else None
        )
        if tradable_prices.shape[1] < 2:
            raise ValueError("Need at least 2 tradable symbols after excluding benchmark.")
        sector_map, beta_map = build_symbol_maps(
            symbols=list(tradable_prices.columns),
            path=Path(
                self.config.get(
                    "sector_classification_cache",
                    "data/market/metadata/yfinance_classification.csv",
                )
            ),
            fetch_missing=bool(self.config.get("fetch_missing_sector_data", False)),
        )

        rebalance_dates = [
            d for d in self._rebalance_dates(tradable_prices.index)
            if pd.Timestamp(start_dt) <= d <= pd.Timestamp(end_dt)
        ]
        if len(rebalance_dates) < 2:
            raise ValueError("Need at least 2 rebalance dates in backtest window")

        initial_capital = float(self.config.get("initial_capital", self.config.get("portfolio_value", 1_000_000.0)))
        current_weights = self._equal_weights(tradable_prices.columns)
        nav = initial_capital

        equity_rows: list[dict] = []
        rebalance_log: list[dict] = []
        orders_rows: list[dict] = []
        weights_rows: list[dict] = []
        signal_ic_history: Dict[str, list[float]] = {}
        prev_alpha_weights: Dict[str, float] = {}
        warmup_rows = max(
            int(self.risk_model.lookback_days) + 1,
            int(self.alpha_model.long_lookback) + 1,
            int(self.alpha_model.vol_lookback) + 2,
        )
        min_sector_cov = float(self.config.get("min_sector_coverage", 0.70))
        min_beta_cov = float(self.config.get("min_beta_coverage", 0.70))
        coverage_denom = float(max(1, tradable_prices.shape[1]))
        sector_cov = float(len(sector_map)) / coverage_denom
        beta_cov = float(len(beta_map)) / coverage_denom
        if (
            bool(self.config.get("auto_refresh_sector_cache_on_low_coverage", True))
            and (sector_cov < min_sector_cov or beta_cov < min_beta_cov)
        ):
            sector_map, beta_map = build_symbol_maps(
                symbols=list(tradable_prices.columns),
                path=Path(
                    self.config.get(
                        "sector_classification_cache",
                        "data/market/metadata/yfinance_classification.csv",
                    )
                ),
                fetch_missing=True,
            )

        for i in range(len(rebalance_dates) - 1):
            rebalance_date = rebalance_dates[i]
            next_date = rebalance_dates[i + 1]
            liquid_symbols = self._select_liquid_symbols(
                close_history=tradable_prices.loc[:rebalance_date],
                volume_history=(tradable_volumes.loc[:rebalance_date] if tradable_volumes is not None else None),
                top_n=int(self.config.get("liquidity_top_n", 100)),
                lookback_days=int(self.config.get("liquidity_lookback_days", 60)),
                enabled=bool(self.config.get("dynamic_liquidity_filter", False)),
            )

            history = tradable_prices.loc[:rebalance_date, liquid_symbols]
            volume_history = (
                tradable_volumes.loc[:rebalance_date, liquid_symbols]
                if tradable_volumes is not None
                else None
            )
            if history.shape[0] < warmup_rows:
                continue
            signals = list(
                self.config.get(
                    "alpha_signals",
                    ["mom_1m", "mom_3m", "mom_6m", "rev_1w", "low_vol"],
                )
            )
            components = self.alpha_model.component_scores(
                history,
                volumes=volume_history,
                signals=signals,
            )
            alpha_scores, alpha_weights = self.alpha_model.ic_weighted_alpha(
                components,
                ic_history=signal_ic_history,
                ic_lookback=int(self.config.get("ic_lookback_rebalances", 26)),
                weighting_mode=str(self.config.get("ic_weighting_mode", "positive")),
                corr_penalty=float(self.config.get("alpha_corr_penalty", 0.35)),
                min_abs_weight=float(self.config.get("alpha_min_ic_weight", 0.0)),
                prev_weights=prev_alpha_weights,
                weight_smoothing=float(self.config.get("alpha_weight_smoothing", 0.25)),
                max_signal_weight=float(self.config.get("alpha_max_signal_weight", 0.35)),
                ic_ewm_decay=float(self.config.get("ic_ewm_decay", 0.85)),
            )
            covariance = self.risk_model.covariance(history)

            benchmark_weights = self._benchmark_proxy_weights(
                close_history=tradable_prices.loc[:rebalance_date],
                volume_history=(tradable_volumes.loc[:rebalance_date] if tradable_volumes is not None else None),
                mode=str(self.config.get("benchmark_weight_mode", "liquidity_proxy")),
                lookback_days=int(self.config.get("benchmark_weight_lookback_days", 60)),
            ).reindex(alpha_scores.index).fillna(0.0)
            current_subset = {s: float(current_weights.get(s, 0.0)) for s in alpha_scores.index}

            target_weights, optimizer_details = self.optimizer.optimize(
                alpha_scores=alpha_scores,
                covariance=covariance,
                current_weights=current_subset,
                benchmark_weights=benchmark_weights.to_dict(),
                sector_map={s: sector_map.get(s, "") for s in alpha_scores.index},
                return_details=True,
            )
            subset_target_weights = {s: float(target_weights.get(s, 0.0)) for s in alpha_scores.index}
            target_weights = {s: subset_target_weights.get(s, 0.0) for s in tradable_prices.columns}
            raw_target_subset = optimizer_details.get("raw_target_weights", subset_target_weights)
            raw_target_weights = {s: float(raw_target_subset.get(s, 0.0)) for s in tradable_prices.columns}
            benchmark_subset = benchmark_weights.to_dict()
            benchmark_all_weights = {
                s: float(benchmark_subset.get(s, 0.0))
                for s in tradable_prices.columns
            }
            raw_turnover = sum(
                abs(float(raw_target_weights.get(s, 0.0)) - float(current_weights.get(s, 0.0)))
                for s in set(current_weights) | set(raw_target_weights)
            )
            nav_after_costs, effective_weights, turnover, total_cost = self.accounting.apply_rebalance(
                nav_before=nav,
                current_weights=current_weights,
                target_weights=target_weights,
            )
            orders = self.rebalancer.generate_orders(
                current_weights=current_weights,
                target_weights=effective_weights,
                portfolio_value=nav,
            )

            price_now = tradable_prices.loc[rebalance_date].reindex(alpha_scores.index).astype(float)
            price_next = tradable_prices.loc[next_date].reindex(alpha_scores.index).astype(float)
            symbol_returns = ((price_next / price_now) - 1.0).replace([pd.NA], 0.0).fillna(0.0).to_dict()
            realized_series = pd.Series(symbol_returns).reindex(alpha_scores.index).fillna(0.0)
            signal_ic_now: Dict[str, float] = {}
            for signal_name in components.columns:
                ic_val = self.attribution.cross_sectional_ic(
                    components[signal_name].reindex(alpha_scores.index), realized_series
                )
                signal_ic_now[signal_name] = float(ic_val)
                signal_ic_history.setdefault(signal_name, []).append(float(ic_val))

            nav_after_period, portfolio_return = self.accounting.step_nav(
                nav_after_rebalance=nav_after_costs,
                weights=effective_weights,
                symbol_returns=symbol_returns,
            )
            bench_now = float(benchmark_series.loc[rebalance_date]) if rebalance_date in benchmark_series.index else 0.0
            bench_next = float(benchmark_series.loc[next_date]) if next_date in benchmark_series.index else 0.0
            benchmark_return = (bench_next / bench_now - 1.0) if bench_now > 0 else 0.0
            metrics = self.attribution.diagnostics(
                alpha_scores=alpha_scores,
                realized_returns=realized_series,
                target_weights=effective_weights,
                unconstrained_active_weights={
                    s: float(raw_target_weights.get(s, 0.0)) - float(benchmark_all_weights.get(s, 0.0))
                    for s in tradable_prices.columns
                },
                constrained_active_weights={
                    s: float(effective_weights.get(s, 0.0)) - float(benchmark_all_weights.get(s, 0.0))
                    for s in tradable_prices.columns
                },
            )
            horizon_metrics = self._horizon_metrics(
                close_prices=tradable_prices,
                rebalance_dates=rebalance_dates,
                rebalance_index=i,
                alpha_scores=alpha_scores,
            )

            row = {
                "trade_date": rebalance_date.strftime("%Y-%m-%d"),
                "next_date": next_date.strftime("%Y-%m-%d"),
                "nav": nav_after_period,
                "portfolio_return": portfolio_return,
                "benchmark_return": benchmark_return,
                "turnover": turnover,
                "raw_turnover": raw_turnover,
                "executed_turnover": turnover,
                "turnover_constraint_drag": max(raw_turnover - turnover, 0.0),
                "cost": total_cost,
            }
            row.update({f"metric_{k}": float(v) for k, v in metrics.items()})
            row.update({f"metric_{k}": float(v) for k, v in horizon_metrics.items()})
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
                    "raw_target_weights": {k: float(v) for k, v in raw_target_weights.items()},
                    "target_weights": {k: float(v) for k, v in effective_weights.items()},
                    "benchmark_weights": benchmark_all_weights,
                    "alpha_weights": {k: float(v) for k, v in alpha_weights.items()},
                    "liquid_universe_size": int(len(liquid_symbols)),
                    "sector_map_coverage": float(
                        sum(1 for s in alpha_scores.index if s in sector_map)
                    ) / float(len(alpha_scores)),
                    "beta_map_coverage": float(
                        sum(1 for s in alpha_scores.index if s in beta_map)
                    ) / float(len(alpha_scores)),
                    "signal_ic": signal_ic_now,
                    "portfolio_metrics": metrics,
                    "horizon_metrics": horizon_metrics,
                }
            )
            for order in orders:
                enriched = dict(order)
                enriched["trade_date"] = row["trade_date"]
                orders_rows.append(enriched)
            weights_rows.append({"trade_date": row["trade_date"], **{k: float(v) for k, v in effective_weights.items()}})

            current_weights = effective_weights
            prev_alpha_weights = alpha_weights
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

    def _horizon_metrics(
        self,
        close_prices: pd.DataFrame,
        rebalance_dates: list[pd.Timestamp],
        rebalance_index: int,
        alpha_scores: pd.Series,
    ) -> Dict[str, float]:
        horizons = list(self.config.get("ic_horizons", [1, 2, 4]))
        quantiles = int(self.config.get("quantile_buckets", 5))
        metrics: Dict[str, float] = {}
        date0 = rebalance_dates[rebalance_index]
        px0 = close_prices.loc[date0].reindex(alpha_scores.index).astype(float)

        for h in horizons:
            key = int(h)
            future_idx = rebalance_index + key
            if key < 1 or future_idx >= len(rebalance_dates):
                continue
            date_h = rebalance_dates[future_idx]
            pxh = close_prices.loc[date_h].reindex(alpha_scores.index).astype(float)
            realized = ((pxh / px0) - 1.0).replace([pd.NA], 0.0).fillna(0.0)
            ic_h = self.attribution.cross_sectional_ic(alpha_scores, realized)
            spread_h = self.attribution.top_bottom_spread(
                alpha_scores, realized, quantiles=quantiles
            )
            hit_h = self.attribution.top_bottom_hit(
                alpha_scores, realized, quantiles=quantiles
            )
            metrics[f"ic_h{key}"] = float(ic_h)
            metrics[f"spread_h{key}"] = float(spread_h)
            metrics[f"hit_h{key}"] = float(hit_h)
        return metrics

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
    def _select_liquid_symbols(
        close_history: pd.DataFrame,
        volume_history: Optional[pd.DataFrame],
        top_n: int,
        lookback_days: int,
        enabled: bool,
    ) -> list[str]:
        symbols = list(close_history.columns)
        if not enabled or volume_history is None:
            return symbols
        if close_history.empty or volume_history.empty:
            return symbols
        if top_n <= 0 or top_n >= len(symbols):
            return symbols

        aligned_close = close_history.reindex(columns=symbols).astype(float)
        aligned_vol = volume_history.reindex(columns=symbols).astype(float)
        dollar_vol = (aligned_close * aligned_vol).replace([pd.NA], 0.0).fillna(0.0)
        med = dollar_vol.tail(max(1, int(lookback_days))).median(axis=0)
        med = med.sort_values(ascending=False)
        liquid = [s for s in med.index[:top_n] if pd.notna(med.loc[s])]
        return liquid if len(liquid) >= 2 else symbols

    @staticmethod
    def _benchmark_proxy_weights(
        close_history: pd.DataFrame,
        volume_history: Optional[pd.DataFrame],
        mode: str,
        lookback_days: int,
    ) -> pd.Series:
        symbols = list(close_history.columns)
        if len(symbols) == 0:
            return pd.Series(dtype=float)
        if mode.lower() == "liquidity_proxy" and volume_history is not None and not volume_history.empty:
            aligned_close = close_history.reindex(columns=symbols).astype(float)
            aligned_vol = volume_history.reindex(columns=symbols).astype(float)
            dollar_vol = (aligned_close * aligned_vol).replace([pd.NA], 0.0).fillna(0.0)
            proxy = dollar_vol.tail(max(1, int(lookback_days))).median(axis=0).clip(lower=0.0)
            if float(proxy.sum()) > 0:
                return proxy / float(proxy.sum())
        # Fallback: equal-weight proxy benchmark over tradable universe.
        return pd.Series(1.0 / len(symbols), index=symbols, dtype=float)

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
