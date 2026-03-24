---
phase: 01-foundation-and-parser
plan: "06"
subsystem: infra
tags: [docker, docker-compose, entrypoint, stake, migrations]

# Dependency graph
requires:
  - phase: 01-foundation-and-parser plan 05
    provides: stake service code at services/stake/main.py and bankroll migrations module
provides:
  - Docker 'stake' build target in Dockerfile
  - stake service definition in docker-compose.yml with all env vars
  - STAKE_PARSER__MODEL configurability at deployment time (PARSE-02)
  - D-02 telegram conflict warning documented in docker-compose.yml
  - entrypoint.sh runs stake migrations with ImportError fallback
affects:
  - deployment
  - production (Coolify)
  - human verification checkpoint

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Docker multi-stage target: add FROM base AS <service> + CMD pattern"
    - "docker-compose env var override via ${VAR:-default} syntax for parser model configurability"
    - "entrypoint.sh ImportError guard for service-specific migrations"

key-files:
  created: []
  modified:
    - Dockerfile
    - docker-compose.yml
    - entrypoint.sh

key-decisions:
  - "stake service added as opt-in — telegram service must be explicitly stopped first (D-02 comment in docker-compose)"
  - "STAKE_PARSER__MODEL uses ${STAKE_PARSER_MODEL:-google/gemini-2.0-flash-001} default in docker-compose so it's always overridable without rebuilding"
  - "entrypoint.sh uses try/except ImportError to safely skip stake migrations for existing tabtouch services"

patterns-established:
  - "D-02 compliance: same-bot-token services documented with explicit warning comment"
  - "Stake env vars use STAKE_ prefix matching StakeSettings.env_prefix in settings.py"

requirements-completed: [PIPELINE-01, PIPELINE-02, PIPELINE-03, PIPELINE-04, PIPELINE-05, INPUT-01, INPUT-02, BANK-02, BANK-03, BANK-04, AUDIT-01]

# Metrics
duration: 5min
completed: 2026-03-24
---

# Phase 01 Plan 06: Docker Integration and Deployment Summary

**STATUS: PARTIAL — Task 1 complete, Task 2 (human-verify checkpoint) pending**

**Stake advisor Docker target wired with `racehorse-stake` service, STAKE_PARSER__MODEL configurability, and safe entrypoint migration guard**

## Performance

- **Duration:** ~5 min (Task 1 only)
- **Started:** 2026-03-24T06:25:00Z
- **Completed (partial):** 2026-03-24T06:28:26Z
- **Tasks:** 1 of 2 (Task 2 is checkpoint:human-verify)
- **Files modified:** 3

## Accomplishments

- Added `FROM base AS stake` target to Dockerfile with correct CMD entry point
- Added `stake` service definition to docker-compose.yml with all required env vars (STAKE_REDIS__URL, STAKE_DATABASE_PATH, STAKE_AUDIT__LOG_PATH, STAKE_TELEGRAM_BOT_TOKEN, STAKE_TELEGRAM_CHAT_ID, STAKE_OPENROUTER_API_KEY, STAKE_PARSER__MODEL, STAKE_PARSER__TEMPERATURE, STAKE_PARSER__MAX_TOKENS)
- Added D-02 warning comment block in docker-compose.yml explaining telegram must be stopped before starting stake
- Updated entrypoint.sh to run `run_stake_migrations` with try/except ImportError so existing tabtouch services are unaffected

## Task Commits

1. **Task 1: Add Docker target, compose service with all env vars, and telegram service guard** - `8d0b002` (feat)
2. **Task 2: Verify end-to-end bot flow in Telegram** - PENDING (checkpoint:human-verify)

## Files Created/Modified

- `Dockerfile` - Added `FROM base AS stake` + `CMD ["python3", "services/stake/main.py"]` after telegram target
- `docker-compose.yml` - Added stake service with full env var set including STAKE_PARSER__MODEL (PARSE-02 configurability)
- `entrypoint.sh` - Updated db_path fallback to check STAKE_DATABASE_PATH; added run_stake_migrations call with ImportError guard

## Decisions Made

- Used comment-based D-02 warning (not Docker profiles) to avoid breaking existing tabtouch deployments that rely on default `docker compose up`
- STAKE_PARSER__MODEL defaults to `google/gemini-2.0-flash-001` — override via `STAKE_PARSER_MODEL` env var in .env without rebuild
- STAKE_ prefix env vars map to StakeSettings via env_nested_delimiter="__" per existing Pydantic settings pattern

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

**Task 2 checkpoint pending.** To complete plan verification:

```bash
docker compose stop telegram && docker build -f Dockerfile -t racehorse-base:latest --target base . && docker compose up -d stake redis
```

Then verify in Telegram per the checkpoint how-to-verify steps in 01-06-PLAN.md.

If any step fails, consult the failure-routing table in Task 2 of the plan for targeted re-execution.

## Next Phase Readiness

- Task 1 complete: Docker infrastructure ready for deployment
- Task 2 (human verification) must be completed before Phase 01 is fully done
- Once verified, Phase 01 requirements PIPELINE-01 through AUDIT-01 are satisfied

---
*Phase: 01-foundation-and-parser*
*Partial completion: 2026-03-24*
