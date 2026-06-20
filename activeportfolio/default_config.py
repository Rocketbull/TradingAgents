import os

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("ACTIVEPORTFOLIO_RESULTS_DIR", "./results"),
    "data_cache_dir": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
        "dataflows/data_cache",
    ),
    # Portfolio management mode
    "portfolio_mode": False,
    "benchmark_symbol": "SPY",
    "universe_source": "single_symbol",   # single_symbol, config_list, sp500_file, sp500_snapshot
    "portfolio_universe": [],             # Used when universe_source=config_list
    "portfolio_universe_size": 50,        # Used when universe_source=sp500_file
    "universe_snapshot_dir": "data/universe/sp500/snapshots",
    # When False, sp500_snapshot uses one latest available snapshot for all rebalance dates.
    # When True, sp500_snapshot resolves membership as of each rebalance date.
    "snapshot_schedule_enabled": False,
    "dynamic_liquidity_filter": False,
    "liquidity_top_n": 100,
    "liquidity_lookback_days": 60,
    "portfolio_construction_mode": "optimizer",  # optimizer, equal_weight
    "benchmark_weight_mode": "liquidity_proxy",  # equal, liquidity_proxy
    "benchmark_weight_lookback_days": 60,
    "benchmark_hedge_ratio": 0.0,  # Optional short benchmark overlay applied to period returns.
    "rebalance_frequency": "weekly",      # daily, weekly, monthly
    "monthly_rebalance_offset_days": 0,   # trading-day offset from month-end for monthly rebalances
    "max_weight": 0.05,
    "active_weight_cap": None,           # Optional absolute cap on |w - benchmark_w|
    "sector_active_weight_cap": None,    # Optional cap on |sector_w - sector_benchmark_w|
    "tracking_error_target": None,       # Optional annualized ex-ante TE target
    "sector_cap": 0.25,
    "turnover_limit": 0.20,
    "risk_aversion": 3.0,
    "transaction_cost_bps": 5.0,
    "portfolio_value": 1000000.0,
    "alpha_lookback_days": 252,
    # Backtest settings
    "backtest_start_date": None,
    "backtest_end_date": None,
    "backtest_output_dir": None,
    "initial_capital": 1000000.0,
    "slippage_bps": 0.0,
    "min_trade_notional": 0.0,
    "data_root": "data/market",
    "symbol_file": "data/universe/sp500/current/sp500_symbols.txt",
    "sector_classification_cache": "data/market/metadata/yfinance_classification.csv",
    "fetch_missing_sector_data": True,
    "auto_refresh_sector_cache_on_low_coverage": True,
    "min_sector_coverage": 0.70,
    "min_beta_coverage": 0.70,
    "ic_horizons": [1, 2, 4],      # In rebalance steps
    "quantile_buckets": 5,         # For top-bottom spread/hit diagnostics
    "alpha_signals": [
        "mom_1m",
        "mom_3m",
        "mom_6m",
        "mom_12m",
        "mom_12m_skip_1m",
        "rev_1w",
        "rev_1m",
        "low_vol",
        "downside_vol",
        "trend_12m_1m",
        "breakout_52w",
    ],
    # Optional signal registry to fully define alpha signals from config.
    # When non-empty, AlphaModel.from_config() builds signals from this list.
    # Example item: {"type": "momentum", "name": "mom_3m", "window": 63, "enabled": True}
    "alpha_signal_registry": [],
    "alpha_profile": None,
    "ic_lookback_rebalances": 26,
    "ic_weighting_mode": "positive",   # positive, signed
    "alpha_corr_penalty": 0.35,
    "alpha_min_ic_weight": 0.0,
    "alpha_weight_smoothing": 0.25,
    "alpha_max_signal_weight": 0.35,
    "ic_ewm_decay": 0.85,
    # IC gating (disabled by default while framework evolves).
    "ic_gate_min_mean": None,         # Example: 0.01
    "ic_gate_use_abs_mean": False,    # Use |IC| for threshold in signed mode if desired.
    "ic_gate_min_tstat": None,        # Example: 1.0
    "ic_gate_min_hit_rate": None,     # Example: 0.52
    "ic_gate_min_samples": 8,         # Minimum history points for significance gates.
    # Regime switch settings (optional dynamic alpha/profile routing)
    "regime_switch_enabled": False,
    "regime_model_type": "rule_v1",  # rule_v1
    "regime_benchmark_symbol": "SPY",
    "regime_risk_symbol": "BTC-USD",
    "regime_defensive_symbol": "GLD",
    "regime_short_window": 21,
    "regime_long_window": 63,
    "regime_relative_window": 63,
    "regime_risk_on_threshold": 0.15,
    "regime_risk_off_threshold": -0.15,
    "regime_temperature": 0.20,
    "regime_min_hold_rebalances": 2,          # minimum rebalances before another regime switch
    "regime_switch_confidence_buffer": 0.10,  # min top-vs-second probability margin to switch
    # Optional mapping: {"risk_on": "<profile>", "neutral": "<profile>", "risk_off": "<profile>"}
    "regime_alpha_profiles": {},
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        "core_stock_apis": "yfinance",       # Options: alpha_vantage, yfinance
        "technical_indicators": "yfinance",  # Options: alpha_vantage, yfinance, mytt
        "fundamental_data": "yfinance",      # Options: alpha_vantage, yfinance
        "news_data": "yfinance",             # Options: alpha_vantage, yfinance
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
    },
}
