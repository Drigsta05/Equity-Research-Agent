"""Calculator tool for precise financial arithmetic."""

from __future__ import annotations

import json
import logging
import math

logger = logging.getLogger(__name__)

CALCULATOR_TOOL = {
    "name": "calculator",
    "description": (
        "Evaluate mathematical expressions with precision. Use this for ALL arithmetic "
        "in financial modeling — growth rates, margins, DCF calculations, WACC, ROIC, etc. "
        "Supports standard math operations, exponents (**), and common financial functions. "
        "You can pass multiple expressions at once to calculate in batch."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "expressions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {
                            "type": "string",
                            "description": "A descriptive label for the calculation, e.g., 'Revenue FY26E'",
                        },
                        "expression": {
                            "type": "string",
                            "description": (
                                "A Python math expression. Use standard operators (+, -, *, /, **, %). "
                                "Available functions: round(), abs(), min(), max(), sum(), "
                                "pow(), sqrt() (via math.sqrt). "
                                "Example: '1500 * 1.15 * 0.35' or '(120 / 1.08**3)'"
                            ),
                        },
                    },
                    "required": ["label", "expression"],
                },
                "description": "List of calculations to perform.",
            },
        },
        "required": ["expressions"],
    },
}

# Safe math namespace — no access to builtins, os, etc.
_SAFE_NAMES = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "pow": pow,
    "sqrt": math.sqrt,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "pi": math.pi,
    "e": math.e,
    "inf": float("inf"),
}


def _safe_eval(expression: str) -> float:
    """Evaluate a math expression safely."""
    # Block dangerous patterns
    blocked = ["import", "exec", "eval", "open", "os.", "sys.", "__", "lambda"]
    expr_lower = expression.lower()
    for pattern in blocked:
        if pattern in expr_lower:
            raise ValueError(f"Blocked expression pattern: {pattern}")

    return float(eval(expression, {"__builtins__": {}}, _SAFE_NAMES))


def execute_calculator(expressions: list[dict]) -> str:
    """Execute a batch of math expressions."""
    results = []

    for item in expressions:
        label = item.get("label", "unlabeled")
        expr = item.get("expression", "")

        try:
            value = _safe_eval(expr)

            # Format nicely
            if abs(value) >= 1e6:
                formatted = f"{value:,.0f}"
            elif abs(value) >= 1:
                formatted = f"{value:,.2f}"
            elif value == 0:
                formatted = "0"
            else:
                formatted = f"{value:.4f}"

            results.append({
                "label": label,
                "expression": expr,
                "result": value,
                "formatted": formatted,
            })

        except Exception as e:
            results.append({
                "label": label,
                "expression": expr,
                "error": str(e),
            })

    return json.dumps({"calculations": results}, indent=2)
