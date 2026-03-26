---
phase: 02-ev-engine-and-analysis
plan: "01"
subsystem: data-contracts
tags: [models, pydantic, settings, pipeline-state, phase2]
dependency_graph:
  requires: []
  provides:
    - services.stake.analysis.models (ResearchResult, ResearchOutput, RunnerAnalysis, AnalysisResult, BetRecommendation)
    - services.stake.pipeline.state.PipelineState (Phase 2 fields)
    - services.stake.settings.SizingSettings
    - services.stake.settings.ResearchSettings.provider
  affects:
    - services/stake/pipeline/state.py
    - services/stake/settings.py
tech_stack:
  added: []
  patterns:
    - "Pydantic BaseModel for data contracts (not BaseSettings — per established pattern)"
    - "TypedDict with Optional fields for LangGraph state (Redis FSM serialisation compatible)"
    - "dict fields in TypedDict for Pydantic model data (model_dump() round-trip)"
key_files:
  created:
    - services/stake/analysis/__init__.py
    - services/stake/analysis/models.py
    - services/stake/pipeline/research/__init__.py
  modified:
    - services/stake/pipeline/state.py
    - services/stake/settings.py
decisions:
  - "TypedDict uses dict fields (not Pydantic models) for research_results, analysis_result, final_bets — state passes through Redis FSM which requires JSON-serialisable types; model_dump() used at write, model_validate() at read"
  - "SizingSettings extends BaseModel (not BaseSettings) — consistent with established pattern from Phase 1 to avoid env loading issues with nested BaseSettings"
  - "ResearchSettings.provider defaults to 'online' (OpenRouter) not 'searxng' — simpler dependency, no local server needed for development"
metrics:
  duration: "123 seconds"
  completed_date: "2026-03-26"
  tasks_completed: 2
  files_created: 3
  files_modified: 2
---

# Phase 2 Plan 01: Phase 2 Data Contracts Summary

Phase 2 data contracts defined: 5 Pydantic models, extended PipelineState with 8 new fields, SizingSettings with quarter-Kelly defaults, and ResearchSettings with configurable provider.

## What Was Built

All Phase 2 interfaces are now importable. Downstream plans (02, 03, 04) can implement against stable contracts without coordination overhead.

### Task 1: Phase 2 Pydantic Models and Packages

Created `services/stake/analysis/` package with 5 Pydantic data contract models:

- **ResearchResult** — per-runner research output (form, trainer, expert opinion, data_quality signal)
- **ResearchOutput** — aggregated research for all runners + overall race context
- **RunnerAnalysis** — AI-assigned probabilities + label + reasoning per runner
- **AnalysisResult** — race-level analysis with skip signals, AI override, market discrepancy notes
- **BetRecommendation** — final sized bet with EV, kelly_pct, usdt_amount, sparsity flag

Created `services/stake/pipeline/research/` package (empty `__init__.py`) as placeholder for Phase 2 research nodes.

### Task 2: PipelineState and Settings Extensions

Extended `PipelineState` with 8 Phase 2 fields:
- `skip_signal`, `skip_reason`, `skip_tier` — race-level skip decision (Tier 1 pre-analysis, Tier 2 post-analysis)
- `research_results`, `research_error` — research node output as dict
- `analysis_result` — analysis node output as dict
- `final_bets` — list of BetRecommendation dicts after portfolio caps
- `recommendation_text` — formatted Telegram message

Added `SizingSettings` to `settings.py`:
- `kelly_multiplier=0.25` (quarter-Kelly per BET-02)
- `per_bet_cap_pct=0.03` (3% max single bet per BET-03)
- `max_total_exposure_pct=0.05` (5% max race exposure per BET-04)
- `skip_overround_threshold=15.0` (Tier 1 skip trigger per BET-05/D-06)
- `min_bet_usdt=1.0`, `sparsity_discount=0.5`
- All configurable via `STAKE_SIZING__*` env vars

Extended `ResearchSettings` with `provider` (default: "online") and `searxng_url` fields per SEARCH-02/D-05.

## Deviations from Plan

None — plan executed exactly as written.

## Verification

All acceptance criteria met:

- `from services.stake.analysis.models import ResearchResult, ResearchOutput, RunnerAnalysis, AnalysisResult, BetRecommendation` — passes
- `get_stake_settings().sizing.kelly_multiplier == 0.25` — confirmed
- `get_stake_settings().sizing.skip_overround_threshold == 15.0` — confirmed
- `get_stake_settings().research.provider == "online"` — confirmed
- PipelineState type hints include all 8 Phase 2 fields — confirmed
- All 84 Phase 1 tests pass — confirmed

## Known Stubs

None. This plan defines data contracts only — no data sources wired yet. Contract models are intentionally empty structures awaiting Phase 2 plan 02 (research) and 03 (analysis) implementation.

## Self-Check: PASSED

Files created/modified:
- FOUND: services/stake/analysis/__init__.py
- FOUND: services/stake/analysis/models.py
- FOUND: services/stake/pipeline/research/__init__.py
- FOUND: services/stake/pipeline/state.py (modified)
- FOUND: services/stake/settings.py (modified)

Commits:
- FOUND: 0ce16fc — feat(02-01): add Phase 2 Pydantic data contract models and packages
- FOUND: 5879af2 — feat(02-01): extend PipelineState and Settings for Phase 2
