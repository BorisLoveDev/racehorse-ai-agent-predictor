# Horse Racing Advisor — Phase 1 Architecture

Phase 1 is **paper-only**. Physical betting is disabled by invariant I1. The
agent walks the 11-step spec pipeline for every race, records calibration
samples for every runner, and emits approval cards labelled `[PAPER]` so the
user exercises the UX end-to-end without risk.

## 11-step graph

```
ingest → parse → interrupt_gate → research → probability_model →
analyst → sizer → decision_maker → interrupt_approval →
result_recorder → settlement → reflection_update
```

Two LangGraph `interrupt()` pauses: `interrupt_gate` (Tier-1 overround /
missing-fields filter) and `interrupt_approval` (per-slip approval card).
Checkpointer: `AsyncSqliteSaver` at `data/checkpoints.db`; one `thread_id`
per race (`race:{race_id}:{user_id}`).

## Non-negotiable invariants

| ID | Rule | Enforced at |
|----|------|-------------|
| I1 | Agent never places a live bet without `mode=live` AND `live_unlock=true`. In Phase 1 `live_unlock` is hard-wired to `false`. | config loader, startup checker, sizer, interrupt_approval |
| I2 | LLM never emits a probability. Only `LLMAdjustment {direction, magnitude}` allowed; Python maps to bounded pp shift (≤ ±3pp total per horse). | analyst post-processor, LLMAdjustment pydantic `extra="forbid"` |
| I3 | Parser must-have fields require `raw_excerpt`. Missing excerpt → field treated as missing → interrupt_gate. | parser prompt + validator |
| I4 | Sizer reads only `p_calibrated`. Reflection reads lessons, never writes stakes. | sizer input contract |
| I5 | Kelly input edge = `p_calibrated − p_market`. `edge < min_edge_pp` ⇒ paper-only intent, never promoted. | sizer `compute_proposed_slip` |
| I6 | Drawdown, daily, per-bet caps enforced BEFORE `ProposedBetSlip` is emitted. | sizer node + InvariantChecker.check_drawdown/check_sizing_caps |
| I7 | Checkpoint persists before any irreversible user-visible action. | AsyncSqliteSaver pre-interrupt persistence (LangGraph built-in) |
| I8 | `live` forbidden if `audit.reproducible=false` on any of last 10 races. | InvariantChecker.check_reproducibility_for_live |
| I9 | `paper → live` transition requires ≥200 paper samples, Brier ≤ 0.22, reproducibility ≥ 95% on last 10, explicit `/promote_live` command. | future handler (deferred beyond Phase 1) |

## Data contracts (Phase 1)

- `BetIntent { market, selections, confidence, rationale_id, edge_source }` —
  LLM-authored, no money.
- `LLMAdjustment { target_horse_no, direction, magnitude, rationale }` —
  Python maps to bounded pp shift.
- `ProposedBetSlip` — adds `stake`, `kelly_fraction_used`, `max_loss`,
  `profit_if_win`, `portfolio_var_95`, `caps_applied`, `sizing_params`, `mode`.
  `risk_95` from the original v1.0 spec was replaced by this triplet because
  a single binary bet has `VaR95 == max_loss` by definition; the triplet
  surfaces the actual quantities a user needs to judge the bet.
- `BetSlip` — adds `id` (UUID), `race_id`, `user_id`, `idempotency_key`,
  `status` (draft|confirmed|cancelled|expired), `confirmed_at`, `user_edits`.
- `AuditTrace { schema_version, race_id, thread_id, started_at,
  finished_at, reproducible, steps, total_cost_usd }` with
  `reproducible=True` iff every step used `temperature ≤ 0.1` AND no error.
- `Lesson { id, created_at, tag, condition, action, evidence_bet_ids,
  pnl_track, status, confidence }`.

## Overround thresholds (per market)

| Market | interrupt | hard_skip |
|--------|-----------|-----------|
| win | 0.12 | 0.15 |
| place | 0.15 | 0.18 |
| quinella / exacta | 0.17 | 0.20 |
| trifecta / trifecta_box / first4 | 0.30 | 0.35 |

Above `hard_skip` the gate payload has `options=["skip"]` only. Between
`interrupt` and `hard_skip` the user sees `["continue", "skip", "ask"]`.

## Calibrator registry

Hierarchical lookup: `track → market → default`. Phase 1 always returns
`IdentityCalibrator` at every level. Phase 3 plugs in Platt / isotonic
calibrators with conservative promotion thresholds (100 samples global,
300 per market, 500 per track). `StubShiftCalibrator` in
`tests/stake/e2e/_helpers.py` is a test-only helper that shifts
probabilities by a fixed pp amount to drive e2e scenarios where
positive edge must exist; it is never wired in production.

## Mode progression (Phase 2+)

`paper → live` requires ALL of:

- ≥ 200 paper samples with settled outcomes
- Brier score ≤ 0.22 on the last 90-day window
- `reproducible` flag true on ≥ 9 of last 10 audit traces
- Explicit `/promote_live <token>` command with printed confirmation

Phase 1 hard-wires `live_unlock=false` in config. Any config attempting
`mode: live` raises `InvariantViolation(I1)` at `load_config()`.

## Storage

- `data/stake.db` — production data (bankroll, bet slips, samples, lessons,
  audit traces).
- `data/checkpoints.db` — LangGraph checkpoints (AsyncSqliteSaver).

All tables are prefixed `stake_` per project convention. New Phase 1
tables: `stake_bet_slips`, `stake_calibration_samples`, `stake_audit_traces`.

## Key modules

- `services/stake/config/` — YAML loader with I1 enforcement.
- `services/stake/invariants/` — I1..I9 definitions + runtime checker.
- `services/stake/contracts/` — Pydantic v2 BetIntent/ProposedBetSlip/
  BetSlip/LLMAdjustment/AuditTrace/Lesson.
- `services/stake/probability/` — ProbabilityModel + CalibratorRegistry.
- `services/stake/calibration/` — samples repository.
- `services/stake/pipeline/` — checkpointer singleton, interrupt payloads,
  run_or_resume helper, compile_race_graph, all node factories.
- `services/stake/telegram_bridge/` — renderers, resume_router,
  TelegramGraphRunner.
- `services/stake/handlers/risk_commands.py` — `/kill` and `/resume`.
- `services/stake/main.py` — `build_runtime()` assembles everything. The
  legacy `main()` coroutine for the pre-Phase-1 parse→calc→format graph
  still ships in the same module; switching the process entry point to
  `build_runtime()` is a Phase 2 wiring step.
