"""
Financial calculator tool — specialized functions for DCF modeling.

Provides NPV, PV, IRR, WACC, CAGR, and terminal value calculations
that the basic calculator can't do cleanly with raw expressions.
Agents should use this for multi-step financial computations.
"""

from __future__ import annotations

import json
import logging
import math

logger = logging.getLogger(__name__)

FINANCIAL_CALCULATOR_TOOL = {
    "name": "financial_calculator",
    "description": (
        "Specialized financial calculator for DCF modeling. Provides NPV, PV of cash flow "
        "series, IRR, WACC, CAGR, terminal value, and sensitivity table generation. "
        "Use this instead of the basic calculator for multi-step financial computations "
        "like discounting a series of cash flows or building a sensitivity matrix."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": [
                    "npv",
                    "pv_series",
                    "irr",
                    "wacc",
                    "cagr",
                    "terminal_value",
                    "sensitivity_table",
                    "ev_to_equity",
                ],
                "description": "The financial calculation to perform.",
            },
            "params": {
                "type": "object",
                "description": "Parameters for the calculation. See operation-specific requirements.",
            },
        },
        "required": ["operation", "params"],
    },
}


def _npv(params: dict) -> dict:
    """
    Net Present Value of a series of cash flows.

    Params:
        discount_rate: float (e.g., 0.09 for 9%)
        cash_flows: list[float] — cash flows starting at year 1
            (year 0 NOT included; add it separately if needed)
    """
    rate = params["discount_rate"]
    flows = params["cash_flows"]

    pv_flows = []
    total = 0.0
    for i, cf in enumerate(flows, start=1):
        pv = cf / ((1 + rate) ** i)
        pv_flows.append({"year": i, "cash_flow": cf, "discount_factor": 1 / ((1 + rate) ** i), "pv": pv})
        total += pv

    return {
        "npv": total,
        "discount_rate": rate,
        "num_periods": len(flows),
        "detail": pv_flows,
    }


def _pv_series(params: dict) -> dict:
    """
    Present value of each cash flow in a series, with running total.
    More detailed than NPV — shows discount factor for each period.

    Params:
        discount_rate: float
        cash_flows: list[float] — year 1 through year N
        terminal_value: float (optional) — added to the last year's cash flow
    """
    rate = params["discount_rate"]
    flows = list(params["cash_flows"])
    tv = params.get("terminal_value", 0)

    if tv and flows:
        flows[-1] = flows[-1] + tv

    detail = []
    running_pv = 0.0
    for i, cf in enumerate(flows, start=1):
        df = 1 / ((1 + rate) ** i)
        pv = cf * df
        running_pv += pv
        detail.append({
            "year": i,
            "cash_flow": round(cf, 2),
            "discount_factor": round(df, 6),
            "pv": round(pv, 2),
            "cumulative_pv": round(running_pv, 2),
        })

    return {
        "total_pv": round(running_pv, 2),
        "discount_rate": rate,
        "terminal_value_included": tv,
        "detail": detail,
    }


def _irr(params: dict) -> dict:
    """
    Internal Rate of Return using Newton's method.

    Params:
        cash_flows: list[float] — starting at year 0 (must include initial investment as negative)
    """
    flows = params["cash_flows"]

    if not flows or len(flows) < 2:
        return {"error": "Need at least 2 cash flows (year 0 investment + year 1+ returns)"}

    # Newton-Raphson
    rate = 0.10  # initial guess
    for _ in range(200):
        npv_val = sum(cf / (1 + rate) ** i for i, cf in enumerate(flows))
        dnpv = sum(-i * cf / (1 + rate) ** (i + 1) for i, cf in enumerate(flows))

        if abs(dnpv) < 1e-12:
            break

        rate_new = rate - npv_val / dnpv

        if abs(rate_new - rate) < 1e-9:
            rate = rate_new
            break
        rate = rate_new

    # Verify
    npv_check = sum(cf / (1 + rate) ** i for i, cf in enumerate(flows))

    return {
        "irr": round(rate, 6),
        "irr_pct": round(rate * 100, 2),
        "npv_at_irr": round(npv_check, 2),
        "converged": abs(npv_check) < 0.01,
    }


def _wacc(params: dict) -> dict:
    """
    Weighted Average Cost of Capital.

    Params:
        risk_free_rate: float (e.g., 0.04 for 4%)
        beta: float
        equity_risk_premium: float (e.g., 0.055 for 5.5%)
        size_premium: float (optional, default 0)
        company_premium: float (optional, default 0)
        pre_tax_cost_of_debt: float
        tax_rate: float (e.g., 0.21 for 21%)
        debt_to_total_capital: float (e.g., 0.30 for 30%)
    """
    rf = params["risk_free_rate"]
    beta = params["beta"]
    erp = params["equity_risk_premium"]
    sp = params.get("size_premium", 0)
    cp = params.get("company_premium", 0)
    kd_pre = params["pre_tax_cost_of_debt"]
    tax = params["tax_rate"]
    debt_pct = params["debt_to_total_capital"]
    equity_pct = 1 - debt_pct

    ke = rf + beta * erp + sp + cp
    kd_post = kd_pre * (1 - tax)
    wacc_val = equity_pct * ke + debt_pct * kd_post

    return {
        "cost_of_equity_pct": round(ke * 100, 2),
        "after_tax_cost_of_debt_pct": round(kd_post * 100, 2),
        "equity_weight_pct": round(equity_pct * 100, 2),
        "debt_weight_pct": round(debt_pct * 100, 2),
        "wacc_pct": round(wacc_val * 100, 2),
        "wacc": round(wacc_val, 6),
        "components": {
            "risk_free_rate": rf,
            "beta": beta,
            "equity_risk_premium": erp,
            "size_premium": sp,
            "company_premium": cp,
            "pre_tax_cost_of_debt": kd_pre,
            "tax_rate": tax,
        },
    }


def _cagr(params: dict) -> dict:
    """
    Compound Annual Growth Rate.

    Params:
        begin_value: float
        end_value: float
        years: int
    """
    bv = params["begin_value"]
    ev = params["end_value"]
    n = params["years"]

    if bv <= 0:
        return {"error": "begin_value must be positive"}
    if n <= 0:
        return {"error": "years must be positive"}

    cagr_val = (ev / bv) ** (1 / n) - 1

    return {
        "cagr": round(cagr_val, 6),
        "cagr_pct": round(cagr_val * 100, 2),
        "begin_value": bv,
        "end_value": ev,
        "years": n,
    }


def _terminal_value(params: dict) -> dict:
    """
    Terminal value via perpetuity growth and/or exit multiple.

    Params:
        method: "perpetuity_growth" | "exit_multiple" | "both"
        # For perpetuity growth:
        final_year_fcf: float
        growth_rate: float (e.g., 0.025 for 2.5%)
        discount_rate: float (WACC)
        # For exit multiple:
        final_year_ebitda: float (optional)
        exit_multiple: float (optional)
        # Common:
        years_out: int — how many years in the future (for PV calculation)
    """
    method = params.get("method", "perpetuity_growth")
    years = params.get("years_out", 5)
    rate = params.get("discount_rate", 0.09)
    result = {}

    if method in ("perpetuity_growth", "both"):
        fcf = params["final_year_fcf"]
        g = params["growth_rate"]

        if rate <= g:
            return {"error": f"discount_rate ({rate}) must be > growth_rate ({g})"}

        tv_perp = fcf * (1 + g) / (rate - g)
        pv_tv_perp = tv_perp / ((1 + rate) ** years)

        # Implied exit multiple (TV / final year EBITDA)
        ebitda = params.get("final_year_ebitda")
        implied_multiple = tv_perp / ebitda if ebitda and ebitda > 0 else None

        result["perpetuity_growth"] = {
            "terminal_value": round(tv_perp, 2),
            "pv_terminal_value": round(pv_tv_perp, 2),
            "growth_rate": g,
            "implied_exit_multiple": round(implied_multiple, 1) if implied_multiple else None,
        }

    if method in ("exit_multiple", "both"):
        ebitda = params.get("final_year_ebitda")
        multiple = params.get("exit_multiple")

        if not ebitda or not multiple:
            if method == "exit_multiple":
                return {"error": "exit_multiple method requires final_year_ebitda and exit_multiple"}
        else:
            tv_exit = ebitda * multiple
            pv_tv_exit = tv_exit / ((1 + rate) ** years)

            # Implied perpetuity growth rate
            fcf = params.get("final_year_fcf")
            implied_g = None
            if fcf and fcf > 0:
                # TV = FCF*(1+g)/(r-g) → solve for g: g = (TV*r - FCF) / (TV + FCF)
                implied_g = (tv_exit * rate - fcf) / (tv_exit + fcf)

            result["exit_multiple"] = {
                "terminal_value": round(tv_exit, 2),
                "pv_terminal_value": round(pv_tv_exit, 2),
                "exit_ev_ebitda": multiple,
                "implied_growth_rate": round(implied_g, 4) if implied_g is not None else None,
            }

    result["years_out"] = years
    result["discount_rate"] = rate

    return result


def _sensitivity_table(params: dict) -> dict:
    """
    Build a WACC vs terminal growth sensitivity matrix for DCF per-share value.

    Params:
        base_ev: float — enterprise value at base WACC and growth
        base_wacc: float (e.g., 0.09)
        base_growth: float (e.g., 0.025)
        wacc_range: list[float] — WACC values to test (e.g., [0.07, 0.08, 0.09, 0.10, 0.11])
        growth_range: list[float] — growth values to test
        terminal_year_fcf: float — FCF in the terminal year
        explicit_period_pv: float — PV of the explicit forecast period
        net_debt: float — net debt to subtract from EV
        shares_outstanding: float — diluted shares
        years_to_terminal: int — years until terminal value
    """
    fcf = params["terminal_year_fcf"]
    explicit_pv = params["explicit_period_pv"]
    net_debt = params["net_debt"]
    shares = params["shares_outstanding"]
    years = params["years_to_terminal"]
    wacc_range = params["wacc_range"]
    growth_range = params["growth_range"]

    matrix = []
    for w in wacc_range:
        row = []
        for g in growth_range:
            if w <= g:
                row.append(None)  # invalid: WACC must exceed growth
            else:
                tv = fcf * (1 + g) / (w - g)
                pv_tv = tv / ((1 + w) ** years)
                ev = explicit_pv + pv_tv
                equity = ev - net_debt
                per_share = equity / shares if shares > 0 else 0
                row.append(round(per_share, 2))
        matrix.append(row)

    return {
        "wacc_range_pct": [round(w * 100, 1) for w in wacc_range],
        "growth_range_pct": [round(g * 100, 1) for g in growth_range],
        "matrix": matrix,
        "note": "Rows = WACC, Columns = terminal growth. Values = equity value per share. null = invalid (WACC <= growth).",
    }


def _ev_to_equity(params: dict) -> dict:
    """
    Bridge from Enterprise Value to Equity Value per Share.

    Params:
        enterprise_value: float
        net_debt: float (positive = company has net debt)
        minority_interest: float (optional, default 0)
        preferred_equity: float (optional, default 0)
        shares_outstanding: float (diluted)
    """
    ev = params["enterprise_value"]
    nd = params.get("net_debt", 0)
    mi = params.get("minority_interest", 0)
    pe = params.get("preferred_equity", 0)
    shares = params["shares_outstanding"]

    equity_value = ev - nd - mi - pe
    per_share = equity_value / shares if shares > 0 else 0

    return {
        "enterprise_value": round(ev, 2),
        "less_net_debt": round(nd, 2),
        "less_minority_interest": round(mi, 2),
        "less_preferred_equity": round(pe, 2),
        "equity_value": round(equity_value, 2),
        "shares_outstanding": shares,
        "equity_value_per_share": round(per_share, 2),
    }


_OPERATIONS = {
    "npv": _npv,
    "pv_series": _pv_series,
    "irr": _irr,
    "wacc": _wacc,
    "cagr": _cagr,
    "terminal_value": _terminal_value,
    "sensitivity_table": _sensitivity_table,
    "ev_to_equity": _ev_to_equity,
}


def execute_financial_calculator(operation: str, params: dict) -> str:
    """Execute a financial calculation."""
    fn = _OPERATIONS.get(operation)
    if fn is None:
        return json.dumps({"error": f"Unknown operation: {operation}. Available: {list(_OPERATIONS.keys())}"})

    try:
        result = fn(params)
        return json.dumps({"operation": operation, "result": result}, indent=2)
    except KeyError as e:
        return json.dumps({"error": f"Missing required parameter: {e}", "operation": operation})
    except (ZeroDivisionError, ValueError, OverflowError) as e:
        return json.dumps({"error": f"Calculation error: {str(e)}", "operation": operation})
    except Exception as e:
        logger.exception("Financial calculator failed")
        return json.dumps({"error": f"Unexpected error: {str(e)}", "operation": operation})
