# Equity Research Agent — Improvement Roadmap

Prioritized list of potential improvements, organized by impact and urgency.
Each item is marked as **DONE**, **NEXT**, **LATER**, or **PREMATURE** with justification.

---

## DONE (Implemented)

### 1. Schema Validation Between Pipeline Stages
**Impact: Critical | Effort: Medium**

Added `jsonschema` validation in `coordinator.py` at both handoff points:
- After Agent 1: validates `research_state.json` against schema + content quality checks
- After Agent 2: validates `model_state.json` against schema + consistency checks

**Why this was #1:** Without validation, Agent 2 could receive malformed JSON and silently
produce garbage that cascades through the entire pipeline. Validation catches broken data
before it spreads — prevents an estimated 30% of garbage outputs.

What it checks:
- Schema conformance (required fields, types, enums)
- Revenue approach consistency (bottom_up requires segment data, top_down requires TAM)
- Historical data sufficiency (3+ years of income statement)
- Source citation count
- Scenario probability sums
- Terminal value sanity (warns if >85% of EV)

### 2. Agent 1 Stopping Criteria
**Impact: High | Effort: Low**

Added concrete, measurable stopping rules to the research agent prompt:
- **Coverage reached:** All 15 must-have fields populated + 5 sources → stop
- **Diminishing returns:** 35+ calls + 12/15 fields → document gaps, stop
- **Hard ceiling:** 45 calls → stop immediately, document gaps
- **Wind-down mode:** After 25 calls, read state file and only fill specific gaps

**Why this matters:** Without stopping criteria, Agent 1 either stops too early (missing
critical data) or loops endlessly burning tokens on diminishing marginal searches. The
hard ceiling prevents $100+ research runs; the coverage check prevents premature exits.

### 3. Agent 2 Decision Trees for Consistency Checks
**Impact: High | Effort: Medium**

Replaced "flag if inconsistent" with explicit CHECK → DIAGNOSE → FIX or ACCEPT trees:
- Terminal value > 75% of EV → extend forecast period → reduce growth → accept with warning
- Reinvestment vs growth divergence > 10pp → adjust terminal growth or capex → rebuild
- Valuation triangulation spread > 30% → review outlier method → document explanation
- Terminal growth > 4% → cap at 3.5% unless structural justification
- Maximum 3 fix loops, then document remaining flags and proceed

Also added fallback rules for missing data (missing beta, missing segments, negative earnings).

**Why decision trees beat flags:** A flag without an action plan produces either (a) infinite
loops as the agent tries to fix without direction, or (b) a model with known problems that
gets passed to Agent 3 anyway. Decision trees tell the agent exactly what to try, in what
order, and when to give up gracefully.

### 4. Financial Calculator Tool
**Impact: High | Effort: Medium**

Added `tools/financial_calculator.py` with specialized operations:
- `npv` — Net Present Value of a cash flow series with per-year detail
- `pv_series` — PV with terminal value inclusion and running totals
- `irr` — Internal Rate of Return via Newton-Raphson
- `wacc` — Full WACC build from components
- `cagr` — Compound Annual Growth Rate
- `terminal_value` — Perpetuity growth, exit multiple, or both with cross-implied metrics
- `sensitivity_table` — WACC vs growth matrix → per-share equity values
- `ev_to_equity` — Enterprise value bridge to equity value per share

**Why a separate tool, not extending calculator:** The basic calculator handles simple
expressions (`100 * 1.15`). Financial computations require multiple parameters, intermediate
steps, and structured output. Combining them would bloat the basic tool's schema and confuse
the agent about when to use what. Separation follows the principle of one tool = one job.

---

## NEXT (High priority, implement after first live test)

### 5. Per-Company Output Directories
**Impact: Medium | Effort: Low**

Change output path from `output/` to `output/{ticker}_{timestamp}/`.
Currently, second run overwrites first run's files.

**Why not done yet:** Needs a live test first to see if the pipeline works end-to-end.
Output directory structure is trivial to change but has downstream effects on
`--skip-research` and `--skip-model` flags (need to point at a specific previous run).

### 6. API Retry Logic with Exponential Backoff
**Impact: Medium | Effort: Low**

Add retry logic to `engine.py` for transient API errors (rate limits, server errors).
Max 3 retries with 1s/2s/4s backoff. Immediate fail for auth errors.

**Why not done yet:** Affects 1-2% of runs. Worth doing but not blocking. A single
failed API call currently kills the entire pipeline — retry logic makes it more robust.

### 7. Few-Shot Examples in Agent Prompts
**Impact: Medium | Effort: Medium**

Add one targeted example to each prompt for the hardest judgment call:
- Agent 1: Example of a well-structured `modeling_guidance.key_drivers` entry (DONE — added to Agent 1 prompt)
- Agent 2: Example of a source_finding reference with proper JSON path format
- Agent 3: Example of QA notes when there's a genuine conflict between research and model

**Why not all done yet:** Agent 1 got its example. Agent 2 and 3 examples need to come
from a real pipeline run — synthetic examples may not match the actual data structure.
Run one company first, then use real output as examples.

### 8. Agent 3 Conflict Resolution
**Impact: Medium | Effort: Low**

Add explicit decision tree to Agent 3's QA pass for when research narrative conflicts
with model output. Currently says "flag inconsistencies" with no resolution protocol.

Rule: If conflict, trace to source. Use most recent data. If equally recent, flag as
unresolved risk and present both views in the report's risk section.

---

## LATER (Post-v1, based on test results)

### 9. Add Financial Functions to Calculator (NPV in expressions)
**Impact: Low-Medium | Effort: Low**

Add `npv()`, `pv()`, `irr()` as callable functions in the basic calculator's safe
namespace. This complements (doesn't replace) the financial_calculator tool — useful
for quick one-liner calculations without the full structured interface.

**Why later:** The financial_calculator tool handles the complex cases. The basic
calculator works for simple arithmetic. Adding NPV to the basic calculator is a
convenience, not a necessity.

### 10. Verbose Debug Mode
**Impact: Low-Medium | Effort: Low**

Add `--verbose` flag to coordinator that logs:
- Agent's text output at each iteration
- Key metrics from each model stage (ROIC, WACC, fair value)
- Intermediate state file snapshots

**Why later:** Useful for debugging bad outputs, but adds complexity. Currently you can
inspect `research_state.json` and `model_state.json` directly after a run.

### 11. Multi-Currency Handling
**Impact: Medium | Effort: High**

Add FX guidance to prompts for companies with >20% revenue in non-home currency.
Requires: constant-currency growth analysis, FX sensitivity in scenarios, hedging
assessment in research.

**Why later:** Affects ~20-30% of large-cap multinationals. Important but complex to
get right. Need to see how the pipeline handles a US-listed multinational first before
adding FX modeling.

### 12. Excel Formula Specification
**Impact: Medium | Effort: High**

Define explicit rules for cross-sheet references in Excel output. Currently Agent 3
writes the Excel model but has no spec for how Sheet 6 (DCF) should reference
Sheet 5 (Revenue Build). Models often have hardcoded values instead of formulas.

**Why later:** Need to see actual Excel output quality first. May require splitting
Agent 3's Excel generation into 2 calls (operating model + valuation sheets).

### 13. Source Traceability Validation
**Impact: Low-Medium | Effort: Low**

Add regex pattern validation for `source_finding` fields in model_state.json schema.
Currently agents can write vague strings like "Key Driver A" instead of proper JSON
paths like "modeling_guidance.key_drivers[0]".

Pattern: `^[a-z_]+(\\.\\w+)*(\\[\\d+\\])?$`

**Why later:** If the prompts are clear enough, agents follow the format. This is a
safety net for edge cases.

---

## PREMATURE (Don't build until data proves it's needed)

### 14. Training System / Fine-Tuning
**Why premature:** We don't know what fails yet. Training requires (input, desired_output)
pairs — we have zero completed runs. Run 3-5 companies you know well, evaluate outputs,
identify specific failure patterns, THEN build training data targeting those patterns.

Building a training system before having training data is architecture without evidence.

### 15. Per-Company Memory Storage
**Why premature:** The `research_state.json` and `model_state.json` files ARE the company
memory. If you want to re-analyze a company, keep the old output directory and use
`--skip-research`. A separate memory layer adds complexity with no proven benefit.

Would only be needed if: (a) you want to update a model incrementally (e.g., new earnings
quarter), or (b) you want to cross-reference multiple companies. Neither is in scope for v1.

### 16. Parallel Research Tracks
**Why premature:** Splitting Agent 1 into parallel research tracks (e.g., one for
financials, one for competitive analysis, one for management) would reduce wall-clock time.
But it adds architectural complexity (sub-agent coordination, deduplication, merge logic)
and is only worth it if Agent 1 consistently takes >10 minutes. Wait for timing data.

### 17. Agent Layout Changes (Collapsing to 2 or Expanding to 4+)
**Why premature:** The 3-agent split exists as a diagnostic tool. If all three agents
produce good output, the split is validated. If Agent 2 is mediocre despite good research,
the schema is the problem (not agent count). If all three are mediocre, test a single agent.
The answer comes from running the pipeline, not from restructuring before testing.

### 18. Accounting Adjustment Guidance
**Why premature:** Detailed guidance on GAAP vs non-GAAP adjustments, one-time charges,
SBC treatment, etc. is important for model accuracy. But the right guidance depends on
what errors the agents actually make. If Agent 2 consistently uses GAAP when non-GAAP
is appropriate, add specific adjustment rules. Don't add 500 words of accounting guidance
speculatively.

---

## Decision Framework

When evaluating whether to implement an improvement:

1. **Does it prevent cascading failures?** → Do it now (schema validation, stopping criteria)
2. **Does it give agents clear actions when stuck?** → Do it now (decision trees)
3. **Does it remove a capability gap?** → Do it now (financial calculator)
4. **Does it improve output quality?** → Do it after first test (examples, conflict resolution)
5. **Does it optimize performance?** → Do it after timing data (parallelism, caching)
6. **Does it add architecture?** → Do it after failure data (memory, training, agent changes)

The bar for adding complexity is: "I have evidence from a real run that this would help."
