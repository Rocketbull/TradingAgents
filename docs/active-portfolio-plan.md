# TradingAgents Active Portfolio Management Plan (Grinold/Kahn-aligned)

## Summary
This document defines and tracks the roadmap to extend TradingAgents from a single-ticker categorical signal system (`BUY`/`SELL`/`HOLD`) into a multi-asset active portfolio management system aligned with Grinold/Kahn principles.

The plan includes:
1. Current-state architecture review.
2. External open-source baseline research and recommended stack.
3. A phased, decision-complete implementation roadmap.
4. Acceptance criteria, risks, mitigations, and rollout gates.

This plan is now used as a living status artifact and includes implemented vs pending scope.

## Status Snapshot (as of 2026-02-28)
Completed:
- Multi-asset backtest pipeline with rebalance simulation:
  - `tradingagents/backtest/engine.py`
  - `tradingagents/backtest/accounting.py`
  - `tradingagents/backtest/data_loader.py`
  - `tools/demo_backtest.py`
- Portfolio construction core:
  - `tradingagents/portfolio/risk_model.py`
  - `tradingagents/portfolio/optimizer.py`
  - `tradingagents/portfolio/rebalance.py`
  - `tradingagents/portfolio/attribution.py`
- Alpha module split and extensible registry/profiles:
  - `tradingagents/alpha/model.py`
  - `tradingagents/alpha/signals.py`
  - `tradingagents/alpha/profiles.py`
  - `docs/alpha-signal-registry-guide.md`
- Grinold diagnostics and horizon metrics in backtest output:
  - IC / breadth proxy / TC proxy / implied IR / realized active IR
  - horizon IC/spread/hit metrics
- Tests and demo artifacts:
  - `tests/test_portfolio_pipeline.py`
  - `tests/test_backtest_engine.py`
- Repeatable alpha research framework and diagnostics workflow:
  - `research/common/grinold.py`
  - `research/common/run_manager.py`
  - `research/alpha_flat_volume_breakout.py`
  - `notebooks/research_run_viewer.ipynb`
  - `docs/alpha-flat-volume-breakout-research-workflow.md`
- Benchmark-relative construction baseline and TC plumbing improvements:
  - Benchmark proxy weights integrated into backtest rebalance loop.
  - Optimizer supports `active_weight_cap` and optional `tracking_error_target`.
  - Attribution accepts pre/post-constraint active weights for TC estimation.

Partially completed:
- Optimizer backend/fallback policy exists, but deterministic relaxation order is still basic.
- Risk model exists (shrunk covariance), but no factor exposure model yet.

Not completed:
- Historical universe snapshots (anti-survivorship policy).
- Sector constraints and active risk budgets in optimizer.
- Walk-forward and stress grid orchestration.

## Practical Readiness Gap Assessment (as of 2026-02-28)
This section captures where the current implementation is still below practical active-management standards.

1. Benchmark-relative active optimization is incomplete.
- Current backtest now uses proxy benchmark weights and supports active caps/optional TE targets, but benchmark still uses a proxy (not official index weights) and TE policy needs calibration.
- Impact: weights are not governed as true active bets versus benchmark.
- Practicality risk: high.

2. Transfer coefficient (TC) is currently a weak proxy.
- Current attribution now supports TC from unconstrained vs constrained active weights; legacy score-vs-weight proxy remains available as fallback.
- Remaining gap vs Grinold: strengthen logging/usage so corrected TC is always primary in reports and dashboards.
- Practicality risk: high.

3. IC weighting is framework-appropriate but not robust enough yet.
- Strengths: rolling IC, EWMA, correlation penalty, cap, smoothing.
- Gaps: no significance gate / threshold gate, no confidence-aware shrinkage.
- Practicality risk: medium-high.

4. Risk model remains covariance-only.
- Current model uses shrunk sample covariance without a full factor-risk path.
- Practicality risk: medium-high.

5. Universe point-in-time handling is still partial.
- Snapshot support exists, but universe is not fully re-resolved per rebalance date.
- Practicality risk: medium.

Initial quality ratings (for planning only):
- IC weighting: 5/10 (good baseline, not production quality).
- TC estimation: 5/10 (improved plumbing, still proxy-heavy and needs stricter governance).

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

## Phase 0: Data + Universe foundation (Partially complete)
Objectives:
- Define universe and benchmark configuration.
- Define rebalance calendar and historical data coverage requirements.

Deliverables:
- Config fields for universe source and benchmark.
- Deterministic symbol universe snapshots for each rebalance date.

Gate:
- Able to load a stable universe for at least one historical test period.
- Remaining gap: universe is currently sourced from present-day symbol files; add date-stamped membership snapshots.

## Phase 1: Multi-asset state extension (Partially complete)
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
- Remaining gap: state typing in `tradingagents/agents/utils/agent_states.py` is not fully portfolio-first.

## Phase 2: Optimizer integration (Complete for baseline)
Objectives:
- Add pluggable optimizer interface with first implementation on PyPortfolioOpt.

Deliverables:
- Optimizer abstraction and default backend.
- Constraint configuration wiring from config to optimizer.
- Deterministic fallback behavior on infeasibility.

Gate:
- Produces valid weights for test universe under defined constraints.

## Phase 3: Rebalance and execution simulation (Complete for baseline)
Objectives:
- Convert target weights to executable order plan and simulate costs.

Deliverables:
- Rebalance order generation (`delta_weights` to orders).
- Transaction cost model (`bps`-based) and turnover cap enforcement.
- Portfolio path tracking across rebalance dates.

Gate:
- Multi-period backtest emits holdings, trades, and PnL trace.

## Phase 4: Grinold diagnostics (Complete for baseline)
Objectives:
- Implement quality metrics for active management process.

Deliverables:
- IC and forward-return alignment metrics.
- Breadth proxy for effective independent bets.
- Transfer coefficient proxy (post-constraint signal retention).
- Realized IR reporting.

Gate:
- Diagnostics computed and stored per rebalance cycle.

## Phase 5: Hardening (In progress)
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
- `tradingagents/alpha/model.py`
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
- [x] Confirm first implementation stack:
  - Default: `PyPortfolioOpt` + `alphalens-reloaded`.
- [x] Confirm first milestone scope:
  - Weekly rebalance,
  - long-only,
  - top-50 universe,
  - benchmark `SPY`.
- [ ] Confirm deterministic data snapshot policy for universe and prices.
- [ ] Confirm fallback policy for optimizer infeasibility (baseline exists; relaxation policy to formalize).
- [x] Confirm reporting schema for diagnostics and rebalance logs.

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

## 11) Next Execution Steps (Amended)
Priority 1 (data correctness):
- Add universe snapshot support:
  - New input format: `data/market/universe/sp500_membership_YYYY-MM-DD.csv`
  - Backtest should resolve the latest snapshot available on each rebalance date.
  - Acceptance: no forward-looking membership in historical windows.

Priority 2 (optimizer realism):
- Add sector and benchmark-relative constraints:
  - In optimizer: sector cap enforcement and active weight cap vs benchmark.
  - Extend config with explicit `active_weight_cap` and optional `tracking_error_target`.
  - Acceptance: tests that assert sector caps and active caps under rebalance.
- Add explicit benchmark-relative objective wiring:
  - Optimize expected *active* return under active-risk controls.
  - Ensure benchmark weights are injected as true benchmark, not placeholders.
  - Acceptance: active weights sum to zero (where applicable) and TE controls bind in stress tests.
- Status update:
  - Baseline implementation added (`active_weight_cap`, optional `tracking_error_target`, benchmark proxy weights).
  - Remaining work: integrate official benchmark constituent weights and validate TE target calibration policy.

Priority 3 (risk model depth):
- Add optional factor risk model path:
  - Estimate simple market/beta and sector exposures.
  - Expose factor covariance + specific risk estimates.
  - Acceptance: optimizer can run in `risk_model_type = covariance|factor`.

Priority 4 (hardening and research loop):
- Add walk-forward runner + stress matrix:
  - Vary transaction costs, turnover limits, universe size, and rebalance frequency.
  - Persist comparable run manifests and aggregate report.
  - Acceptance: reproducible multi-run summary table and notebook charts.
- Execution protocol:
  - Every material model/optimizer/attribution enhancement must include a matched A/B backtest (pre-change vs post-change) with fixed config and dataset.
  - Store both run artifacts and a delta summary in the experiment log.
- Status update:
  - Baseline reproducibility pieces are now implemented for research runs:
    - deterministic run tags from parameters,
    - `params.json` and `manifest.json` per run,
    - generic reusable notebook viewer for run artifacts.
  - Remaining work:
    - add batch walk-forward/stress orchestrator,
    - produce consolidated multi-run comparison table.

Priority 5 (portfolio state integration):
- Complete portfolio-first state schema in `agent_states.py` and graph pipeline.
- Acceptance: portfolio graph run emits typed `alpha_scores`, `target_weights`, and `rebalance_orders`.

Priority 6 (attribution correctness):
- Replace TC proxy with pre/post-constraint active-weight TC:
  - Persist unconstrained active weights and constrained active weights per rebalance.
  - Compute TC from their correlation and compare with current proxy.
  - Acceptance: attribution report includes both legacy proxy and corrected TC during transition.
- Status update:
  - Backtest now passes unconstrained/constrained active weights into attribution diagnostics.
  - Remaining work: expose corrected TC explicitly in notebook dashboards as primary metric.

## 12) Deferred TODOs (Framework Stage)
These are intentionally deferred while the project prioritizes framework completeness over alpha quality.

- TODO 1: IC threshold gate (signal pruning)
  - Rule: set a signal weight to zero when rolling IC is below a configurable minimum.
  - Purpose: prevent persistently weak signals from polluting composite alpha.
  - Status: deferred.

- TODO 2: IC significance gate (robustness filter)
  - Rule: require minimum statistical strength (for example IC t-stat and/or hit-rate threshold) before allowing non-zero signal weight.
  - Purpose: avoid overreacting to noise in short IC histories.
  - Status: deferred.

- TODO 3: Standardize research scripts on shared framework
  - Rule: migrate `research/hypothesis_analysis.py` and `research/threshold_sweep.py` to use shared run manager + manifest pattern.
  - Purpose: make research outputs consistently reproducible and easier to compare in one viewer.
  - Status: pending.

- TODO 4: Cross-run experiment registry and comparison report
  - Rule: add an index file (or parquet/csv table) that records all runs with key metrics for filtering and ranking.
  - Purpose: support repeatable parameter sweeps and apples-to-apples comparisons across experiments.
  - Status: pending.

- TODO 5: Long-short expansion path (beta-neutral and 130/30)
  - Rule: extend current benchmark-relative architecture to support:
    - beta-neutral portfolios (beta target near 0),
    - 130/30 long-short construction (gross/net exposure constraints).
  - Required upgrades:
    - optimizer bounds/objective for negative weights and leverage/gross-net constraints,
    - direct beta/factor exposure constraints in optimization,
    - accounting and rebalance support for shorts (borrow/margin/carry),
    - long-short specific diagnostics (gross/net exposure, beta drift, borrow drag).
  - Purpose: keep architecture ready for advanced mandate types while preserving current benchmark-relative implementation as baseline.
  - Status: future.

- Rationale for deferral:
  - Current stage is focused on architecture, data plumbing, and end-to-end workflow reliability.
  - High-quality stable IC is not yet expected; hard gating now may hide integration issues.

## Assumptions and Defaults Chosen
- Save location: `docs/active-portfolio-plan.md`.
- First implementation stack: PyPortfolioOpt baseline, with extension points for Riskfolio-Lib/cvxportfolio later.
- Initial operating mode: long-only active weights versus benchmark, weekly rebalance, constrained turnover.
