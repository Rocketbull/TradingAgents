from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import pandas as pd

from activeportfolio.alpha import AlphaModel, apply_alpha_profile
from activeportfolio.dataflows.fred_macro import FREDMacroStore
from activeportfolio.dataflows.yfinance_classification import build_symbol_maps
from activeportfolio.default_config import DEFAULT_CONFIG
from activeportfolio.portfolio import (
    AttributionEngine,
    PortfolioOptimizer,
    Rebalancer,
    RiskModel,
)
from activeportfolio.regime import (
    FREDMacroRegimeModel,
    RuleBasedRegimeModel,
    RuleBasedRegimeModelV2,
    regime_stage_title,
    summarize_regime,
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
        alpha_profile = str(merged.get("alpha_profile") or "").strip()
        if alpha_profile:
            merged = apply_alpha_profile(merged, alpha_profile, overwrite=True)
        self.config = merged

        symbol_file = self._resolve_path_with_legacy(
            Path(self.config.get("symbol_file", "data/universe/sp500/current/sp500_symbols.txt")),
            legacy_path=Path("data/market/sp500_symbols.txt"),
            expect_dir=False,
        )
        snapshot_dir = self._resolve_path_with_legacy(
            Path(self.config.get("universe_snapshot_dir", "data/universe/sp500/snapshots")),
            legacy_path=Path("data/market/universe"),
            expect_dir=True,
        )
        self.config["symbol_file"] = str(symbol_file)
        self.config["universe_snapshot_dir"] = str(snapshot_dir)

        self.alpha_model = AlphaModel.from_config(self.config)
        self.regime_model = self._build_regime_model()
        self._alpha_model_cache: Dict[str, AlphaModel] = {}
        self.risk_model = RiskModel(lookback_days=int(self.config.get("alpha_lookback_days", 252)))
        self.optimizer = PortfolioOptimizer(
            risk_aversion=float(self.config.get("risk_aversion", 3.0)),
            max_weight=float(self.config.get("max_weight", 0.05)),
            active_weight_cap=(
                float(self.config["active_weight_cap"])
                if self.config.get("active_weight_cap") is not None
                else None
            ),
            sector_active_weight_cap=(
                float(self.config["sector_active_weight_cap"])
                if self.config.get("sector_active_weight_cap") is not None
                else None
            ),
            tracking_error_target=(
                float(self.config["tracking_error_target"])
                if self.config.get("tracking_error_target") is not None
                else None
            ),
            turnover_limit=float(self.config.get("turnover_limit", 0.20)),
            sector_cap=(
                float(self.config["sector_cap"])
                if self.config.get("sector_cap") is not None
                else None
            ),
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
            symbol_file=symbol_file,
            universe_snapshot_dir=snapshot_dir,
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
        universe_schedule: dict[pd.Timestamp, list[str]] = {}

        if close_prices is None:
            load_start = (start_dt - timedelta(days=warmup_days)).strftime("%Y-%m-%d")
            calendar_index = self._load_calendar_index(
                load_start=load_start,
                end_date=end_date,
                fallback_symbol=fallback_symbol,
            )
            rebalance_dates = [
                d for d in self._rebalance_dates(calendar_index)
                if pd.Timestamp(start_dt) <= d <= pd.Timestamp(end_dt)
            ]
            if len(rebalance_dates) < 2:
                raise ValueError("Need at least 2 rebalance dates in backtest window")

            universe_schedule = self._resolve_universe_schedule(
                rebalance_dates=rebalance_dates,
                fallback_symbol=fallback_symbol,
            )
            symbols_union = sorted(
                {
                    s
                    for syms in universe_schedule.values()
                    for s in syms
                    if str(s).strip()
                }
            )
            if len(symbols_union) < 2:
                raise ValueError("Resolved universe contains fewer than 2 symbols.")

            close_prices = self.data_loader.load_close_matrix(symbols_union, load_start, end_date)
            trading_index = close_prices.index
            try:
                volume_matrix = self.data_loader.load_volume_matrix(symbols_union, load_start, end_date)
            except Exception:
                volume_matrix = None
            context_symbols = self._all_context_symbols()
            if context_symbols:
                try:
                    context_prices = self.data_loader.load_close_matrix(
                        context_symbols, load_start, end_date
                    )
                    context_prices = context_prices.reindex(trading_index).ffill()
                    close_prices = pd.concat([close_prices, context_prices], axis=1)
                    close_prices = close_prices.loc[:, ~close_prices.columns.duplicated(keep="first")]
                except Exception:
                    pass
        else:
            close_prices = close_prices.sort_index().copy()
            close_prices = close_prices.loc[close_prices.index <= pd.Timestamp(end_dt)]
            volume_matrix = None
            rebalance_dates = [
                d for d in self._rebalance_dates(close_prices.index)
                if pd.Timestamp(start_dt) <= d <= pd.Timestamp(end_dt)
            ]
            if len(rebalance_dates) < 2:
                raise ValueError("Need at least 2 rebalance dates in backtest window")
            universe_schedule = {
                d: [str(c).upper() for c in close_prices.columns]
                for d in rebalance_dates
            }

        benchmark_symbol = str(self.config.get("benchmark_symbol", "SPY")).upper()
        context_symbols = set(self._all_context_symbols())
        benchmark_series = (
            close_prices[benchmark_symbol].copy()
            if benchmark_symbol in close_prices.columns
            else pd.Series(0.0, index=close_prices.index)
        )
        tradable_prices = close_prices.drop(columns=[benchmark_symbol], errors="ignore")
        if context_symbols:
            tradable_prices = tradable_prices.drop(columns=list(context_symbols), errors="ignore")
        tradable_volumes = (
            volume_matrix.drop(columns=[benchmark_symbol], errors="ignore")
            if volume_matrix is not None
            else None
        )
        if tradable_prices.shape[1] < 2:
            raise ValueError("Need at least 2 tradable symbols after excluding benchmark.")
        rebalance_dates = [d for d in rebalance_dates if d in tradable_prices.index]
        if len(rebalance_dates) < 2:
            raise ValueError("Need at least 2 rebalance dates in backtest window")
        per_date_universe: dict[pd.Timestamp, list[str]] = {}
        for d in rebalance_dates:
            raw = universe_schedule.get(d, [])
            filtered = [
                str(s).upper()
                for s in raw
                if str(s).upper() in tradable_prices.columns
            ]
            if len(filtered) < 2:
                filtered = list(tradable_prices.columns)
            per_date_universe[d] = list(dict.fromkeys(filtered))

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

        initial_capital = float(self.config.get("initial_capital", self.config.get("portfolio_value", 1_000_000.0)))
        construction_mode = str(self.config.get("portfolio_construction_mode", "optimizer")).lower()
        benchmark_hedge_ratio = max(0.0, float(self.config.get("benchmark_hedge_ratio", 0.0)))
        base_benchmark_overlay = float(self.config.get("benchmark_overlay", 0.0)) - benchmark_hedge_ratio
        current_weights = {s: 0.0 for s in tradable_prices.columns}
        init_universe = per_date_universe.get(rebalance_dates[0], list(tradable_prices.columns))
        current_weights.update(self._equal_weights(init_universe))
        nav = initial_capital

        equity_rows: list[dict] = []
        rebalance_log: list[dict] = []
        orders_rows: list[dict] = []
        weights_rows: list[dict] = []
        signal_ic_history: Dict[str, list[float]] = {}
        prev_alpha_weights: Dict[str, float] = {}
        applied_regime_label: str | None = None
        applied_regime_hold_count = 0
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

        for i in range(len(rebalance_dates)):
            rebalance_date = rebalance_dates[i]
            is_terminal_rebalance = i == len(rebalance_dates) - 1
            next_date = rebalance_dates[i + 1] if not is_terminal_rebalance else rebalance_date
            universe_today = per_date_universe.get(rebalance_date, list(tradable_prices.columns))
            today_close_history = tradable_prices.loc[:rebalance_date, universe_today].ffill()
            today_volume_history = (
                tradable_volumes.loc[:rebalance_date, universe_today].ffill()
                if tradable_volumes is not None
                else None
            )
            liquid_symbols = self._select_liquid_symbols(
                close_history=today_close_history,
                volume_history=today_volume_history,
                top_n=int(self.config.get("liquidity_top_n", 100)),
                lookback_days=int(self.config.get("liquidity_lookback_days", 60)),
                enabled=bool(self.config.get("dynamic_liquidity_filter", False)),
            )

            history = today_close_history.loc[:, liquid_symbols].ffill()
            history = history.dropna(axis=1, thresh=max(2, warmup_rows))
            history = history.dropna(axis=0, how="any")
            liquid_symbols = list(history.columns)
            alpha_cols = list(dict.fromkeys(liquid_symbols + [s for s in context_symbols if s in close_prices.columns]))
            alpha_history = close_prices.loc[history.index, alpha_cols].ffill()
            volume_history = (
                today_volume_history.reindex(index=history.index, columns=history.columns).ffill()
                if today_volume_history is not None
                else None
            )
            if history.shape[1] < 2 or history.shape[0] < warmup_rows:
                continue
            raw_regime = self._detect_regime(close_prices.loc[:rebalance_date])
            regime_label, switched, switch_reason = self._apply_regime_stability(
                raw_regime=raw_regime,
                current_label=applied_regime_label,
                current_hold_count=applied_regime_hold_count,
            )
            if regime_label == applied_regime_label:
                applied_regime_hold_count += 1
            else:
                applied_regime_label = regime_label
                applied_regime_hold_count = 1
            regime = dict(raw_regime)
            regime["raw_label"] = raw_regime.get("label", "static")
            regime["label"] = regime_label
            regime["switched"] = bool(switched)
            regime["switch_reason"] = str(switch_reason)
            regime["hold_count"] = int(applied_regime_hold_count)
            regime_benchmark_overlay = self._regime_benchmark_overlay(regime["label"])
            effective_benchmark_overlay = base_benchmark_overlay + regime_benchmark_overlay

            active_profile = None
            if construction_mode == "equal_weight":
                alpha_scores = pd.Series(0.0, index=history.columns, dtype=float)
                alpha_weights = {}
                raw_alpha_scores = pd.Series(0.0, index=history.columns, dtype=float)
                components = pd.DataFrame(index=history.columns)
                raw_components = pd.DataFrame(index=history.columns)
            else:
                signals = list(
                    self.config.get("alpha_signals", ["mom_1m", "mom_3m", "mom_6m", "rev_1w", "low_vol"])
                )
                active_alpha_model = self.alpha_model
                if self.regime_model is not None:
                    active_alpha_model, signals, active_profile = self._alpha_for_regime(regime["label"])
                components = active_alpha_model.component_scores(
                    alpha_history,
                    volumes=volume_history,
                    signals=signals,
                )
                raw_components = active_alpha_model.raw_component_scores(
                    alpha_history,
                    volumes=volume_history,
                    signals=signals,
                )
                components = components.reindex(history.columns).fillna(0.0)
                raw_components = raw_components.reindex(history.columns).fillna(0.0)
                alpha_scores, alpha_weights = active_alpha_model.ic_weighted_alpha(
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
                    ic_gate_min_mean=self.config.get("ic_gate_min_mean"),
                    ic_gate_use_abs_mean=bool(self.config.get("ic_gate_use_abs_mean", False)),
                    ic_gate_min_tstat=self.config.get("ic_gate_min_tstat"),
                    ic_gate_min_hit_rate=self.config.get("ic_gate_min_hit_rate"),
                    ic_gate_min_samples=int(self.config.get("ic_gate_min_samples", 8)),
                )
                signal_weight_series = (
                    pd.Series(alpha_weights, dtype=float)
                    .reindex(components.columns)
                    .fillna(0.0)
                )
                raw_alpha_scores = (
                    raw_components.mul(signal_weight_series, axis=1).sum(axis=1)
                    .reindex(alpha_scores.index)
                    .fillna(0.0)
                )
                covariance = self.risk_model.covariance(history)

            benchmark_weights = self._benchmark_proxy_weights(
                close_history=today_close_history,
                volume_history=today_volume_history,
                mode=str(self.config.get("benchmark_weight_mode", "liquidity_proxy")),
                lookback_days=int(self.config.get("benchmark_weight_lookback_days", 60)),
            ).reindex(alpha_scores.index).fillna(0.0)
            current_subset = {s: float(current_weights.get(s, 0.0)) for s in alpha_scores.index}
            if construction_mode == "equal_weight":
                equal_subset = self._equal_weights(alpha_scores.index)
                target_weights = dict(equal_subset)
                optimizer_details = {
                    "backend": "equal_weight",
                    "used_fallback": False,
                    "audit_unconstrained_active_weights": {s: 0.0 for s in alpha_scores.index},
                    "raw_target_weights": dict(equal_subset),
                    "target_weights": dict(equal_subset),
                }
            else:
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
            unconstrained_active_subset = optimizer_details.get("audit_unconstrained_active_weights", {})
            audit_symbols = list(alpha_scores.index)
            unconstrained_active_weights = {
                s: float(unconstrained_active_subset.get(s, 0.0)) for s in audit_symbols
            }
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
            constrained_active_weights = {
                s: float(effective_weights.get(s, 0.0)) - float(benchmark_all_weights.get(s, 0.0))
                for s in audit_symbols
            }

            price_now = tradable_prices.loc[rebalance_date].reindex(alpha_scores.index).astype(float)
            signal_ic_now: Dict[str, float] = {}
            hedge_return = 0.0
            if is_terminal_rebalance:
                symbol_returns = {symbol: 0.0 for symbol in alpha_scores.index}
                realized_series = pd.Series(symbol_returns).reindex(alpha_scores.index).fillna(0.0)
                nav_after_period = nav_after_costs
                portfolio_return = 0.0
                benchmark_return = 0.0
                if construction_mode == "equal_weight":
                    metrics = {}
                else:
                    metrics = {
                        "information_coefficient": float("nan"),
                        "breadth_proxy": float("nan"),
                        "transfer_coefficient": float("nan"),
                        "transfer_coefficient_corrected": float("nan"),
                        "transfer_coefficient_legacy_proxy": float("nan"),
                        "transfer_coefficient_proxy": float("nan"),
                        "realized_information_ratio": float("nan"),
                    }
                horizon_metrics = {}
                for signal_name in components.columns:
                    signal_ic_now[signal_name] = float("nan")
            else:
                price_next = tradable_prices.loc[next_date].reindex(alpha_scores.index).astype(float)
                symbol_returns = ((price_next / price_now) - 1.0).replace([pd.NA], 0.0).fillna(0.0).to_dict()
                realized_series = pd.Series(symbol_returns).reindex(alpha_scores.index).fillna(0.0)
                if construction_mode != "equal_weight":
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
                hedge_return = effective_benchmark_overlay * benchmark_return
                portfolio_return += hedge_return
                nav_after_period = nav_after_costs * (1.0 + portfolio_return)
                if construction_mode == "equal_weight":
                    metrics = {}
                    horizon_metrics = {}
                else:
                    metrics = self.attribution.diagnostics(
                        alpha_scores=alpha_scores,
                        realized_returns=realized_series,
                        target_weights=effective_weights,
                        unconstrained_active_weights=unconstrained_active_weights,
                        constrained_active_weights=constrained_active_weights,
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
                "construction_mode": construction_mode,
                "benchmark_hedge_ratio": benchmark_hedge_ratio,
                "benchmark_overlay": effective_benchmark_overlay,
                "regime_benchmark_overlay": regime_benchmark_overlay,
                "hedge_return": hedge_return,
                "regime_label": regime["label"],
                "regime_raw_label": regime["raw_label"],
                "regime_score": float(regime["score"]),
                "regime_prob_risk_on": float(regime["probabilities"].get("risk_on", 0.0)),
                "regime_prob_neutral": float(regime["probabilities"].get("neutral", 0.0)),
                "regime_prob_risk_off": float(regime["probabilities"].get("risk_off", 0.0)),
                "regime_switched": int(bool(regime.get("switched", False))),
                "regime_hold_count": int(regime.get("hold_count", 0)),
                "terminal_snapshot": int(is_terminal_rebalance),
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
                    "portfolio_return": portfolio_return,
                    "benchmark_return": benchmark_return,
                    "active_return": portfolio_return - benchmark_return,
                    "turnover": turnover,
                    "cost": total_cost,
                    "orders_count": len(orders),
                    "terminal_snapshot": int(is_terminal_rebalance),
                    "raw_target_weights": {k: float(v) for k, v in raw_target_weights.items()},
                    "target_weights": {k: float(v) for k, v in effective_weights.items()},
                    "benchmark_weights": benchmark_all_weights,
                    "construction_mode": construction_mode,
                    "benchmark_hedge_ratio": benchmark_hedge_ratio,
                    "benchmark_overlay": effective_benchmark_overlay,
                    "regime_benchmark_overlay": regime_benchmark_overlay,
                    "hedge_return": hedge_return,
                    "unconstrained_active_weights": unconstrained_active_weights,
                    "constrained_active_weights": constrained_active_weights,
                    "alpha_weights": {k: float(v) for k, v in alpha_weights.items()},
                    "scores": {k: float(v) for k, v in raw_alpha_scores.items()},
                    "z_scores": {k: float(v) for k, v in alpha_scores.items()},
                    "liquid_universe_size": int(len(liquid_symbols)),
                    "sector_map_coverage": float(
                        sum(1 for s in alpha_scores.index if s in sector_map)
                    ) / float(len(alpha_scores)),
                    "beta_map_coverage": float(
                        sum(1 for s in alpha_scores.index if s in beta_map)
                    ) / float(len(alpha_scores)),
                    "signal_ic": signal_ic_now,
                    "regime": regime,
                    "regime_profile": active_profile,
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
        summary["benchmark_symbol"] = benchmark_symbol
        summary["rebalance_points"] = len(equity_curve)
        summary["final_nav"] = float(equity_curve["nav"].iloc[-1])
        summary["initial_capital"] = initial_capital

        out_dir = self._output_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        daily_market_value = self._daily_market_value_curve(
            tradable_prices=tradable_prices,
            benchmark_series=benchmark_series,
            rebalance_log=rebalance_log,
        )
        equity_curve.to_csv(out_dir / "equity_curve.csv", index=False)
        daily_market_value.to_csv(out_dir / "daily_market_value.csv", index=False)
        pd.DataFrame(weights_rows).to_csv(out_dir / "weights_history.csv", index=False)
        pd.DataFrame(orders_rows).to_csv(out_dir / "orders_history.csv", index=False)
        with open(out_dir / "rebalance_log.jsonl", "w", encoding="utf-8") as fh:
            for row in rebalance_log:
                fh.write(json.dumps(row) + "\n")
        (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        commentary = self._build_monthly_commentary(summary=summary, rebalance_log=rebalance_log)
        if commentary:
            (out_dir / "monthly_commentary.md").write_text(commentary, encoding="utf-8")

        return {
            "summary": summary,
            "equity_curve": equity_curve,
            "daily_market_value": daily_market_value,
            "rebalance_log": rebalance_log,
            "output_dir": str(out_dir),
        }

    @staticmethod
    def _daily_market_value_curve(
        tradable_prices: pd.DataFrame,
        benchmark_series: pd.Series,
        rebalance_log: list[dict[str, Any]],
    ) -> pd.DataFrame:
        if not rebalance_log:
            raise ValueError("rebalance_log is empty")

        rebalance_by_date = {
            pd.Timestamp(str(row["trade_date"])): row
            for row in rebalance_log
        }
        start_date = min(rebalance_by_date)
        end_date = max(rebalance_by_date)
        trading_index = tradable_prices.index[
            (tradable_prices.index >= start_date) & (tradable_prices.index <= end_date)
        ]
        if trading_index.empty:
            raise ValueError("No trading dates overlap the rebalance log window.")

        tradable_returns = (
            tradable_prices.reindex(trading_index)
            .ffill()
            .pct_change()
            .replace([math.inf, -math.inf], 0.0)
            .fillna(0.0)
        )
        benchmark_returns = (
            benchmark_series.reindex(trading_index)
            .ffill()
            .pct_change()
            .replace([math.inf, -math.inf], 0.0)
            .fillna(0.0)
        )

        current_weights: dict[str, float] = {}
        portfolio_value: float | None = None
        benchmark_value: float | None = None
        rows: list[dict[str, Any]] = []

        for i, trade_date in enumerate(trading_index):
            rebalance_row = rebalance_by_date.get(trade_date)
            if i == 0:
                if rebalance_row is None:
                    raise ValueError("First trading date is missing a rebalance snapshot.")
                portfolio_value = float(rebalance_row["nav_after_costs"])
                benchmark_value = portfolio_value
                current_weights = {
                    str(symbol): float(weight)
                    for symbol, weight in dict(rebalance_row.get("target_weights", {})).items()
                }
                portfolio_return = 0.0
                benchmark_return = 0.0
            else:
                assert portfolio_value is not None
                assert benchmark_value is not None
                prev_portfolio_value = portfolio_value
                symbol_daily_returns = tradable_returns.loc[trade_date]
                portfolio_return = float(
                    sum(
                        float(current_weights.get(symbol, 0.0)) * float(symbol_daily_returns.get(symbol, 0.0))
                        for symbol in tradable_prices.columns
                    )
                )
                portfolio_value = float(prev_portfolio_value * (1.0 + portfolio_return))
                benchmark_return = float(benchmark_returns.loc[trade_date])
                benchmark_value = float(benchmark_value * (1.0 + benchmark_return))

                if rebalance_row is not None:
                    portfolio_value = float(rebalance_row["nav_after_costs"])
                    portfolio_return = float(portfolio_value / prev_portfolio_value - 1.0)
                    current_weights = {
                        str(symbol): float(weight)
                        for symbol, weight in dict(rebalance_row.get("target_weights", {})).items()
                    }

            rows.append(
                {
                    "trade_date": trade_date.strftime("%Y-%m-%d"),
                    "portfolio_value": float(portfolio_value),
                    "benchmark_value": float(benchmark_value),
                    "portfolio_return": float(portfolio_return),
                    "benchmark_return": float(benchmark_return),
                    "active_return": float(portfolio_return - benchmark_return),
                    "is_rebalance": int(rebalance_row is not None),
                }
            )

        return pd.DataFrame(rows)

    @staticmethod
    def _resolve_path_with_legacy(path: Path, legacy_path: Path, expect_dir: bool) -> Path:
        if expect_dir:
            if path.is_dir():
                has_snapshot_files = any(path.glob("sp500_membership_*.csv"))
                if has_snapshot_files:
                    return path
                if legacy_path.is_dir() and any(legacy_path.glob("sp500_membership_*.csv")):
                    return legacy_path
                return path
            if legacy_path.is_dir():
                return legacy_path
            return path

        if path.exists():
            return path
        if legacy_path.exists():
            return legacy_path
        return path

    def _load_calendar_index(self, load_start: str, end_date: str, fallback_symbol: str) -> pd.DatetimeIndex:
        benchmark_symbol = str(self.config.get("benchmark_symbol", "SPY")).upper()
        candidates = [benchmark_symbol, str(fallback_symbol).upper()]
        seen: set[str] = set()
        ordered = []
        for s in candidates:
            if s and s not in seen:
                ordered.append(s)
                seen.add(s)
        for symbol in ordered:
            try:
                s = self.data_loader.load_symbol_series(
                    symbol=symbol,
                    start_date=load_start,
                    end_date=end_date,
                    field_candidates=["Adj Close", "Close"],
                )
                idx = pd.DatetimeIndex(s.index).sort_values().unique()
                if len(idx) > 0:
                    return idx
            except Exception:
                continue
        raise ValueError(
            f"Unable to build trading calendar from benchmark/fallback symbols: {ordered}"
        )

    def _resolve_universe_schedule(
        self,
        rebalance_dates: list[pd.Timestamp],
        fallback_symbol: str,
    ) -> dict[pd.Timestamp, list[str]]:
        source = str(self.config.get("universe_source", "single_symbol")).lower()
        benchmark_symbol = str(self.config.get("benchmark_symbol", "SPY")).upper()
        portfolio_universe = list(self.config.get("portfolio_universe", []))
        portfolio_universe_size = int(self.config.get("portfolio_universe_size", 50))
        schedule: dict[pd.Timestamp, list[str]] = {}
        snapshot_schedule_enabled = bool(self.config.get("snapshot_schedule_enabled", False))

        def _load_symbols_with_legacy(asof_date: str | None) -> list[str]:
            try:
                return self.data_loader.load_symbols(
                    universe_source=source,
                    portfolio_universe=portfolio_universe,
                    portfolio_universe_size=portfolio_universe_size,
                    benchmark_symbol=benchmark_symbol,
                    fallback_symbol=fallback_symbol,
                    asof_date=asof_date,
                )
            except FileNotFoundError:
                legacy_snapshot_dir = Path("data/market/universe")
                if (
                    self.data_loader.universe_snapshot_dir == legacy_snapshot_dir
                    or not legacy_snapshot_dir.exists()
                ):
                    raise
                legacy_loader = LocalParquetDataLoader(
                    data_root=self.data_loader.data_root,
                    symbol_file=self.data_loader.symbol_file,
                    universe_snapshot_dir=legacy_snapshot_dir,
                )
                return legacy_loader.load_symbols(
                    universe_source=source,
                    portfolio_universe=portfolio_universe,
                    portfolio_universe_size=portfolio_universe_size,
                    benchmark_symbol=benchmark_symbol,
                    fallback_symbol=fallback_symbol,
                    asof_date=asof_date,
                )

        if source != "sp500_snapshot":
            symbols = _load_symbols_with_legacy(asof_date=self.config.get("backtest_start_date"))
            for d in rebalance_dates:
                schedule[d] = list(symbols)
            return schedule

        if not snapshot_schedule_enabled:
            # Keep historical runs stable by default: use one latest-available snapshot
            # for all rebalance dates.
            symbols = _load_symbols_with_legacy(asof_date=None)
            for d in rebalance_dates:
                schedule[d] = list(symbols)
            return schedule

        for d in rebalance_dates:
            asof = pd.Timestamp(d).strftime("%Y-%m-%d")
            symbols = _load_symbols_with_legacy(asof_date=asof)
            schedule[d] = list(symbols)
        return schedule

    def _build_regime_model(self) -> RuleBasedRegimeModel | RuleBasedRegimeModelV2 | FREDMacroRegimeModel | None:
        if not bool(self.config.get("regime_switch_enabled", False)):
            return None
        model_type = str(self.config.get("regime_model_type", "rule_v1")).lower()
        if model_type == "rule_v1":
            return RuleBasedRegimeModel(
                benchmark_symbol=str(self.config.get("regime_benchmark_symbol", self.config.get("benchmark_symbol", "SPY"))).upper(),
                risk_symbol=str(self.config.get("regime_risk_symbol", "BTC-USD")).upper(),
                defensive_symbol=str(self.config.get("regime_defensive_symbol", "GLD")).upper(),
                short_window=int(self.config.get("regime_short_window", 21)),
                long_window=int(self.config.get("regime_long_window", 63)),
                relative_window=int(self.config.get("regime_relative_window", 63)),
                risk_on_threshold=float(self.config.get("regime_risk_on_threshold", 0.15)),
                risk_off_threshold=float(self.config.get("regime_risk_off_threshold", -0.15)),
                temperature=float(self.config.get("regime_temperature", 0.20)),
            )
        if model_type == "rule_v2":
            speculative_symbols = tuple(
                str(s).upper()
                for s in self.config.get("regime_v2_speculative_symbols", ["BTC-USD", "ETH-USD"])
                if str(s).strip()
            )
            return RuleBasedRegimeModelV2(
                benchmark_symbol=str(self.config.get("regime_benchmark_symbol", self.config.get("benchmark_symbol", "SPY"))).upper(),
                duration_symbol=str(self.config.get("regime_v2_duration_symbol", "TLT")).upper(),
                defensive_symbol=str(self.config.get("regime_v2_defensive_symbol", "GLD")).upper(),
                growth_symbol=str(self.config.get("regime_v2_growth_symbol", "XLK")).upper(),
                inflation_symbol=str(self.config.get("regime_v2_inflation_symbol", "XLE")).upper(),
                speculative_symbols=speculative_symbols,
                short_window=int(self.config.get("regime_short_window", 21)),
                long_window=int(self.config.get("regime_long_window", 63)),
                relative_window=int(self.config.get("regime_relative_window", 63)),
                risk_on_threshold=float(self.config.get("regime_risk_on_threshold", 0.15)),
                risk_off_threshold=float(self.config.get("regime_risk_off_threshold", -0.15)),
                temperature=float(self.config.get("regime_temperature", 0.20)),
            )
        if model_type == "macro_v1":
            store = FREDMacroStore(
                root_dir=str(self.config.get("regime_macro_data_root", "data/macro/fred")),
                auto_download=bool(self.config.get("regime_macro_auto_download", True)),
            )
            return FREDMacroRegimeModel(
                macro_store=store,
                macro_lookback_days=int(self.config.get("regime_macro_lookback_days", 800)),
                unemployment_series_id=str(self.config.get("regime_macro_unemployment_series_id", "UNRATE")).upper(),
                inflation_series_id=str(self.config.get("regime_macro_inflation_series_id", "CPIAUCSL")).upper(),
                growth_series_id=str(self.config.get("regime_macro_growth_series_id", "INDPRO")).upper(),
                curve_series_id=str(self.config.get("regime_macro_curve_series_id", "T10Y2Y")).upper(),
                policy_series_id=str(self.config.get("regime_macro_policy_series_id", "FEDFUNDS")).upper(),
                stress_series_id=str(self.config.get("regime_macro_stress_series_id", "VIXCLS")).upper(),
                unemployment_lag_days=int(self.config.get("regime_macro_unemployment_lag_days", 35)),
                inflation_lag_days=int(self.config.get("regime_macro_inflation_lag_days", 35)),
                growth_lag_days=int(self.config.get("regime_macro_growth_lag_days", 35)),
                curve_lag_days=int(self.config.get("regime_macro_curve_lag_days", 1)),
                policy_lag_days=int(self.config.get("regime_macro_policy_lag_days", 35)),
                stress_lag_days=int(self.config.get("regime_macro_stress_lag_days", 1)),
                risk_on_threshold=float(self.config.get("regime_risk_on_threshold", 0.15)),
                risk_off_threshold=float(self.config.get("regime_risk_off_threshold", -0.15)),
                temperature=float(self.config.get("regime_temperature", 0.20)),
                growth_weight=float(self.config.get("regime_macro_growth_weight", 0.25)),
                labor_weight=float(self.config.get("regime_macro_labor_weight", 0.20)),
                inflation_weight=float(self.config.get("regime_macro_inflation_weight", 0.15)),
                curve_weight=float(self.config.get("regime_macro_curve_weight", 0.15)),
                policy_weight=float(self.config.get("regime_macro_policy_weight", 0.10)),
                stress_weight=float(self.config.get("regime_macro_stress_weight", 0.15)),
            )
        raise ValueError(f"Unsupported regime_model_type '{model_type}'.")

    def _detect_regime(self, close_history: pd.DataFrame) -> Dict[str, Any]:
        if self.regime_model is None:
            return {
                "label": "static",
                "score": 0.0,
                "probabilities": {"risk_on": 0.0, "neutral": 1.0, "risk_off": 0.0},
                "diagnostics": {},
            }
        d = self.regime_model.detect(close_history)
        return {
            "label": d.label,
            "score": float(d.score),
            "probabilities": dict(d.probabilities),
            "diagnostics": dict(d.diagnostics),
        }

    def _apply_regime_stability(
        self,
        raw_regime: Dict[str, Any],
        current_label: str | None,
        current_hold_count: int,
    ) -> tuple[str, bool, str]:
        raw_label = str(raw_regime.get("label", "static"))
        if current_label is None:
            return raw_label, True, "init"
        if raw_label == current_label:
            return current_label, False, "same_label"

        min_hold = int(self.config.get("regime_min_hold_rebalances", 2))
        if current_hold_count < max(0, min_hold):
            return current_label, False, "min_hold_block"

        probs = raw_regime.get("probabilities", {})
        margin = 0.0
        if isinstance(probs, dict) and probs:
            vals = sorted([float(v) for v in probs.values() if pd.notna(v)], reverse=True)
            if len(vals) >= 2:
                margin = float(vals[0] - vals[1])
            elif len(vals) == 1:
                margin = float(vals[0])
        min_margin = float(self.config.get("regime_switch_confidence_buffer", 0.10))
        if margin < max(0.0, min_margin):
            return current_label, False, "confidence_block"

        return raw_label, True, "switch"

    def _regime_profile_name(self, label: str) -> str | None:
        mapping = self.config.get("regime_alpha_profiles", {})
        if not isinstance(mapping, dict):
            return None
        v = mapping.get(label)
        if v is None:
            return None
        out = str(v).strip()
        return out or None

    def _alpha_for_regime(self, label: str) -> tuple[AlphaModel, list[str], str | None]:
        profile = self._regime_profile_name(label)
        if not profile:
            signals = list(
                self.config.get("alpha_signals", ["mom_1m", "mom_3m", "mom_6m", "rev_1w", "low_vol"])
            )
            return self.alpha_model, signals, None

        if profile not in self._alpha_model_cache:
            cfg = apply_alpha_profile(dict(self.config), profile, overwrite=True)
            self._alpha_model_cache[profile] = AlphaModel.from_config(cfg)
        model = self._alpha_model_cache[profile]
        cfg = apply_alpha_profile(dict(self.config), profile, overwrite=True)
        signals = list(cfg.get("alpha_signals", model.available_signals()))
        return model, signals, profile

    def _regime_benchmark_overlay(self, label: str) -> float:
        mapping = self.config.get("regime_benchmark_overlays", {})
        if not isinstance(mapping, dict):
            return 0.0
        value = mapping.get(label)
        if value is None:
            return 0.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _alpha_context_symbols(self) -> list[str]:
        return self._alpha_context_symbols_from_config(self.config)

    @staticmethod
    def _alpha_context_symbols_from_config(config: Dict[str, Any]) -> list[str]:
        out: list[str] = []
        reg = config.get("alpha_signal_registry", [])
        if not isinstance(reg, list):
            return out
        for spec in reg:
            if not isinstance(spec, dict):
                continue
            if not bool(spec.get("enabled", True)):
                continue
            typ = str(spec.get("type", "")).strip().lower()
            if typ == "btc_gld_corr":
                risk = str(spec.get("risk_symbol", "BTC-USD")).upper()
                defensive = str(spec.get("defensive_symbol", "GLD")).upper()
                if risk:
                    out.append(risk)
                if defensive:
                    out.append(defensive)
        dedup: list[str] = []
        seen: set[str] = set()
        for s in out:
            if s not in seen:
                dedup.append(s)
                seen.add(s)
        return dedup

    def _regime_context_symbols(self) -> list[str]:
        if self.regime_model is None:
            return []
        model_type = str(self.config.get("regime_model_type", "rule_v1")).lower()
        if model_type == "rule_v2":
            out = [
                str(self.config.get("regime_v2_duration_symbol", "TLT")).upper(),
                str(self.config.get("regime_v2_defensive_symbol", "GLD")).upper(),
                str(self.config.get("regime_v2_growth_symbol", "XLK")).upper(),
                str(self.config.get("regime_v2_inflation_symbol", "XLE")).upper(),
            ]
            out.extend(
                str(s).upper()
                for s in self.config.get("regime_v2_speculative_symbols", ["BTC-USD", "ETH-USD"])
                if str(s).strip()
            )
            return [s for s in out if s]
        out = [
            str(self.config.get("regime_risk_symbol", "BTC-USD")).upper(),
            str(self.config.get("regime_defensive_symbol", "GLD")).upper(),
        ]
        return [s for s in out if s]

    def _all_context_symbols(self) -> list[str]:
        symbols = list(self._alpha_context_symbols())
        symbols.extend(self._regime_context_symbols())
        mapping = self.config.get("regime_alpha_profiles", {})
        if isinstance(mapping, dict):
            for maybe_profile in mapping.values():
                if maybe_profile is None:
                    continue
                profile = str(maybe_profile).strip()
                if not profile:
                    continue
                prof_cfg = apply_alpha_profile(dict(self.config), profile, overwrite=True)
                symbols.extend(self._alpha_context_symbols_from_config(prof_cfg))
        dedup: list[str] = []
        seen: set[str] = set()
        for s in symbols:
            if s not in seen:
                dedup.append(s)
                seen.add(s)
        return dedup

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
            grouped = pd.Series(dates, index=dates).groupby([dates.year, dates.month])
            offset = int(self.config.get("monthly_rebalance_offset_days", 0))
            picks: list[pd.Timestamp] = []
            for (year, month), month_dates in grouped:
                month_idx = pd.DatetimeIndex(month_dates.values).sort_values()
                if len(month_idx) == 0:
                    continue
                month_end = pd.Timestamp(year=int(year), month=int(month), day=1) + pd.offsets.BMonthEnd(0)
                target = month_end + pd.offsets.BDay(offset) if offset < 0 else month_end
                if target > month_idx[-1]:
                    continue
                if target < month_idx[0]:
                    picks.append(pd.Timestamp(month_idx[0]))
                    continue
                eligible = month_idx[month_idx <= target]
                if len(eligible) > 0:
                    picks.append(pd.Timestamp(eligible[-1]))
            return picks
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

    def _build_monthly_commentary(
        self,
        summary: Dict[str, Any],
        rebalance_log: list[dict[str, Any]],
    ) -> str:
        if str(self.config.get("rebalance_frequency", "weekly")).lower() != "monthly":
            return ""
        if len(rebalance_log) < 2:
            return ""

        benchmark_symbol = str(summary.get("benchmark_symbol", self.config.get("benchmark_symbol", "SPY"))).upper()
        initial_capital = float(summary.get("initial_capital", self.config.get("initial_capital", 1_000_000.0)))
        sections = ["# Monthly Rebalance Commentary"]

        for prev_row, current_row in zip(rebalance_log[:-1], rebalance_log[1:]):
            current_date = str(current_row.get("trade_date", ""))
            prev_date = str(prev_row.get("trade_date", ""))
            benchmark_return = float(prev_row.get("benchmark_return", 0.0))
            portfolio_return = float(prev_row.get("portfolio_return", 0.0))
            active_return = float(prev_row.get("active_return", portfolio_return - benchmark_return))
            nav_before = float(current_row.get("nav_before", 0.0))
            nav_after_costs = float(current_row.get("nav_after_costs", nav_before))
            since_inception = (nav_before / initial_capital - 1.0) if initial_capital > 0 else 0.0

            adds, trims = self._weight_change_lists(
                previous_weights=dict(prev_row.get("target_weights", {})),
                current_weights=dict(current_row.get("target_weights", {})),
                limit=5,
            )
            top_holdings = self._top_weights(dict(current_row.get("target_weights", {})), limit=5)
            signal_emphasis = self._top_weights(dict(current_row.get("alpha_weights", {})), limit=3)
            regime = dict(current_row.get("regime", {}))
            regime_label = str(regime.get("label", "static"))
            regime_reason = str(regime.get("switch_reason", "n/a"))
            regime_title = regime_stage_title(regime_label)
            regime_summary = summarize_regime(regime)

            sections.extend(
                [
                    "",
                    f"## {current_date}",
                    "",
                    "### MoM Benchmark Performance",
                    f"From {prev_date} to {current_date}, `{benchmark_symbol}` returned {self._fmt_pct(benchmark_return)}.",
                    "",
                    "### Portfolio Performance",
                    (
                        f"Over the same window, the portfolio returned {self._fmt_pct(portfolio_return)} "
                        f"for active return of {self._fmt_pct(active_return)} versus `{benchmark_symbol}`."
                    ),
                    (
                        f"Portfolio value entered the rebalance at {self._fmt_ccy(nav_before)} and exited at "
                        f"{self._fmt_ccy(nav_after_costs)} after modeled trading costs of "
                        f"{self._fmt_ccy(float(current_row.get('cost', 0.0)))}. "
                        f"Since inception, NAV was {self._fmt_pct(since_inception)} above starting capital."
                    ),
                    "",
                    "### Rebalance Decisions",
                    (
                        f"The rebalance executed {int(current_row.get('orders_count', 0))} orders with "
                        f"turnover of {self._fmt_pct(float(current_row.get('turnover', 0.0)))}."
                    ),
                    f"Largest adds: {adds}.",
                    f"Largest trims: {trims}.",
                    f"Top holdings after rebalance: {top_holdings}.",
                    f"Signal emphasis: {signal_emphasis}.",
                    (
                        f"Regime posture: `{regime_label}` "
                        f"(switch_reason=`{regime_reason}`, hold_count={int(regime.get('hold_count', 0))})."
                    ),
                    "",
                    "### Macro Regime",
                    f"Macro stage: {regime_title}.",
                    regime_summary,
                ]
            )

        return "\n".join(sections).strip() + "\n"

    @staticmethod
    def _weight_change_lists(
        previous_weights: Dict[str, Any],
        current_weights: Dict[str, Any],
        limit: int,
    ) -> tuple[str, str]:
        deltas: list[tuple[str, float]] = []
        for symbol in sorted(set(previous_weights) | set(current_weights)):
            delta = float(current_weights.get(symbol, 0.0)) - float(previous_weights.get(symbol, 0.0))
            if abs(delta) < 1e-4:
                continue
            deltas.append((symbol, delta))

        adds = [item for item in deltas if item[1] > 0]
        trims = [item for item in deltas if item[1] < 0]
        adds.sort(key=lambda item: item[1], reverse=True)
        trims.sort(key=lambda item: item[1])
        return (
            BacktestEngine._fmt_weight_pairs(adds[:limit]),
            BacktestEngine._fmt_weight_pairs(trims[:limit]),
        )

    @staticmethod
    def _top_weights(weights: Dict[str, Any], limit: int) -> str:
        ranked = [
            (str(symbol), float(weight))
            for symbol, weight in weights.items()
            if abs(float(weight)) >= 1e-4
        ]
        ranked.sort(key=lambda item: item[1], reverse=True)
        return BacktestEngine._fmt_weight_pairs(ranked[:limit])

    @staticmethod
    def _fmt_weight_pairs(pairs: list[tuple[str, float]]) -> str:
        if not pairs:
            return "no material changes"
        return ", ".join(f"`{symbol}` {BacktestEngine._fmt_pct(weight)}" for symbol, weight in pairs)

    @staticmethod
    def _fmt_pct(value: float) -> str:
        return f"{value:+.2%}"

    @staticmethod
    def _fmt_ccy(value: float) -> str:
        return f"${value:,.0f}"

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
