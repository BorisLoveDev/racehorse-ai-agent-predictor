# Phase 2: EV Engine and Analysis - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-25
**Phase:** 02-ev-engine-and-analysis
**Areas discussed:** Research strategy, EV/Kelly math engine, AI analysis output, Skip signal

---

## Research Strategy

### Primary search provider
| Option | Description | Selected |
|--------|-------------|----------|
| OpenRouter online model first | Use online-capable LLM as primary — built-in web access, single API call. SearXNG as fallback. | ✓ |
| SearXNG first | SearXNG queries per runner (already on Meridian, free). OpenRouter online model as fallback. | |
| Both in parallel | Run SearXNG + online model simultaneously, merge results. More thorough but doubles cost. | |

**User's choice:** OpenRouter online model first
**Notes:** User emphasized online mode as primary search method.

### Research structure
| Option | Description | Selected |
|--------|-------------|----------|
| One call per runner | More thorough — each runner gets focused research. Higher cost. | |
| Batch all runners in one call | Single LLM call with all runners. Cheaper, faster. | |
| You decide | Claude picks approach | |

**User's choice:** Custom — Research orchestrator pattern
**Notes:** User wants expensive senior agent (gemini-pro) to create a research plan, then cheap sub-agents (flash-lite) execute it. Senior agent decides per-runner vs batch strategy autonomously. Sub-agent spawning required.

### Research data priorities
| Option | Description | Selected |
|--------|-------------|----------|
| Recent form & race results | Last 3-5 starts, finishing positions | |
| Trainer/jockey stats | Win rates, recent form | |
| Expert tips & predictions | Racing tipster opinions | |
| Track/conditions analysis | Track bias, weather, distance suitability | |

**User's choice:** "Senior agent decides what it needs"
**Notes:** Full autonomy to the orchestrator agent — no hardcoded research template.

---

## EV/Kelly Math Engine

### Pre-analysis skip threshold
| Option | Description | Selected |
|--------|-------------|----------|
| 15% margin (1.15 overround) | Industry standard. Configurable via env. | |
| 20% margin (1.20 overround) | More lenient — allows tighter races through. | |
| You decide | Claude picks threshold, makes configurable | ✓ |

**User's choice:** You decide
**Notes:** —

### Kelly fraction default
| Option | Description | Selected |
|--------|-------------|----------|
| Quarter-Kelly (0.25x) | Conservative, matches BET-02 requirement. | |
| Flat 1% until calibrated | Even more conservative until 50+ resolved bets. | |
| You decide | Claude picks approach | ✓ |

**User's choice:** Senior agent makes important decisions, all computable math strictly in Python and passed to agent
**Notes:** User doesn't have preference on exact Kelly fraction — wants all deterministic math in Python, qualitative decisions delegated to senior agent.

---

## AI Analysis Output

### Presentation format
| Option | Description | Selected |
|--------|-------------|----------|
| Structured card per runner | Each runner gets a card with label, EV, amount, notes. | ✓ |
| Summary table + narrative | Table + AI analyst report style. | |
| You decide | Claude designs format | |

**User's choice:** Structured card per runner

### Output depth
| Option | Description | Selected |
|--------|-------------|----------|
| Numbers + brief reasoning | Labels, amounts, AND 2-3 sentence explanation per runner. | ✓ |
| Numbers only | Just labels and bet amounts. | |
| You decide | Claude picks detail level | |

**User's choice:** Numbers + brief reasoning

---

## Skip Signal

### Post-analysis AI override
| Option | Description | Selected |
|--------|-------------|----------|
| Yes — AI can override math | AI can recommend skip even when EV is positive. Adds "AI override" flag. | ✓ |
| No — math is final | If EV positive, always recommend. AI adds warnings only. | |
| Soft override | AI recommends skip but shows EV numbers alongside — user decides. | |

**User's choice:** Yes — AI can override math
**Notes:** User emphasized two-tier skip: (1) pre-analysis when odds are squeezed, (2) post-analysis when AI sees unfavorable situation. AI has full authority to say "don't bet."

---

## Claude's Discretion

- Exact overround threshold for pre-analysis skip
- Kelly fraction: quarter-Kelly vs flat 1%
- Research prompt design and sub-agent spawning strategy
- Telegram card layout and formatting
- LangGraph node structure
- Error handling for failed research/analysis
- Edge cases: all runners -EV, only 1 +EV, etc.
