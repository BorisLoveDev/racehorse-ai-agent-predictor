---
phase: 02-ev-engine-and-analysis
plan: "03"
subsystem: research
tags: [langchain, langgraph, openrouter, searxng, httpx, pydantic, react-agent, two-tier-orchestrator]

requires:
  - phase: 02-01
    provides: ResearchOutput/ResearchResult models in analysis/models.py, PipelineState with research fields, ResearchSettings/AnalysisSettings in settings.py

provides:
  - searxng_search @tool: async httpx search returning top-5 formatted results
  - online_model_search @tool: ChatOpenAI with web grounding via extra_body plugins
  - ORCHESTRATOR_SYSTEM_PROMPT: full autonomy research planning prompt (D-03/D-04)
  - SUB_AGENT_SYSTEM_PROMPT: concise prompt for cheap flash-lite sub-agents
  - ANALYSIS_SYSTEM_PROMPT: ARCH-01-enforcing prompt (no LLM bet amount generation)
  - research_node: three-phase LangGraph node (plan -> execute -> synthesize)
  - build_research_orchestrator: factory for senior LLM using settings.analysis.model
  - build_search_sub_agent: factory for cheap React agent using settings.research.model
  - ResearchPlan/SearchQuery: Pydantic models for Phase 1 structured planning output

affects:
  - 02-04 (analysis node uses ANALYSIS_SYSTEM_PROMPT and research_results from research_node)
  - pipeline graph wiring (research_node exported from research/__init__.py)

tech-stack:
  added: []
  patterns:
    - Two-tier orchestrator: expensive model (gemini-pro) plans + synthesizes; cheap model (flash-lite) executes searches via create_react_agent
    - Three-phase research node: Phase 1 plan (structured output ResearchPlan), Phase 2 execute (sub-agents), Phase 3 synthesize (structured output ResearchOutput)
    - Provider selection via settings.research.provider ('online'/'searxng') — no code changes needed to switch
    - skip_signal passthrough in research_node — no-op return {} preserves D-06 tier-1 skip

key-files:
  created:
    - services/stake/pipeline/research/tools.py
    - services/stake/pipeline/research/prompts.py
    - services/stake/pipeline/research/agent.py
    - services/stake/analysis/prompts.py
    - tests/stake/test_research_tools.py
  modified:
    - services/stake/pipeline/research/__init__.py

key-decisions:
  - "ResearchPlan/SearchQuery as internal Pydantic models for Phase 1 structured output — orchestrator plans into typed model before sub-agents execute"
  - "online_model_search tool uses research.model (flash-lite) not analysis.model — cheap sub-agents call the tool; build_search_sub_agent sets the model"
  - "Three-phase node makes two separate orchestrator LLM calls (plan + synthesize) — first with ResearchPlan output, second with ResearchOutput output"
  - "_build_runners_context falls back to parsed_race.runners if enriched_runners is empty — handles edge case where calc_node skipped"

patterns-established:
  - "Two-tier research: ORCHESTRATOR_SYSTEM_PROMPT drives both planning and synthesis calls; sub-agents are stateless single-query executors"
  - "Tool error handling: both tools return error strings rather than raising — sub-agent can continue with partial results"

requirements-completed: [SEARCH-01, SEARCH-02]

duration: 3min
completed: "2026-03-26"
---

# Phase 02 Plan 03: Research Layer Summary

**Two-tier research orchestrator with searxng_search/@online_model_search tools, three-phase research_node (plan/execute/synthesize), and ARCH-01-enforcing analysis prompt**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-26T12:51:47Z
- **Completed:** 2026-03-26T12:54:57Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- searxng_search and online_model_search @tool functions with full error handling and async httpx/ChatOpenAI respectively
- Three-phase research_node: expensive orchestrator (gemini-pro) creates ResearchPlan, cheap sub-agents (flash-lite) execute queries via create_react_agent, orchestrator synthesizes ResearchOutput
- ORCHESTRATOR_SYSTEM_PROMPT gives full autonomy per D-03/D-04 with 3-8 query guidance
- ANALYSIS_SYSTEM_PROMPT enforces ARCH-01: LLM never generates or modifies bet amounts
- 6 unit tests covering formatting, empty results, httpx exceptions, LLM exceptions, and content truncation

## Task Commits

1. **Task 1: Create research tools and prompts** - `69eff51` (feat)
2. **Task 2: Create two-tier research orchestrator and research_node** - `e10d97a` (feat)

**Plan metadata:** (docs commit to follow)

## Files Created/Modified

- `services/stake/pipeline/research/tools.py` - searxng_search and online_model_search @tool functions
- `services/stake/pipeline/research/prompts.py` - ORCHESTRATOR_SYSTEM_PROMPT and SUB_AGENT_SYSTEM_PROMPT
- `services/stake/pipeline/research/agent.py` - research_node, build_research_orchestrator, build_search_sub_agent, ResearchPlan, _build_runners_context
- `services/stake/pipeline/research/__init__.py` - exports research_node, build_research_orchestrator, build_search_sub_agent
- `services/stake/analysis/prompts.py` - ANALYSIS_SYSTEM_PROMPT (ARCH-01 enforcing)
- `tests/stake/test_research_tools.py` - 6 unit tests for tool error handling and formatting

## Decisions Made

- ResearchPlan/SearchQuery as internal Pydantic models used only for Phase 1 structured output — keeps the planning call typed without polluting the models module
- online_model_search uses research.model (flash-lite) when called by sub-agents — the tool itself reads settings dynamically; build_search_sub_agent sets model via ChatOpenAI constructor
- Two separate orchestrator calls (plan then synthesize) avoids mixing Pydantic schemas in a single call — cleaner error handling and easier to debug which phase failed
- _build_runners_context falls back to parsed_race.runners if enriched_runners is empty — defensive against edge cases

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- research_node exported from services.stake.pipeline.research — ready for wiring into LangGraph StateGraph
- ANALYSIS_SYSTEM_PROMPT ready for Plan 04 (analysis node)
- All 146 tests pass, no regressions

---
*Phase: 02-ev-engine-and-analysis*
*Completed: 2026-03-26*
