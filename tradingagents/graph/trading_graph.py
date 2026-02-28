# TradingAgents/graph/trading_graph.py

import os
from pathlib import Path
import json
from datetime import date, datetime, timedelta
from typing import Dict, Any, Tuple, List, Optional

import pandas as pd
import yfinance as yf
from langgraph.prebuilt import ToolNode

from tradingagents.llm_clients import create_llm_client

from tradingagents.agents import *
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.agents.utils.memory import FinancialSituationMemory
from tradingagents.agents.utils.agent_states import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
)
from tradingagents.dataflows.config import set_config
from tradingagents.alpha import AlphaModel
from tradingagents.portfolio import (
    RiskModel,
    PortfolioOptimizer,
    Rebalancer,
    AttributionEngine,
)

# Import the new abstract tool methods from agent_utils
from tradingagents.agents.utils.agent_utils import (
    get_stock_data,
    get_indicators,
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
    get_news,
    get_insider_transactions,
    get_global_news
)

from .conditional_logic import ConditionalLogic
from .setup import GraphSetup
from .propagation import Propagator
from .reflection import Reflector
from .signal_processing import SignalProcessor


class TradingAgentsGraph:
    """Main class that orchestrates the trading agents framework."""

    def __init__(
        self,
        selected_analysts=["market", "social", "news", "fundamentals"],
        debug=False,
        config: Dict[str, Any] = None,
        callbacks: Optional[List] = None,
    ):
        """Initialize the trading agents graph and components.

        Args:
            selected_analysts: List of analyst types to include
            debug: Whether to run in debug mode
            config: Configuration dictionary. If None, uses default config
            callbacks: Optional list of callback handlers (e.g., for tracking LLM/tool stats)
        """
        self.debug = debug
        self.config = config or DEFAULT_CONFIG
        self.callbacks = callbacks or []

        # Update the interface's config
        set_config(self.config)

        # Create necessary directories
        os.makedirs(
            os.path.join(self.config["project_dir"], "dataflows/data_cache"),
            exist_ok=True,
        )

        self.deep_thinking_llm = None
        self.quick_thinking_llm = None
        self.bull_memory = None
        self.bear_memory = None
        self.trader_memory = None
        self.invest_judge_memory = None
        self.risk_manager_memory = None
        self.tool_nodes = {}
        self.conditional_logic = None
        self.graph_setup = None
        self.propagator = None
        self.reflector = None
        self.signal_processor = None

        # State tracking
        self.curr_state = None
        self.ticker = None
        self.log_states_dict = {}  # date to full state dict
        self.current_portfolio_weights: Dict[str, float] = {}
        self.portfolio_log_states_dict: Dict[str, Dict[str, Any]] = {}

        # Portfolio components (used when portfolio_mode=True)
        self.alpha_model = AlphaModel.from_config(self.config)
        self.risk_model = RiskModel(lookback_days=self.config.get("alpha_lookback_days", 252))
        self.portfolio_optimizer = PortfolioOptimizer(
            risk_aversion=float(self.config.get("risk_aversion", 3.0)),
            max_weight=float(self.config.get("max_weight", 0.05)),
            turnover_limit=float(self.config.get("turnover_limit", 0.20)),
        )
        self.rebalancer = Rebalancer(
            transaction_cost_bps=float(self.config.get("transaction_cost_bps", 5.0))
        )
        self.attribution_engine = AttributionEngine()

        if not self.config.get("portfolio_mode", False):
            # Initialize LLMs with provider-specific thinking configuration
            llm_kwargs = self._get_provider_kwargs()
            if self.callbacks:
                llm_kwargs["callbacks"] = self.callbacks

            deep_client = create_llm_client(
                provider=self.config["llm_provider"],
                model=self.config["deep_think_llm"],
                base_url=self.config.get("backend_url"),
                **llm_kwargs,
            )
            quick_client = create_llm_client(
                provider=self.config["llm_provider"],
                model=self.config["quick_think_llm"],
                base_url=self.config.get("backend_url"),
                **llm_kwargs,
            )

            self.deep_thinking_llm = deep_client.get_llm()
            self.quick_thinking_llm = quick_client.get_llm()

            # Initialize memories
            self.bull_memory = FinancialSituationMemory("bull_memory", self.config)
            self.bear_memory = FinancialSituationMemory("bear_memory", self.config)
            self.trader_memory = FinancialSituationMemory("trader_memory", self.config)
            self.invest_judge_memory = FinancialSituationMemory("invest_judge_memory", self.config)
            self.risk_manager_memory = FinancialSituationMemory("risk_manager_memory", self.config)

            # Create tool nodes and graph components
            self.tool_nodes = self._create_tool_nodes()
            self.conditional_logic = ConditionalLogic()
            self.graph_setup = GraphSetup(
                self.quick_thinking_llm,
                self.deep_thinking_llm,
                self.tool_nodes,
                self.bull_memory,
                self.bear_memory,
                self.trader_memory,
                self.invest_judge_memory,
                self.risk_manager_memory,
                self.conditional_logic,
            )

            self.propagator = Propagator()
            self.reflector = Reflector(self.quick_thinking_llm)
            self.signal_processor = SignalProcessor(self.quick_thinking_llm)
            self.graph = self.graph_setup.setup_graph(selected_analysts)
        else:
            self.graph = None

    def _get_provider_kwargs(self) -> Dict[str, Any]:
        """Get provider-specific kwargs for LLM client creation."""
        kwargs = {}
        provider = self.config.get("llm_provider", "").lower()

        if provider == "google":
            thinking_level = self.config.get("google_thinking_level")
            if thinking_level:
                kwargs["thinking_level"] = thinking_level

        elif provider == "openai":
            reasoning_effort = self.config.get("openai_reasoning_effort")
            if reasoning_effort:
                kwargs["reasoning_effort"] = reasoning_effort

        return kwargs

    def _create_tool_nodes(self) -> Dict[str, ToolNode]:
        """Create tool nodes for different data sources using abstract methods."""
        return {
            "market": ToolNode(
                [
                    # Core stock data tools
                    get_stock_data,
                    # Technical indicators
                    get_indicators,
                ]
            ),
            "social": ToolNode(
                [
                    # News tools for social media analysis
                    get_news,
                ]
            ),
            "news": ToolNode(
                [
                    # News and insider information
                    get_news,
                    get_global_news,
                    get_insider_transactions,
                ]
            ),
            "fundamentals": ToolNode(
                [
                    # Fundamental analysis tools
                    get_fundamentals,
                    get_balance_sheet,
                    get_cashflow,
                    get_income_statement,
                ]
            ),
        }

    def propagate(self, company_name, trade_date):
        """Run the trading agents graph for a company on a specific date."""
        if self.config.get("portfolio_mode", False):
            return self._run_portfolio_cycle(company_name=company_name, trade_date=trade_date)

        self.ticker = company_name

        # Initialize state
        init_agent_state = self.propagator.create_initial_state(
            company_name, trade_date
        )
        args = self.propagator.get_graph_args()

        if self.debug:
            # Debug mode with tracing
            trace = []
            for chunk in self.graph.stream(init_agent_state, **args):
                if len(chunk["messages"]) == 0:
                    pass
                else:
                    chunk["messages"][-1].pretty_print()
                    trace.append(chunk)

            final_state = trace[-1]
        else:
            # Standard mode without tracing
            final_state = self.graph.invoke(init_agent_state, **args)

        # Store current state for reflection
        self.curr_state = final_state

        # Log state
        self._log_state(trade_date, final_state)

        # Return decision and processed signal
        return final_state, self.process_signal(final_state["final_trade_decision"])

    def _run_portfolio_cycle(self, company_name: str, trade_date: str):
        trade_dt = datetime.strptime(str(trade_date), "%Y-%m-%d")
        universe = self._resolve_universe(company_name)
        if len(universe) < 2:
            raise ValueError("Portfolio mode requires at least 2 symbols in universe")

        closes = self._download_close_prices(universe, trade_dt)
        alpha_scores = self.alpha_model.score(closes)
        covariance = self.risk_model.covariance(closes)

        benchmark_symbol = self.config.get("benchmark_symbol", "SPY").upper()
        benchmark_weights = pd.Series(0.0, index=alpha_scores.index)
        if benchmark_symbol in benchmark_weights.index:
            benchmark_weights.loc[benchmark_symbol] = 1.0
        else:
            benchmark_weights[:] = 1.0 / len(benchmark_weights)

        target_weights = self.portfolio_optimizer.optimize(
            alpha_scores=alpha_scores,
            covariance=covariance,
            current_weights=self.current_portfolio_weights,
            benchmark_weights=benchmark_weights.to_dict(),
        )

        current_weights = self._align_weights(alpha_scores.index.tolist(), self.current_portfolio_weights)
        orders = self.rebalancer.generate_orders(
            current_weights=current_weights,
            target_weights=target_weights,
            portfolio_value=float(self.config.get("portfolio_value", 1_000_000.0)),
        )

        realized_proxy = closes.pct_change().iloc[-1].reindex(alpha_scores.index).fillna(0.0)
        metrics = self.attribution_engine.diagnostics(
            alpha_scores=alpha_scores,
            realized_returns=realized_proxy,
            target_weights=target_weights,
        )

        portfolio_state = {
            "trade_date": str(trade_date),
            "company_of_interest": company_name,
            "universe": alpha_scores.index.tolist(),
            "alpha_scores": {k: float(v) for k, v in alpha_scores.to_dict().items()},
            "benchmark_weights": {k: float(v) for k, v in benchmark_weights.to_dict().items()},
            "current_weights": {k: float(v) for k, v in current_weights.items()},
            "target_weights": {k: float(v) for k, v in target_weights.items()},
            "rebalance_orders": orders,
            "portfolio_metrics": metrics,
        }

        self.current_portfolio_weights = dict(target_weights)
        self.curr_state = portfolio_state
        self._log_portfolio_state(str(trade_date), portfolio_state)
        return portfolio_state, "REBALANCE"

    def _resolve_universe(self, company_name: str) -> list[str]:
        source = str(self.config.get("universe_source", "single_symbol")).lower()
        if source == "config_list":
            symbols = [str(s).upper() for s in self.config.get("portfolio_universe", []) if str(s).strip()]
            return sorted(set(symbols))
        if source == "sp500_file":
            path = Path("data/market/sp500_symbols.txt")
            if not path.exists():
                raise FileNotFoundError(f"S&P500 symbols file not found: {path}")
            symbols = [line.strip().upper() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            size = int(self.config.get("portfolio_universe_size", 50))
            return symbols[:size]
        symbol = str(company_name).upper().strip()
        benchmark = str(self.config.get("benchmark_symbol", "SPY")).upper()
        return sorted({symbol, benchmark})

    def _download_close_prices(self, symbols: list[str], trade_dt: datetime) -> pd.DataFrame:
        lookback_days = int(self.config.get("alpha_lookback_days", 252))
        start = (trade_dt - timedelta(days=max(lookback_days * 2, 365))).strftime("%Y-%m-%d")
        end = (trade_dt + timedelta(days=1)).strftime("%Y-%m-%d")

        data = yf.download(
            symbols,
            start=start,
            end=end,
            auto_adjust=True,
            progress=False,
            group_by="column",
            multi_level_index=True,
        )
        if data.empty:
            raise ValueError("No market data returned for portfolio universe")

        if ("Close" in data.columns.get_level_values(0)):
            closes = data["Close"]
        elif "Close" in data.columns:
            closes = data[["Close"]].rename(columns={"Close": symbols[0]})
        else:
            raise ValueError("Close price series missing from yfinance response")

        closes = closes.sort_index().ffill().dropna(axis=1, how="all")
        missing = sorted(set(symbols) - set(closes.columns))
        if missing:
            # Keep deterministic behavior; only operate on symbols with available data.
            closes = closes[[c for c in closes.columns if c in symbols]]
        if closes.shape[1] < 2:
            raise ValueError("Insufficient symbol coverage after market data download")
        return closes

    @staticmethod
    def _align_weights(symbols: list[str], raw: Dict[str, float]) -> Dict[str, float]:
        if not raw:
            w = 1.0 / len(symbols)
            return {s: w for s in symbols}
        aligned = {s: float(raw.get(s, 0.0)) for s in symbols}
        total = sum(max(v, 0.0) for v in aligned.values())
        if total <= 0:
            w = 1.0 / len(symbols)
            return {s: w for s in symbols}
        return {k: max(v, 0.0) / total for k, v in aligned.items()}

    def _log_portfolio_state(self, trade_date: str, portfolio_state: Dict[str, Any]) -> None:
        self.portfolio_log_states_dict[trade_date] = portfolio_state
        directory = Path("eval_results/portfolio/TradingAgentsPortfolio_logs/")
        directory.mkdir(parents=True, exist_ok=True)
        with open(
            directory / f"portfolio_log_{trade_date}.json",
            "w",
            encoding="utf-8",
        ) as file_handle:
            json.dump(self.portfolio_log_states_dict, file_handle, indent=4)

    def _log_state(self, trade_date, final_state):
        """Log the final state to a JSON file."""
        self.log_states_dict[str(trade_date)] = {
            "company_of_interest": final_state["company_of_interest"],
            "trade_date": final_state["trade_date"],
            "market_report": final_state["market_report"],
            "sentiment_report": final_state["sentiment_report"],
            "news_report": final_state["news_report"],
            "fundamentals_report": final_state["fundamentals_report"],
            "investment_debate_state": {
                "bull_history": final_state["investment_debate_state"]["bull_history"],
                "bear_history": final_state["investment_debate_state"]["bear_history"],
                "history": final_state["investment_debate_state"]["history"],
                "current_response": final_state["investment_debate_state"][
                    "current_response"
                ],
                "judge_decision": final_state["investment_debate_state"][
                    "judge_decision"
                ],
            },
            "trader_investment_decision": final_state["trader_investment_plan"],
            "risk_debate_state": {
                "aggressive_history": final_state["risk_debate_state"]["aggressive_history"],
                "conservative_history": final_state["risk_debate_state"]["conservative_history"],
                "neutral_history": final_state["risk_debate_state"]["neutral_history"],
                "history": final_state["risk_debate_state"]["history"],
                "judge_decision": final_state["risk_debate_state"]["judge_decision"],
            },
            "investment_plan": final_state["investment_plan"],
            "final_trade_decision": final_state["final_trade_decision"],
        }

        # Save to file
        directory = Path(f"eval_results/{self.ticker}/TradingAgentsStrategy_logs/")
        directory.mkdir(parents=True, exist_ok=True)

        with open(
            f"eval_results/{self.ticker}/TradingAgentsStrategy_logs/full_states_log_{trade_date}.json",
            "w",
        ) as f:
            json.dump(self.log_states_dict, f, indent=4)

    def reflect_and_remember(self, returns_losses):
        """Reflect on decisions and update memory based on returns."""
        if self.reflector is None:
            raise RuntimeError("reflect_and_remember is unavailable when portfolio_mode=True")
        self.reflector.reflect_bull_researcher(
            self.curr_state, returns_losses, self.bull_memory
        )
        self.reflector.reflect_bear_researcher(
            self.curr_state, returns_losses, self.bear_memory
        )
        self.reflector.reflect_trader(
            self.curr_state, returns_losses, self.trader_memory
        )
        self.reflector.reflect_invest_judge(
            self.curr_state, returns_losses, self.invest_judge_memory
        )
        self.reflector.reflect_risk_manager(
            self.curr_state, returns_losses, self.risk_manager_memory
        )

    def process_signal(self, full_signal):
        """Process a signal to extract the core decision."""
        if self.signal_processor is None:
            raise RuntimeError("process_signal is unavailable when portfolio_mode=True")
        return self.signal_processor.process_signal(full_signal)
