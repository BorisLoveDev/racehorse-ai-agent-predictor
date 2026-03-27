# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — MVP

**Shipped:** 2026-03-27
**Phases:** 3 | **Plans:** 14 | **Tasks:** 21

### What Was Built
- Full Telegram pipeline: paste text → LLM parse → confirm → web research → AI analysis → Kelly sizing → recommendation
- Result evaluation with P&L tracking (placed vs tracked distinction)
- AI reflection pipeline: mindset.md entries + structured lesson extraction → injection into next analysis
- Drawdown circuit breaker with inline unlock button
- /stats command with all-time, 30-day, 7-day views
- 210 unit tests, 5,435 LOC service code, 3,589 LOC test code

### What Worked
- ARCH-01 (deterministic math) caught early and enforced — no LLM-generated bet amounts anywhere
- Wave-based parallel execution: Phase 3 waves 2-3 ran 2 agents in parallel per wave
- LangGraph node composition: each pipeline step is an independent async function, easily testable
- TDD approach in math-heavy modules (odds, Kelly, evaluator) caught edge cases before integration
- Pydantic structured output for LLM parsing — eliminates regex fragility

### What Was Inefficient
- Phase 1 lacked VERIFICATION.md — only Phase 3 had formal verification, creating tech debt
- settings.py defaults drifted from spec (half-Kelly instead of quarter-Kelly) — caught only at milestone audit
- Some SUMMARY.md files missing requirements_completed frontmatter — weakened traceability

### Patterns Established
- `BaseModel` for nested settings (not `BaseSettings`) — avoids env var conflicts with nested delimiter
- `with_structured_output()` pattern for all LLM extraction (parser, result parser, lesson extractor)
- Non-blocking reflection: try/except wraps LLM calls, FSM transitions happen before reflection completes
- Short callback prefixes (st:, sr:, sd:) for Telegram 64-byte limit

### Key Lessons
1. Run verification on every phase, not just the last — Phase 1+2 gaps only surfaced at milestone audit
2. Settings defaults should match the spec from day one — env var configurability doesn't excuse wrong defaults
3. Drawdown UX needs buttons, not just commands — users don't remember /unlock_drawdown exists

### Cost Observations
- Model mix: ~5% opus (planning), ~90% sonnet (execution/verification), ~5% haiku (none used)
- Notable: Quick task (2-line keyboard fix) was faster inline than spawning planner+executor agents

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Plans | Key Change |
|-----------|--------|-------|------------|
| v1.0 | 3 | 14 | First milestone — established wave-based parallel execution |

### Cumulative Quality

| Milestone | Tests | LOC (service) | LOC (tests) |
|-----------|-------|---------------|-------------|
| v1.0 | 210 | 5,435 | 3,589 |

### Top Lessons (Verified Across Milestones)

1. Verify every phase, not just the final one — gaps compound silently
2. ARCH-01 (deterministic math) is non-negotiable for anything involving money
