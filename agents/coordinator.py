"""
Coordinator: Sequential Pipeline
---------------------------------
Agent 1 → wait → Agent 2 → wait → Agent 3.
No routing logic, no decision trees, no orchestrator intelligence.
The file schemas do the coordination.

This is ~50 lines of actual logic. The simplicity is intentional.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

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
        # Log tool name but not full input (can be large)
        input_summary = str(tool_input)[:200]
        logger.info("[%s] Calling %s: %s", agent_name, tool_name, input_summary)
    return callback


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
            max_iterations=50,  # Research may need many loops
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

        # Verify output exists
        if not (OUTPUT_DIR / "research_state.json").exists():
            logger.error("Agent 1 did not produce research_state.json!")
            return results
    else:
        logger.info("Skipping Agent 1 (--skip-research). Using existing research_state.json.")
        if not (OUTPUT_DIR / "research_state.json").exists():
            logger.error("No research_state.json found! Cannot skip research.")
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
            max_iterations=30,  # Modeling loops less than research
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

        # Verify output exists
        if not (OUTPUT_DIR / "model_state.json").exists():
            logger.error("Agent 2 did not produce model_state.json!")
            return results
    else:
        logger.info("Skipping Agent 2 (--skip-model). Using existing model_state.json.")
        if not (OUTPUT_DIR / "model_state.json").exists():
            logger.error("No model_state.json found! Cannot skip model.")
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
        max_iterations=15,  # Writer should be more focused
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
    total_tokens = sum(r.get("tokens", 0) for r in results.values())
    total_tool_calls = sum(r.get("tool_calls", 0) for r in results.values())

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

    # Exit with error if pipeline produced no outputs
    if not results.get("pipeline", {}).get("outputs"):
        sys.exit(1)


if __name__ == "__main__":
    main()
