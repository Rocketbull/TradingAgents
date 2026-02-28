# TradingAgents Active Portfolio Management Plan (Grinold/Kahn-aligned)

## Summary
This document defines a planning-only roadmap to extend TradingAgents from a single-ticker categorical signal system (`BUY`/`SELL`/`HOLD`) into a multi-asset active portfolio management system aligned with Grinold/Kahn principles.

The plan includes:
1. Current-state architecture review.
2. External open-source baseline research and recommended stack.
3. A phased, decision-complete implementation roadmap.
4. Acceptance criteria, risks, mitigations, and rollout gates.

No functional code changes are proposed in this document.

## 1) Title + Scope
- Title: TradingAgents Active Portfolio Management Plan (Grinold/Kahn-aligned)
- Scope: Move from single-ticker `BUY`/`SELL`/`HOLD` outputs to multi-asset active portfolio target weights and rebalance decisions relative to a benchmark.

## 2) Current-State Findings (with file references)

### Single-asset state and flow
- State initialization currently assumes one `company_of_interest` and one `trade_date` per run:
  - `tradingagents/graph/propagation.py`
- Core state schema is report-centric and debate-centric, not portfolio-centric:
  - `tradingagents/agents/utils/agent_states.py`

### Decision extraction is categorical only
- Signal post-processing explicitly extracts only one of `BUY`, `SELL`, `HOLD`:
  - `tradingagents/graph/signal_processing.py`

### No optimizer/risk-model layer
- Current orchestration builds analyst/research/risk debate nodes and produces final textual decision, but has no portfolio optimizer, risk model, or order generation layer:
  - `tradingagents/graph/trading_graph.py`

### Existing strengths
- Multi-agent research and risk debate pipeline already exists and is modular.
- `backtrader` is already a dependency and can support execution/backtest simulation.

## 3) Research: Candidate Open-Source Baselines

### 3.1 PyPortfolio/PyPortfolioOpt (MIT) - recommended baseline optimizer
- Repo: `https://github.com/PyPortfolio/PyPortfolioOpt`
- Why:
  - Lightweight Python-native optimizer for expected returns/covariance to weights.
  - Good fit for first implementation with constrained complexity.
  - MIT license is permissive and low-friction for integration.
- Adoption risk:
  - Focused on optimization layer only; does not provide full execution framework.
  - Requires careful wrapper design for turnover and real-world constraints.

### 3.2 stefan-jansen/alphalens-reloaded (Apache-2.0) - factor diagnostics
- Repo: `https://github.com/stefan-jansen/alphalens-reloaded`
- Why:
  - Useful for IC/turnover/decay style diagnostics for alpha quality.
  - Aligns with Grinold-style measurement discipline.
- License notes:
  - Apache-2.0 is permissive and enterprise-friendly.
- Adoption risk:
  - Diagnostics toolkit, not an optimizer or execution engine.
  - Requires structured factor/forward-return data preparation.

### 3.3 dcajasn/Riskfolio-Lib (BSD-3-Clause) - richer risk constraints
- Repo: `https://github.com/dcajasn/Riskfolio-Lib`
- Why:
  - Advanced constraints, risk budgeting, and objective options beyond simple mean-variance.
  - Strong candidate for phase-2+ optimization sophistication.
- License notes:
  - BSD-3-Clause is permissive.
- Adoption risk:
  - Larger API surface and higher implementation complexity than a minimal baseline.

### 3.4 Optional advanced path: cvxgrp/cvxportfolio (GPL-3.0)
- Repo: `https://github.com/cvxgrp/cvxportfolio`
- Why:
  - Strong framework for policy optimization with transaction costs and constraints.
- License notes:
  - GPL-3.0 introduces copyleft obligations; isolate as optional adapter.
- Adoption risk:
  - License constraints and steeper onboarding.

### 3.5 Optional full-platform path: microsoft/qlib (MIT)
- Repo: `https://github.com/microsoft/qlib`
- Why:
  - End-to-end quant research stack (data, modeling, workflows).
- License notes:
  - MIT.
- Adoption risk:
  - Heavy integration footprint; can overwhelm incremental rollout.

### Baseline recommendation
- Primary stack for initial implementation:
  - `PyPortfolioOpt` for optimization.
  - `alphalens-reloaded` for alpha diagnostics.
- Keep extension points for:
  - `Riskfolio-Lib` (advanced constraints),
  - optional adapters for `cvxportfolio` and `qlib`.

## 4) Target Architecture (Decision-Complete)
Introduce a portfolio construction pipeline after analyst/research signals:

1. Alpha scoring layer:
- Convert agent outputs into expected active returns per symbol.
- Output: `alpha_scores: Dict[str, float]`.

2. Risk model layer:
- Estimate covariance matrix and optional factor/sector exposures.
- Output: risk inputs for optimizer (covariance + constraints metadata).

3. Optimizer layer:
- Produce `target_weights` from alpha + risk subject to constraints:
  - long-only,
  - max weight,
  - optional sector caps,
  - turnover limit,
  - benchmark-aware active risk controls.

4. Rebalance and execution simulation:
- Compute weight deltas versus `current_weights`.
- Convert deltas into rebalance orders with transaction costs and turnover controls.

5. Attribution and monitoring:
- Track IC, breadth proxy, transfer coefficient proxy, and realized IR by rebalance date.

## 5) Phased Implementation Plan

## Phase 0: Data + Universe foundation
Objectives:
- Define universe and benchmark configuration.
- Define rebalance calendar and historical data coverage requirements.

Deliverables:
- Config fields for universe source and benchmark.
- Deterministic symbol universe snapshots for each rebalance date.

Gate:
- Able to load a stable universe for at least one historical test period.

## Phase 1: Multi-asset state extension
Objectives:
- Extend graph state from single-asset outputs to portfolio-level artifacts.

Add state keys:
- `universe`
- `alpha_scores`
- `target_weights`
- `current_weights`
- `rebalance_orders`

Gate:
- End-to-end run returns portfolio state object for a test universe.

## Phase 2: Optimizer integration
Objectives:
- Add pluggable optimizer interface with first implementation on PyPortfolioOpt.

Deliverables:
- Optimizer abstraction and default backend.
- Constraint configuration wiring from config to optimizer.
- Deterministic fallback behavior on infeasibility.

Gate:
- Produces valid weights for test universe under defined constraints.

## Phase 3: Rebalance and execution simulation
Objectives:
- Convert target weights to executable order plan and simulate costs.

Deliverables:
- Rebalance order generation (`delta_weights` to orders).
- Transaction cost model (`bps`-based) and turnover cap enforcement.
- Portfolio path tracking across rebalance dates.

Gate:
- Multi-period backtest emits holdings, trades, and PnL trace.

## Phase 4: Grinold diagnostics
Objectives:
- Implement quality metrics for active management process.

Deliverables:
- IC and forward-return alignment metrics.
- Breadth proxy for effective independent bets.
- Transfer coefficient proxy (post-constraint signal retention).
- Realized IR reporting.

Gate:
- Diagnostics computed and stored per rebalance cycle.

## Phase 5: Hardening
Objectives:
- Improve reliability, test coverage, and failure-mode handling.

Deliverables:
- Regression backtests.
- Constraint and fallback stress tests.
- Documentation and operational runbook.

Gate:
- Stable repeated runs with deterministic outputs under fixed seed and input data.

## 6) Important Planned Interface/API Additions

### Config additions in `tradingagents/default_config.py`
Planned new keys:
- `portfolio_mode`
- `benchmark_symbol`
- `universe_source`
- `rebalance_frequency`
- `max_weight`
- `sector_cap`
- `turnover_limit`
- `risk_aversion`
- `transaction_cost_bps`

### State additions in `tradingagents/agents/utils/agent_states.py`
Portfolio-level fields planned from Phase 1:
- `universe`
- `alpha_scores`
- `target_weights`
- `current_weights`
- `rebalance_orders`

### New planned modules
- `tradingagents/portfolio/alpha_model.py`
- `tradingagents/portfolio/risk_model.py`
- `tradingagents/portfolio/optimizer.py`
- `tradingagents/portfolio/rebalance.py`
- `tradingagents/portfolio/attribution.py`

Design requirement:
- Keep these modules decoupled behind narrow interfaces to allow optimizer backend swaps.

## 7) Testing and Acceptance Criteria

### Unit tests
- Weight sum constraints.
- Long-only enforcement.
- Max single-name weight enforcement.
- Sector cap enforcement (when sector data available).
- Turnover cap enforcement.

### Integration tests
- End-to-end rebalance flow on small universe (example: 10 symbols).
- Ensure outputs include `target_weights`, `rebalance_orders`, and updated `current_weights`.

### Backtest sanity tests
- No NaN/inf in weights or PnL path.
- Stable optimization fallback path on infeasibility.
- Deterministic outputs with fixed seed and fixed historical input data.

### Acceptance criteria
- System produces valid portfolio target weights each rebalance cycle.
- System produces rebalance orders with transaction cost-aware adjustments.
- Active-management diagnostics are logged per rebalance date.

## 8) Risks + Mitigations

### Data quality and survivorship bias
Risk:
- Using present-day universe for historical periods can bias results.
Mitigation:
- Define universe snapshot policy by date and maintain date-stamped constituent sets.

### Optimization infeasibility
Risk:
- Constraint sets may produce infeasible problems.
Mitigation:
- Define deterministic fallback and constraint relaxation order.

### License mismatch risk
Risk:
- GPL dependencies can impose distribution constraints.
Mitigation:
- Keep GPL options isolated as optional adapters; default stack stays permissive.

### Signal-to-weight instability
Risk:
- LLM-derived alpha scores can be noisy and unstable.
Mitigation:
- Apply score normalization, clipping, and turnover regularization; monitor IC decay.

## 9) Execution Readiness Checklist
- [ ] Confirm first implementation stack:
  - Default: `PyPortfolioOpt` + `alphalens-reloaded`.
- [ ] Confirm first milestone scope:
  - Weekly rebalance,
  - long-only,
  - top-50 universe,
  - benchmark `SPY`.
- [ ] Confirm deterministic data snapshot policy for universe and prices.
- [ ] Confirm fallback policy for optimizer infeasibility.
- [ ] Confirm reporting schema for diagnostics and rebalance logs.

## 10) Active Portfolio Management Enhancements (New)

This section extends the plan with concepts directly aligned with Grinold/Kahn active management.

### 10.1 Forecast Quality Layer
- Add rolling IC by horizon (for example, 1/2/4 rebalance periods).
- Add top-minus-bottom quantile spread and hit-rate diagnostics.
- Use these diagnostics to support alpha confidence scaling.

### 10.2 Fundamental Law Dashboard
- Track and report:
  - average IC,
  - breadth proxy,
  - transfer coefficient proxy,
  - implied IR (`IC * sqrt(Breadth) * TC`),
  - realized active IR.
- Compare implied IR vs realized IR per run.

### 10.3 Constraint-Aware Alpha Translation
- Preserve both pre-constraint and post-constraint target weights.
- Quantify turnover drag from constraints and implementation.

### 10.4 Active Risk and Cost Governance
- Maintain benchmark-relative risk stats (tracking error already present, extend over time).
- Track transaction cost drag and turnover decomposition:
  - raw turnover,
  - executed turnover,
  - constraint drag.

### 10.5 Robustness Protocol
- Walk-forward backtest windows and fixed-seed reproducibility.
- Stress test knobs:
  - higher transaction cost,
  - tighter turnover limits,
  - smaller universe,
  - delayed rebalance schedule.

### 10.6 Implementation Mapping
- `tradingagents/backtest/engine.py`
  - add horizon IC/spread/hit metrics per rebalance row.
  - add turnover decomposition fields per rebalance row.
- `tradingagents/backtest/metrics.py`
  - add Fundamental Law summary and horizon diagnostic aggregates.
- `tradingagents/portfolio/optimizer.py`
  - optionally emit pre-constraint and post-constraint targets.
- `notebooks/demo_backtest_viewer.ipynb`
  - add visualizations for new diagnostic columns.

## Assumptions and Defaults Chosen
- Save location: `docs/active-portfolio-plan.md`.
- First implementation stack: PyPortfolioOpt baseline, with extension points for Riskfolio-Lib/cvxportfolio later.
- Initial operating mode: long-only active weights versus benchmark, weekly rebalance, constrained turnover.
