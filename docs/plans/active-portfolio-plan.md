# TradingAgents Active Portfolio Management Plan (Grinold/Kahn-aligned)

Document type: implementation plan and living status tracker.
For runnable workflows and config usage, start with `docs/README.md` and `docs/guides/backtest-config-workflow.md`.

## Summary
This document defines and tracks the roadmap to extend TradingAgents from a single-ticker categorical signal system (`BUY`/`SELL`/`HOLD`) into a multi-asset active portfolio management system aligned with Grinold/Kahn principles.

The plan includes:
1. Current-state architecture review.
2. External open-source baseline research and recommended stack.
3. A phased, decision-complete implementation roadmap.
4. Acceptance criteria, risks, mitigations, and rollout gates.

This plan is now used as a living status artifact and includes implemented vs pending scope.

As of 2026-03-21, the active portfolio system is no longer just an extension concept. The validated runtime is now the local-data, alpha, portfolio, regime, and backtest stack. The legacy TradingAgents debate/LLM graph remains in the repository, but it is not the primary execution path for active portfolio research. In practice, the broad legacy TradingAgents stack is mainly still useful for data-access and vendor-facing utilities, while portfolio construction and backtesting now live in a separate, more quant-oriented path.

## Status Snapshot (as of 2026-03-21)
Completed:
- Multi-asset backtest pipeline with rebalance simulation:
  - `tradingagents/backtest/engine.py`
  - `tradingagents/backtest/accounting.py`
  - `tradingagents/backtest/data_loader.py`
  - `tools/run_backtest.py`
- Portfolio construction core:
  - `tradingagents/portfolio/risk_model.py`
  - `tradingagents/portfolio/optimizer.py`
  - `tradingagents/portfolio/rebalance.py`
  - `tradingagents/portfolio/attribution.py`
- Alpha module split and extensible registry/profiles:
  - `tradingagents/alpha/model.py`
  - `tradingagents/alpha/signals.py`
  - `tradingagents/alpha/profiles.py`
  - `docs/guides/alpha-signal-registry-guide.md`
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
  - `research/alpha_alphalens_adapter.py`
  - `research/alpha_alphalens_tearsheet.py`
  - `notebooks/research_run_viewer.ipynb`
  - `docs/guides/alpha-flat-volume-breakout-research-workflow.md`
  - `docs/guides/alphalens-research-workflow.md`
- Repo-tracked full backtest baseline config:
  - `research/configs/backtest_current_baseline.json`
- Benchmark-relative construction baseline and TC plumbing improvements:
  - Benchmark proxy weights integrated into backtest rebalance loop.
  - Optimizer supports `active_weight_cap` and optional `tracking_error_target`.
  - Attribution accepts pre/post-constraint active weights for TC estimation.
- Regime-switching baseline (rule-based) and dynamic profile routing:
  - `tradingagents/regime/model.py`
  - Backtest integration with per-rebalance regime labels/scores/probabilities:
    - `tradingagents/backtest/engine.py`
  - Config hooks for regime model and regime-to-profile mapping:
    - `tradingagents/default_config.py`
  - Transition controls:
    - minimum-hold and confidence-buffer gating before regime switches.
    - raw vs applied regime labels logged for auditability.
- Portfolio/backtest runtime is the current validated product path:
  - Primary execution flow is `tools/run_backtest.py` -> `tradingagents/backtest/engine.py`.
  - Portfolio behavior is covered by:
    - `tests/test_portfolio_pipeline.py`
    - `tests/test_backtest_engine.py`
    - `tests/test_regime_model.py`
- Shared data workflow is established:
  - Market history download/store lives under:
    - `tools/download_market_data.py`
    - `tradingagents/dataflows/market_data_store.py`
  - Snapshot-aware universe loading lives under:
    - `tradingagents/backtest/data_loader.py`
    - `tools/build_sp500_snapshots.py`

Partially completed:
- Optimizer backend/fallback policy exists, but deterministic relaxation order is still basic.
- Risk model exists (shrunk covariance), but no factor exposure model yet.
- Snapshot-aware universe support exists, but date-aware runtime is still default-off and historical membership quality depends on the snapshot/event inputs.
- A/B and reproducibility tooling exists, but batch walk-forward and stress-grid orchestration are not yet first-class.
- Architectural separation is not yet clean:
  - active portfolio modules and legacy TradingAgents graph still share one top-level package and one repo narrative.

Not completed:
- Production-grade historical universe snapshots (anti-survivorship policy).
- Official benchmark constituent/weight integration for benchmark-relative construction.
- Factor-risk model path and richer active risk budgets in optimizer.
- Walk-forward and stress grid orchestration.
- Clean module boundary between:
  - active alpha/portfolio/backtest code, and
  - legacy TradingAgents graph/agents/LLM workflow.

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
- Status update: threshold/significance gates now implemented as configurable options (`ic_gate_*`) and kept disabled by default.
- Remaining gap: calibrate gate thresholds by universe/regime and validate via walk-forward.
- A/B calibration note (2026-03-01):
  - Gate-on variants under current momentum-heavy profile underperformed gate-off in full-window tests.
  - Diagnostic: high fallback frequency (many rebalance dates with zero signals passing gates) dominated behavior.
  - Action: keep gates default-off until signal quality/regime-conditional calibration improves.
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

### Primary runtime in use today
- The active portfolio workflow now runs through:
  - `tools/run_backtest.py`
  - `tradingagents/backtest/engine.py`
  - `tradingagents/alpha/model.py`
  - `tradingagents/portfolio/optimizer.py`
  - `tradingagents/portfolio/rebalance.py`
  - `tradingagents/portfolio/attribution.py`
- This is the path exercised by the main portfolio/backtest tests.

### Legacy TradingAgents graph is no longer the portfolio centerline
- `tradingagents/graph/trading_graph.py` still contains a `portfolio_mode`, but that path is not the validated research/backtest runtime.
- The graph/state stack remains largely debate/report-centric:
  - `tradingagents/graph/propagation.py`
  - `tradingagents/agents/utils/agent_states.py`
  - `tradingagents/graph/signal_processing.py`
- For planning purposes, graph integration is now a compatibility concern, not the main delivery path.

### Shared data layer remains useful
- The repo still benefits from shared market-data tooling under:
  - `tradingagents/dataflows/`
  - `tools/download_market_data.py`
  - `tradingagents/dataflows/market_data_store.py`
- This is the main area where the broader TradingAgents codebase still contributes directly to the active portfolio system today.

### Current architectural mismatch
- Documentation and package narrative still over-emphasize the legacy graph/LLM workflow even though active portfolio work now centers on deterministic local-data backtests.
- Result: repo structure and public story lag behind actual implementation.
- Config promotion paths also need to stay explicit:
  - alpha-only promotion via `tradingagents/alpha/profiles.py`
  - full backtest baseline promotion via repo-tracked JSON under `research/configs/`

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
The active portfolio target architecture should now be treated as a standalone quant pipeline with optional adapters, not as a mandatory downstream stage of the legacy analyst/research graph.

1. Alpha scoring layer:
- Convert market data and configured signal definitions into expected active returns per symbol.
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

### 4.1 Recommended Code Boundary
Recommended structural split inside the repo:

1. Shared data module:
- `tradingagents/dataflows/`
- responsibility:
  - vendor access,
  - market history download/store,
  - classification metadata,
  - deterministic local file layout.

2. Active portfolio module:
- `tradingagents/alpha/`
- `tradingagents/portfolio/`
- `tradingagents/backtest/`
- `tradingagents/regime/`
- responsibility:
  - signal generation,
  - risk modeling,
  - optimization,
  - rebalancing,
  - attribution,
  - evaluation.

3. Legacy TradingAgents module:
- `tradingagents/graph/`
- `tradingagents/agents/`
- `tradingagents/llm_clients/`
- `cli/`
- responsibility:
  - debate-driven single-name workflows,
  - LLM orchestration,
  - interactive UX.

### 4.2 Separation Recommendation
Recommended next architectural move:

- First, create a cleaner internal module boundary while keeping one repository.
- Only consider a separate package or repository after the active portfolio API stabilizes and consumers are clear.

Reasoning:
- The active portfolio code already behaves like a separate product surface.
- Forcing more work through `TradingAgentsGraph` would add coupling without improving the tested path.
- A staged internal split is lower-risk than an immediate repo/package extraction.

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
- Maintain only the minimum compatibility state needed for any graph-based or package-based callers.
- Do not treat graph-state expansion as a prerequisite for portfolio/backtest progress.

Add state keys:
- `universe`
- `alpha_scores`
- `target_weights`
- `current_weights`
- `rebalance_orders`

Gate:
- End-to-end run returns portfolio state object for a test universe.
- Remaining gap: state typing in `tradingagents/agents/utils/agent_states.py` is not fully portfolio-first, but this is now secondary unless the graph path becomes a real supported runtime.

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

## Phase 6: Module boundary cleanup (New)
Objectives:
- Reduce coupling between active portfolio code and the legacy TradingAgents graph/runtime.
- Make the active portfolio stack the explicit primary surface for research and backtesting.

Deliverables:
- Define and document the supported active portfolio entrypoints.
- Separate shared data utilities from legacy graph-only code paths.
- Stop requiring portfolio roadmap items to flow through `TradingAgentsGraph`.
- Add a migration note for any remaining portfolio-related graph APIs.

Gate:
- A new contributor can identify the active portfolio runtime without reading legacy graph code first.
- README and plan agree on which module path is primary.
- Legacy graph remains optional and does not block portfolio enhancements.

## 6) Interface/API Status

### Config additions in `tradingagents/default_config.py`
Implemented baseline keys:
- `portfolio_mode`
- `benchmark_symbol`
- `universe_source`
- `rebalance_frequency`
- `max_weight`
- `sector_cap`
- `turnover_limit`
- `risk_aversion`
- `transaction_cost_bps`
- Additional implemented controls now include:
  - `active_weight_cap`
  - `sector_active_weight_cap`
  - `tracking_error_target`
  - `snapshot_schedule_enabled`
  - regime-routing settings

Remaining interface work:
- add explicit `risk_model_type = covariance|factor`
- clarify which config keys belong to:
  - shared data layer,
  - active portfolio layer,
  - legacy graph layer

### State additions in `tradingagents/agents/utils/agent_states.py`
Implemented baseline portfolio fields:
- `universe`
- `alpha_scores`
- `target_weights`
- `current_weights`
- `rebalance_orders`

Status:
- these fields exist,
- but they are not the primary integration surface for current backtest work,
- and should be treated as compatibility-state fields unless the graph path is revived as a first-class runtime.

### Core active portfolio modules now implemented
- `tradingagents/alpha/model.py`
- `tradingagents/portfolio/risk_model.py`
- `tradingagents/portfolio/optimizer.py`
- `tradingagents/portfolio/rebalance.py`
- `tradingagents/portfolio/attribution.py`
- `tradingagents/backtest/engine.py`
- `tradingagents/regime/model.py`

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
- Alpha scores can be noisy and unstable, whether sourced from deterministic signals, regime routing, or any future model-based forecast layer.
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
- [ ] Confirm active portfolio module boundary and whether to keep separation internal-to-repo or promote it to a standalone package later.

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
- `notebooks/single_backtest_viewer.ipynb`
- `notebooks/ab_backtest_viewer.ipynb`
  - add visualizations for new diagnostic columns.

## 11) Next Execution Steps (Amended)
Priority 1 (architecture cleanup):
- Treat active portfolio/backtest as the primary module path.
- Update docs and code organization to reflect:
  - shared data layer,
  - active alpha/portfolio/backtest layer,
  - legacy TradingAgents graph layer.
- Strong recommendation:
  - do an internal module split first,
  - defer any separate package/repo extraction until the active portfolio API is stable.
- Acceptance:
  - plan, README, and entrypoints all identify the same primary runtime,
  - future portfolio enhancements no longer depend on graph-state integration.

Priority 2 (data correctness):
- Add universe snapshot support:
  - New input format: `data/universe/sp500/snapshots/sp500_membership_YYYY-MM-DD.csv`
  - Backtest can resolve snapshot per rebalance date (`snapshot_schedule_enabled=True`).
  - Current default is static latest snapshot for stability (`snapshot_schedule_enabled=False`).
  - Added snapshot build pipeline: `tools/build_sp500_snapshots.py`.
  - Acceptance: no forward-looking membership in historical windows.

Priority 3 (optimizer realism):
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

Priority 4 (risk model depth):
- Add optional factor risk model path:
  - Estimate simple market/beta and sector exposures.
  - Expose factor covariance + specific risk estimates.
  - Acceptance: optimizer can run in `risk_model_type = covariance|factor`.

Priority 5 (hardening and research loop):
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

Priority 6 (attribution correctness):
- Replace TC proxy with pre/post-constraint active-weight TC:
  - Persist unconstrained active weights and constrained active weights per rebalance.
  - Compute TC from their correlation and compare with current proxy.
  - Acceptance: attribution report includes both legacy proxy and corrected TC during transition.
  - Status update:
  - Backtest now passes unconstrained/constrained active weights into attribution diagnostics.
  - Remaining work: expose corrected TC explicitly in notebook dashboards as primary metric.

Priority 7 (regime adaptation):
- Add regime-aware alpha routing and evaluation:
  - Implement baseline rule-based regime detector (`risk_on`, `neutral`, `risk_off`) using benchmark trend and BTC-vs-GLD relative behavior.
  - Route alpha profiles by regime label at each rebalance.
  - Persist regime diagnostics (label, score, probabilities) in rebalance logs and equity rows.
  - Acceptance:
    - regime fields present for each rebalance,
    - profile switching deterministic under fixed data/config.
- Add regime transition controls:
  - Introduce hysteresis/min-hold option to reduce regime flip noise and turnover.
  - Acceptance:
    - reduced switch count without large IC degradation.
- Add regime A/B protocol:
  - Compare static profile vs regime-routed profiles across fixed windows.
  - Require split-period reporting (example: H2-2025 vs 2026) to validate observed regime effects.
  - Standardize run artifact layout as paired directories (`run_a`, `run_b`, `comparison.json`) under one A/B folder.
  - Enforce warmup-aware start-date handling in A/B runners to avoid invalid range alignment.
  - Acceptance:
    - saved delta table with performance and turnover metrics by subperiod.
    - paired A/B artifacts discoverable by notebook without manual path edits.

Priority 8 (legacy compatibility, only if needed):
- If there is a real user for graph-based portfolio mode, reduce it to a thin adapter over the active portfolio engine.
- Do not build new portfolio features directly into `TradingAgentsGraph` unless there is a specific consuming workflow that requires it.
- Acceptance:
  - graph path either:
    - delegates cleanly to the active portfolio engine, or
    - is explicitly documented as experimental/legacy.

## 12) Deferred TODOs (Framework Stage)
These are intentionally deferred while the project prioritizes framework completeness over alpha quality.

- TODO 1: IC threshold gate (signal pruning)
  - Rule: set a signal weight to zero when rolling IC is below a configurable minimum.
  - Purpose: prevent persistently weak signals from polluting composite alpha.
  - Status: implemented (configurable; default off).

- TODO 2: IC significance gate (robustness filter)
  - Rule: require minimum statistical strength (for example IC t-stat and/or hit-rate threshold) before allowing non-zero signal weight.
  - Purpose: avoid overreacting to noise in short IC histories.
  - Status: implemented (configurable; default off).

- TODO 3: Standardize research scripts on shared framework
  - Rule: migrate `research/hypothesis_analysis.py` and `research/threshold_sweep.py` to use shared run manager + manifest pattern.
  - Purpose: make research outputs consistently reproducible and easier to compare in one viewer.
  - Status: implemented in `research/hypothesis_analysis.py` and `research/threshold_sweep.py` (run-tagged output + `summary.csv` + `params.json` + `manifest.json`).

- TODO 4: Cross-run experiment registry and comparison report
  - Rule: add an index file (or parquet/csv table) that records all runs with key metrics for filtering and ranking.
  - Purpose: support repeatable parameter sweeps and apples-to-apples comparisons across experiments.
  - Status: implemented via `research/build_experiment_registry.py` and `research/common/experiment_registry.py` (emits `experiment_registry.csv` + `experiment_comparison.csv`).

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

- TODO 6: Regime model v2 (probabilistic / state-space)
  - Rule: extend from rule-based labels to probabilistic regimes (e.g., HMM/Markov-switching) and blend alpha weights by regime probabilities.
  - Required upgrades:
    - per-regime IC histories and confidence-aware shrinkage,
    - probability-weighted signal/profile blending,
    - transition-cost-aware switching controls.
  - Purpose: reduce hard-switch instability and improve robustness to regime transitions.
  - Status: pending after rule-based v1 baseline.

- Rationale for deferral:
  - Current stage is focused on architecture, data plumbing, and end-to-end workflow reliability.
  - High-quality stable IC is not yet expected; hard gating now may hide integration issues.

## 13) Review of `docs/reference/suggestions.md` + Plan Refinement (2026-03-01)

This section reviews the external suggestions in `docs/reference/suggestions.md` and maps them to actionable updates for this repository.

### Strong ideas worth keeping
- Process-first framing from the Fundamental Law (`IR = IC * sqrt(BR) * TC`) is directionally correct and aligns with current diagnostics.
- Explicit unconstrained-vs-constrained optimizer comparison for TC is a strong audit control and should remain mandatory.
- Explicit signal lifecycle management (standardization, volatility-aware scaling, decay/half-life) is a practical bridge from raw scores to tradable alpha.
- Scheduled skill-vs-luck checks (`IR * sqrt(Time)`) are useful as governance metrics.

### Suggestions that need adaptation for TradingAgents
- Benchmark choice should stay configurable (`SPY`, `QQQ`, or mandate-specific benchmark) rather than fixed in plan text.
- "Residual volatility scaling" depends on factor-model depth; until factor risk path is complete, keep this as optional mode with clear fallback.
- "Do not change strategy until T-stat < 1 for over a year" is too rigid for framework-stage work; continue controlled A/B upgrades with fixed data and explicit deltas.

### Refined execution priorities (added)
Priority A (alpha translation hardening):
- Enforce cross-sectional z-score normalization as explicit pre-optimizer step in all default profiles.
- Add optional alpha volatility-scaling mode:
  - `none` (default for backward compatibility),
  - `total_vol`,
  - `residual_vol` (enabled only when factor path is present).
- Add per-signal half-life decay controls in profile config and alpha aggregation.
- Acceptance:
  - unit tests for z-score normalization behavior, scaling modes, and half-life decay monotonicity.

Priority B (IC governance + horizon audit):
- Standardize IC metrics at 1/2/4 rebalance horizons in both per-date logs and run summaries.
- Add quarterly governance metrics:
  - trailing realized active IR,
  - `IR * sqrt(Time)` t-stat proxy,
  - fallback frequency (dates with zero passed signals after gates).
- Treat suggested IC band (`0.02-0.07`) as a monitoring target, not a hard gate.
- Acceptance:
  - metrics output includes these fields and notebook viewer renders them.

Priority C (breadth and signal diversification):
- Require at least 3 distinct default alpha families in the baseline profile pack (for example momentum, risk/volatility, and breakout/volume).
- Add correlation diagnostics across active signals and report effective breadth proxy in research summaries.
- Acceptance:
  - research artifacts include signal correlation table and breadth proxy trend.

Priority D (constraint tax + cost realism):
- Make corrected TC (pre/post-constraint active-weight correlation) the primary reported TC metric; keep legacy proxy only for transition/debug.
- Extend transaction-cost model from fixed bps to optional two-part model:
  - fixed bps,
  - turnover impact multiplier.
- Continue TE target calibration with benchmark weights from official constituent history when available.
- Acceptance:
  - attribution outputs corrected TC as default and reports cost decomposition.

Priority E (validation protocol tightening):
- Add walk-forward + stress matrix orchestrator over:
  - transaction cost levels,
  - turnover limits,
  - universe size,
  - rebalance frequency.
- Preserve current required matched A/B protocol for material model/optimizer/attribution changes.
- Acceptance:
  - consolidated multi-run comparison table with reproducible manifests.

## Assumptions and Defaults Chosen
- Save location: `docs/plans/active-portfolio-plan.md`.
- First implementation stack: PyPortfolioOpt baseline, with extension points for Riskfolio-Lib/cvxportfolio later.
- Initial operating mode: long-only active weights versus benchmark, weekly rebalance, constrained turnover.
