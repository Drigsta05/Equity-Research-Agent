"""
Coordinator: Sequential Pipeline
---------------------------------
Agent 1 → wait → Agent 2 → wait → Agent 3.
No routing logic, no decision trees, no orchestrator intelligence.
The file schemas do the coordination.

Schema validation between stages catches broken data before it cascades.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import jsonschema

from agents.engine import AgentConfig, AgentResult, run_agent
from prompts import agent1_research, agent2_model, agent3_writer
from tools import AGENT1_TOOLS, AGENT2_TOOLS, AGENT3_TOOLS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("coordinator")

OUTPUT_DIR = Path("output")
SCHEMA_DIR = Path("schemas")


# ──────────────────────────────────────────────────────
# Schema Validation
# ──────────────────────────────────────────────────────

class ValidationError(Exception):
    """Raised when a state file fails schema validation."""
    def __init__(self, stage: str, errors: list[str]):
        self.stage = stage
        self.errors = errors
        super().__init__(f"{stage} validation failed: {len(errors)} error(s)")


def _load_schema(schema_name: str) -> dict:
    """Load a JSON schema from the schemas directory."""
    path = SCHEMA_DIR / schema_name
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_state_file(
    filename: str,
    schema_name: str,
    stage_label: str,
) -> tuple[dict, list[str]]:
    """
    Validate a state file against its JSON schema.

    Returns:
        (parsed_data, errors) — errors is empty if validation passed.
    """
    path = OUTPUT_DIR / filename
    errors = []

    # Check file exists
    if not path.exists():
        return {}, [f"{filename} does not exist"]

    # Parse JSON
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return {}, [f"{filename} is not valid JSON: {e}"]

    # Validate against schema
    try:
        schema = _load_schema(schema_name)
    except FileNotFoundError:
        logger.warning("Schema %s not found, skipping validation", schema_name)
        return data, []

    validator = jsonschema.Draft7Validator(schema)
    for error in validator.iter_errors(data):
        # Build a human-readable path
        path_str = " → ".join(str(p) for p in error.absolute_path) or "(root)"
        errors.append(f"  [{path_str}] {error.message}")

    return data, errors


def _validate_research_completeness(data: dict) -> list[str]:
    """
    Check that research_state.json has the critical fields Agent 2 needs.
    Schema validation checks structure; this checks content quality.
    """
    warnings = []

    # Must-have content checks
    thesis = data.get("thesis", {})
    if not thesis.get("one_line"):
        warnings.append("thesis.one_line is empty — Agent 2 has no investment narrative")
    if not thesis.get("pivotal_points"):
        warnings.append("thesis.pivotal_points is empty — Agent 2 can't anchor model to thesis")

    # Modeling guidance is the critical handoff
    guidance = data.get("modeling_guidance", {})
    if not guidance.get("revenue_approach"):
        warnings.append("modeling_guidance.revenue_approach missing — Agent 2 won't know how to build revenue")
    if not guidance.get("key_drivers"):
        warnings.append("modeling_guidance.key_drivers is empty — Agent 2 has no assumptions to model")

    # Revenue approach must match available data
    approach = guidance.get("revenue_approach")
    segments = data.get("business", {}).get("segments", [])
    segments_with_revenue = [s for s in segments if s.get("revenue_latest_m")]

    if approach == "bottom_up" and len(segments_with_revenue) < 2:
        warnings.append(
            f"revenue_approach is 'bottom_up' but only {len(segments_with_revenue)} segment(s) "
            "have revenue data — Agent 2 can't build bottom-up model. Consider 'top_down' or 'hybrid'."
        )

    if approach == "top_down":
        tam = data.get("industry", {}).get("tam", {})
        if not tam.get("size_b"):
            warnings.append(
                "revenue_approach is 'top_down' but industry.tam.size_b is missing — "
                "Agent 2 can't build top-down model."
            )

    # Historical financials
    historical = data.get("financials", {}).get("historical", {})
    income = historical.get("income_statement", [])
    if len(income) < 2:
        warnings.append(
            f"Only {len(income)} year(s) of historical income statement — "
            "Agent 2 needs 3+ years to establish trends"
        )

    # Sources
    sources = data.get("sources", [])
    if len(sources) < 3:
        warnings.append(f"Only {len(sources)} source(s) cited — research may be thin")

    return warnings


def _validate_model_completeness(data: dict) -> list[str]:
    """
    Check that model_state.json is internally consistent before passing to Agent 3.
    """
    warnings = []

    # Consistency checks must exist and be populated
    checks = data.get("consistency_checks", {})
    if not checks:
        warnings.append("consistency_checks section is empty — model has no quality gate")
        return warnings

    if checks.get("all_checks_passed") is False:
        flags = checks.get("unresolved_flags", [])
        if flags:
            warnings.append(
                f"Model has {len(flags)} unresolved consistency flag(s): "
                + "; ".join(flags[:3])
            )

    # Terminal value sanity
    tv_sanity = checks.get("terminal_value_sanity", {})
    tv_pct = tv_sanity.get("terminal_pct_of_ev")
    if tv_pct is not None and tv_pct > 85:
        warnings.append(
            f"Terminal value is {tv_pct:.0f}% of EV — model is extremely sensitive "
            "to terminal assumptions. Consider extending forecast period."
        )

    # Valuation must exist
    valuation = data.get("valuation", {})
    synthesis = valuation.get("synthesis", {})
    if not synthesis.get("fair_value_per_share"):
        warnings.append("valuation.synthesis.fair_value_per_share is missing — no price target")

    # Scenarios must have probabilities summing to ~100
    scenarios = data.get("scenarios", {})
    bull_p = scenarios.get("bull", {}).get("probability_pct", 0)
    base_p = scenarios.get("base", {}).get("probability_pct", 0)
    bear_p = scenarios.get("bear", {}).get("probability_pct", 0)
    total_p = bull_p + base_p + bear_p
    if total_p > 0 and abs(total_p - 100) > 5:
        warnings.append(
            f"Scenario probabilities sum to {total_p}% (should be ~100%)"
        )

    return warnings


def _run_validation(
    filename: str,
    schema_name: str,
    stage_label: str,
    completeness_fn: callable | None = None,
) -> dict:
    """
    Run schema + completeness validation. Logs results and raises on hard failures.

    Returns the parsed data if validation passes.
    Raises ValidationError for structural failures (bad JSON, missing required fields).
    Logs warnings for content quality issues but does NOT raise.
    """
    logger.info("Validating %s...", filename)

    data, schema_errors = _validate_state_file(filename, schema_name, stage_label)

    if schema_errors:
        logger.error(
            "VALIDATION FAILED — %s has %d schema error(s):",
            filename, len(schema_errors),
        )
        for err in schema_errors[:10]:  # cap at 10 to avoid log spam
            logger.error("  %s", err)
        if len(schema_errors) > 10:
            logger.error("  ... and %d more", len(schema_errors) - 10)
        raise ValidationError(stage_label, schema_errors)

    # Content quality checks (warnings, not failures)
    if completeness_fn:
        warnings = completeness_fn(data)
        if warnings:
            logger.warning(
                "%s passed schema validation but has %d quality warning(s):",
                filename, len(warnings),
            )
            for w in warnings:
                logger.warning("  ⚠ %s", w)
        else:
            logger.info("%s passed all validation checks", filename)
    else:
        logger.info("%s passed schema validation", filename)

    return data


# ──────────────────────────────────────────────────────
# Logging Helpers
# ──────────────────────────────────────────────────────

def _log_result(name: str, result: AgentResult) -> None:
    """Log agent completion stats."""
    logger.info(
        "━━━ %s complete ━━━\n"
        "  Iterations:    %d\n"
        "  Tool calls:    %d\n"
        "  Input tokens:  %s\n"
        "  Output tokens: %s\n"
        "  Duration:      %.1fs\n"
        "  Stopped:       %s",
        name,
        result.iterations,
        result.tool_calls,
        f"{result.input_tokens:,}",
        f"{result.output_tokens:,}",
        result.duration_seconds,
        result.stopped_reason,
    )


def _on_tool_call(agent_name: str):
    """Create a tool call callback for logging."""
    def callback(tool_name: str, tool_input: dict):
        input_summary = str(tool_input)[:200]
        logger.info("[%s] Calling %s: %s", agent_name, tool_name, input_summary)
    return callback


# ──────────────────────────────────────────────────────
# Pipeline
# ──────────────────────────────────────────────────────

def run_pipeline(
    ticker: str,
    company_name: str | None = None,
    model: str = "claude-opus-4-20250514",
    skip_research: bool = False,
    skip_model: bool = False,
) -> dict:
    """
    Run the full 3-agent pipeline.

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL")
        company_name: Optional full company name
        model: Claude model to use for all agents
        skip_research: Skip Agent 1 (use existing research_state.json)
        skip_model: Skip Agent 2 (use existing model_state.json)

    Returns:
        dict with results from each agent stage
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pipeline_start = time.time()
    results = {}

    ticker_upper = ticker.upper()

    # ──────────────────────────────────────────────
    # Agent 1: Research
    # ──────────────────────────────────────────────
    if not skip_research:
        logger.info("=" * 60)
        logger.info("AGENT 1: RESEARCH — %s", ticker_upper)
        logger.info("=" * 60)

        config = AgentConfig(
            name="Research Agent",
            system_prompt=agent1_research.SYSTEM_PROMPT,
            tools=AGENT1_TOOLS,
            model=model,
            max_iterations=50,
        )
        user_msg = agent1_research.build_user_prompt(ticker_upper, company_name)

        result = run_agent(
            config,
            user_msg,
            on_tool_call=_on_tool_call("Research"),
        )
        _log_result("Agent 1 (Research)", result)
        results["research"] = {
            "iterations": result.iterations,
            "tool_calls": result.tool_calls,
            "tokens": result.input_tokens + result.output_tokens,
            "duration_s": result.duration_seconds,
            "stopped": result.stopped_reason,
        }
    else:
        logger.info("Skipping Agent 1 (--skip-research). Using existing research_state.json.")

    # ── Validate research_state.json before Agent 2 ──
    try:
        _run_validation(
            "research_state.json",
            "research_state.json",
            "Research → Model handoff",
            completeness_fn=_validate_research_completeness,
        )
    except ValidationError as e:
        logger.error(
            "Cannot proceed to Agent 2: %s\n"
            "Fix research_state.json or re-run Agent 1.",
            e,
        )
        results["validation_failure"] = {
            "stage": e.stage,
            "errors": e.errors,
        }
        return results

    # ──────────────────────────────────────────────
    # Agent 2: Model + Valuation
    # ──────────────────────────────────────────────
    if not skip_model:
        logger.info("=" * 60)
        logger.info("AGENT 2: MODEL + VALUATION — %s", ticker_upper)
        logger.info("=" * 60)

        config = AgentConfig(
            name="Model Agent",
            system_prompt=agent2_model.SYSTEM_PROMPT,
            tools=AGENT2_TOOLS,
            model=model,
            max_iterations=30,
        )
        user_msg = agent2_model.build_user_prompt(ticker_upper)

        result = run_agent(
            config,
            user_msg,
            on_tool_call=_on_tool_call("Model"),
        )
        _log_result("Agent 2 (Model)", result)
        results["model"] = {
            "iterations": result.iterations,
            "tool_calls": result.tool_calls,
            "tokens": result.input_tokens + result.output_tokens,
            "duration_s": result.duration_seconds,
            "stopped": result.stopped_reason,
        }
    else:
        logger.info("Skipping Agent 2 (--skip-model). Using existing model_state.json.")

    # ── Validate model_state.json before Agent 3 ──
    try:
        _run_validation(
            "model_state.json",
            "model_state.json",
            "Model → Writer handoff",
            completeness_fn=_validate_model_completeness,
        )
    except ValidationError as e:
        logger.error(
            "Cannot proceed to Agent 3: %s\n"
            "Fix model_state.json or re-run Agent 2.",
            e,
        )
        results["validation_failure"] = {
            "stage": e.stage,
            "errors": e.errors,
        }
        return results

    # ──────────────────────────────────────────────
    # Agent 3: Writer + Producer
    # ──────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("AGENT 3: WRITER + PRODUCER — %s", ticker_upper)
    logger.info("=" * 60)

    config = AgentConfig(
        name="Writer Agent",
        system_prompt=agent3_writer.SYSTEM_PROMPT,
        tools=AGENT3_TOOLS,
        model=model,
        max_iterations=15,
    )
    user_msg = agent3_writer.build_user_prompt(ticker_upper)

    result = run_agent(
        config,
        user_msg,
        on_tool_call=_on_tool_call("Writer"),
    )
    _log_result("Agent 3 (Writer)", result)
    results["writer"] = {
        "iterations": result.iterations,
        "tool_calls": result.tool_calls,
        "tokens": result.input_tokens + result.output_tokens,
        "duration_s": result.duration_seconds,
        "stopped": result.stopped_reason,
    }

    # ──────────────────────────────────────────────
    # Pipeline Summary
    # ──────────────────────────────────────────────
    pipeline_duration = time.time() - pipeline_start
    total_tokens = sum(r.get("tokens", 0) for r in results.values() if isinstance(r, dict) and "tokens" in r)
    total_tool_calls = sum(r.get("tool_calls", 0) for r in results.values() if isinstance(r, dict) and "tool_calls" in r)

    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE — %s", ticker_upper)
    logger.info("=" * 60)
    logger.info("  Total duration: %.1fs", pipeline_duration)
    logger.info("  Total tokens:   %s", f"{total_tokens:,}")
    logger.info("  Total tools:    %d", total_tool_calls)

    # List outputs
    outputs = []
    for f in OUTPUT_DIR.iterdir():
        if f.name != ".gitkeep":
            outputs.append(f.name)
    logger.info("  Outputs:        %s", ", ".join(sorted(outputs)))

    # Save pipeline metadata
    results["pipeline"] = {
        "ticker": ticker_upper,
        "duration_s": pipeline_duration,
        "total_tokens": total_tokens,
        "total_tool_calls": total_tool_calls,
        "outputs": sorted(outputs),
    }
    meta_path = OUTPUT_DIR / "pipeline_meta.json"
    meta_path.write_text(json.dumps(results, indent=2))

    return results


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Equity Research Agent Pipeline — 3 agents, sequential execution",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python -m agents.coordinator AAPL
  python -m agents.coordinator MSFT --name "Microsoft Corporation"
  python -m agents.coordinator AAPL --skip-research  # reuse existing research
  python -m agents.coordinator AAPL --skip-model      # reuse existing model
""",
    )
    parser.add_argument("ticker", help="Stock ticker symbol (e.g., AAPL)")
    parser.add_argument("--name", dest="company_name", help="Full company name")
    parser.add_argument(
        "--model",
        default="claude-opus-4-20250514",
        help="Claude model to use (default: claude-opus-4-20250514)",
    )
    parser.add_argument(
        "--skip-research",
        action="store_true",
        help="Skip Agent 1, use existing research_state.json",
    )
    parser.add_argument(
        "--skip-model",
        action="store_true",
        help="Skip Agent 2, use existing model_state.json",
    )

    args = parser.parse_args()

    results = run_pipeline(
        ticker=args.ticker,
        company_name=args.company_name,
        model=args.model,
        skip_research=args.skip_research,
        skip_model=args.skip_model,
    )

    # Exit with error if pipeline failed validation or produced no outputs
    if results.get("validation_failure"):
        sys.exit(2)
    if not results.get("pipeline", {}).get("outputs"):
        sys.exit(1)


if __name__ == "__main__":
    main()
