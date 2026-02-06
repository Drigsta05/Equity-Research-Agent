"""Tests for tool implementations — no API key required."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


class TestCalculator:
    """Test the calculator tool."""

    def test_basic_arithmetic(self):
        from tools.calculator import execute_calculator

        result = json.loads(execute_calculator([
            {"label": "add", "expression": "2 + 3"},
            {"label": "multiply", "expression": "100 * 1.15"},
            {"label": "power", "expression": "1.1 ** 5"},
        ]))

        calcs = result["calculations"]
        assert calcs[0]["result"] == 5.0
        assert calcs[1]["result"] == pytest.approx(115.0)
        assert calcs[2]["result"] == pytest.approx(1.61051, rel=1e-3)

    def test_financial_calculations(self):
        from tools.calculator import execute_calculator

        result = json.loads(execute_calculator([
            {"label": "WACC", "expression": "0.7 * 0.10 + 0.3 * 0.05 * (1 - 0.21)"},
            {"label": "PV", "expression": "100 / (1.08 ** 3)"},
            {"label": "Growth", "expression": "(150 / 100) ** (1/3) - 1"},
        ]))

        calcs = result["calculations"]
        assert calcs[0]["result"] == pytest.approx(0.0819, rel=1e-3)
        assert calcs[1]["result"] == pytest.approx(79.383, rel=1e-2)
        assert calcs[2]["result"] == pytest.approx(0.1447, rel=1e-2)

    def test_blocked_expressions(self):
        from tools.calculator import execute_calculator

        result = json.loads(execute_calculator([
            {"label": "blocked", "expression": "import os"},
        ]))
        assert "error" in result["calculations"][0]

    def test_division_by_zero(self):
        from tools.calculator import execute_calculator

        result = json.loads(execute_calculator([
            {"label": "div_zero", "expression": "1 / 0"},
        ]))
        assert "error" in result["calculations"][0]


class TestFinancialCalculator:
    """Test the financial calculator tool."""

    def test_npv(self):
        from tools.financial_calculator import execute_financial_calculator

        result = json.loads(execute_financial_calculator("npv", {
            "discount_rate": 0.10,
            "cash_flows": [100, 100, 100],
        }))

        r = result["result"]
        assert r["npv"] == pytest.approx(248.69, rel=1e-2)
        assert len(r["detail"]) == 3
        assert r["detail"][0]["year"] == 1

    def test_pv_series_with_terminal(self):
        from tools.financial_calculator import execute_financial_calculator

        result = json.loads(execute_financial_calculator("pv_series", {
            "discount_rate": 0.09,
            "cash_flows": [100, 110, 120],
            "terminal_value": 2000,
        }))

        r = result["result"]
        # Last year should include TV: 120 + 2000 = 2120
        assert r["detail"][-1]["cash_flow"] == pytest.approx(2120.0)
        assert r["total_pv"] > 0

    def test_irr(self):
        from tools.financial_calculator import execute_financial_calculator

        # -1000 now, 400 per year for 3 years → IRR ~10%
        result = json.loads(execute_financial_calculator("irr", {
            "cash_flows": [-1000, 400, 400, 400],
        }))

        r = result["result"]
        assert r["converged"] is True
        assert r["irr_pct"] == pytest.approx(9.70, rel=0.05)

    def test_wacc(self):
        from tools.financial_calculator import execute_financial_calculator

        result = json.loads(execute_financial_calculator("wacc", {
            "risk_free_rate": 0.04,
            "beta": 1.1,
            "equity_risk_premium": 0.055,
            "pre_tax_cost_of_debt": 0.05,
            "tax_rate": 0.21,
            "debt_to_total_capital": 0.30,
        }))

        r = result["result"]
        # Ke = 4% + 1.1*5.5% = 10.05%
        assert r["cost_of_equity_pct"] == pytest.approx(10.05, rel=1e-2)
        # WACC = 0.7*10.05% + 0.3*5%*(1-21%) = 7.035% + 1.185% ≈ 8.22%
        assert r["wacc_pct"] == pytest.approx(8.22, rel=0.02)

    def test_cagr(self):
        from tools.financial_calculator import execute_financial_calculator

        result = json.loads(execute_financial_calculator("cagr", {
            "begin_value": 1000,
            "end_value": 1500,
            "years": 3,
        }))

        r = result["result"]
        assert r["cagr_pct"] == pytest.approx(14.47, rel=0.02)

    def test_terminal_value_perpetuity(self):
        from tools.financial_calculator import execute_financial_calculator

        result = json.loads(execute_financial_calculator("terminal_value", {
            "method": "perpetuity_growth",
            "final_year_fcf": 500,
            "growth_rate": 0.025,
            "discount_rate": 0.09,
            "years_out": 5,
        }))

        r = result["result"]
        pg = r["perpetuity_growth"]
        # TV = 500*(1.025)/(0.09-0.025) = 512.5/0.065 ≈ 7884.6
        assert pg["terminal_value"] == pytest.approx(7884.6, rel=1e-2)
        assert pg["pv_terminal_value"] > 0

    def test_terminal_value_both_methods(self):
        from tools.financial_calculator import execute_financial_calculator

        result = json.loads(execute_financial_calculator("terminal_value", {
            "method": "both",
            "final_year_fcf": 500,
            "growth_rate": 0.025,
            "discount_rate": 0.09,
            "final_year_ebitda": 800,
            "exit_multiple": 10,
            "years_out": 5,
        }))

        r = result["result"]
        assert "perpetuity_growth" in r
        assert "exit_multiple" in r
        assert r["exit_multiple"]["terminal_value"] == pytest.approx(8000.0)

    def test_sensitivity_table(self):
        from tools.financial_calculator import execute_financial_calculator

        result = json.loads(execute_financial_calculator("sensitivity_table", {
            "terminal_year_fcf": 500,
            "explicit_period_pv": 1500,
            "net_debt": 200,
            "shares_outstanding": 100,
            "years_to_terminal": 5,
            "wacc_range": [0.08, 0.09, 0.10],
            "growth_range": [0.02, 0.025, 0.03],
        }))

        r = result["result"]
        assert len(r["matrix"]) == 3  # 3 WACC values
        assert len(r["matrix"][0]) == 3  # 3 growth values
        # Higher WACC → lower value
        assert r["matrix"][0][1] > r["matrix"][2][1]
        # Higher growth → higher value
        assert r["matrix"][1][2] > r["matrix"][1][0]

    def test_ev_to_equity(self):
        from tools.financial_calculator import execute_financial_calculator

        result = json.loads(execute_financial_calculator("ev_to_equity", {
            "enterprise_value": 10000,
            "net_debt": 2000,
            "shares_outstanding": 500,
        }))

        r = result["result"]
        assert r["equity_value"] == 8000
        assert r["equity_value_per_share"] == 16.0

    def test_invalid_operation(self):
        from tools.financial_calculator import execute_financial_calculator

        result = json.loads(execute_financial_calculator("invalid_op", {}))
        assert "error" in result

    def test_missing_params(self):
        from tools.financial_calculator import execute_financial_calculator

        result = json.loads(execute_financial_calculator("npv", {}))
        assert "error" in result


class TestFileIO:
    """Test file I/O tools."""

    def test_write_and_read_json(self, tmp_path):
        from tools.file_io import execute_file_write, execute_file_read

        # Patch OUTPUT_DIR
        with patch("tools.file_io.OUTPUT_DIR", tmp_path):
            # Write
            data = {"test": "value", "number": 42}
            write_result = json.loads(execute_file_write(
                "test.json", json.dumps(data),
            ))
            assert write_result["success"] is True

            # Read
            read_result = json.loads(execute_file_read("test.json"))
            assert read_result["content"]["test"] == "value"
            assert read_result["content"]["number"] == 42

    def test_write_invalid_json(self, tmp_path):
        from tools.file_io import execute_file_write

        with patch("tools.file_io.OUTPUT_DIR", tmp_path):
            result = json.loads(execute_file_write("test.json", "not json{"))
            assert "error" in result

    def test_read_nonexistent(self, tmp_path):
        from tools.file_io import execute_file_read

        with patch("tools.file_io.OUTPUT_DIR", tmp_path):
            result = json.loads(execute_file_read("nonexistent.json"))
            assert "error" in result


class TestChartBuilder:
    """Test chart creation."""

    def test_create_bar_chart(self, tmp_path):
        from tools.chart_builder import execute_create_chart

        with patch("tools.chart_builder.OUTPUT_DIR", tmp_path):
            result = json.loads(execute_create_chart(
                filename="test_bar.png",
                chart_type="bar",
                title="Revenue by Year",
                categories=["FY2022", "FY2023", "FY2024"],
                series=[{"name": "Revenue", "values": [1000, 1150, 1300]}],
                y_format="currency",
                show_values=True,
            ))
            assert result["success"] is True
            assert (tmp_path / "test_bar.png").exists()

    def test_create_grouped_bar_chart(self, tmp_path):
        from tools.chart_builder import execute_create_chart

        with patch("tools.chart_builder.OUTPUT_DIR", tmp_path):
            result = json.loads(execute_create_chart(
                filename="test_grouped.png",
                chart_type="grouped_bar",
                title="Peer Comparison",
                categories=["AAPL", "MSFT", "GOOGL"],
                series=[
                    {"name": "EV/EBITDA", "values": [22, 25, 18]},
                    {"name": "P/E", "values": [28, 32, 24]},
                ],
            ))
            assert result["success"] is True
            assert result["chart_type"] == "grouped_bar"

    def test_create_line_chart(self, tmp_path):
        from tools.chart_builder import execute_create_chart

        with patch("tools.chart_builder.OUTPUT_DIR", tmp_path):
            result = json.loads(execute_create_chart(
                filename="test_line.png",
                chart_type="line",
                title="Margin Trajectory",
                categories=["FY2022", "FY2023", "FY2024", "FY2025E"],
                series=[
                    {"name": "Gross Margin", "values": [43.3, 44.1, 46.2, 47.0]},
                    {"name": "EBITDA Margin", "values": [33.5, 34.1, 35.8, 36.5]},
                ],
                y_format="percent",
            ))
            assert result["success"] is True
            assert (tmp_path / "test_line.png").exists()

    def test_create_waterfall_chart(self, tmp_path):
        from tools.chart_builder import execute_create_chart

        with patch("tools.chart_builder.OUTPUT_DIR", tmp_path):
            result = json.loads(execute_create_chart(
                filename="test_waterfall.png",
                chart_type="waterfall",
                title="FCF Bridge",
                categories=["EBITDA", "Tax", "Capex", "WC", "UFCF"],
                series=[{"name": "Bridge", "values": [350, -74, -80, -15, 0]}],
                y_format="currency",
            ))
            assert result["success"] is True

    def test_invalid_chart_type(self, tmp_path):
        from tools.chart_builder import execute_create_chart

        with patch("tools.chart_builder.OUTPUT_DIR", tmp_path):
            result = json.loads(execute_create_chart(
                filename="test_bad.png",
                chart_type="pie",
                title="Bad Chart",
                categories=["A", "B"],
                series=[{"name": "x", "values": [1, 2]}],
            ))
            assert "error" in result


class TestDocxBuilder:
    """Test DOCX creation."""

    def test_create_basic_docx(self, tmp_path):
        from tools.docx_builder import execute_create_docx

        with patch("tools.docx_builder.OUTPUT_DIR", tmp_path):
            result = json.loads(execute_create_docx(
                filename="test_report.docx",
                title="Test Report",
                subtitle="Test Subtitle",
                sections=[
                    {
                        "heading": "Section 1",
                        "body": "This is the body text.\n\nSecond paragraph.",
                    },
                    {
                        "heading": "Section 2",
                        "body": "• Bullet point 1\n• Bullet point 2",
                    },
                ],
            ))
            assert result["success"] is True
            assert (tmp_path / "test_report.docx").exists()

    def test_docx_with_embedded_chart(self, tmp_path):
        from tools.chart_builder import execute_create_chart
        from tools.docx_builder import execute_create_docx

        # First create a chart
        with patch("tools.chart_builder.OUTPUT_DIR", tmp_path):
            json.loads(execute_create_chart(
                filename="embed_test.png",
                chart_type="bar",
                title="Test",
                categories=["A", "B"],
                series=[{"name": "x", "values": [1, 2]}],
            ))

        # Then create a docx that embeds it
        with patch("tools.docx_builder.OUTPUT_DIR", tmp_path):
            result = json.loads(execute_create_docx(
                filename="test_with_chart.docx",
                title="Chart Embed Test",
                sections=[
                    {
                        "heading": "Section with Chart",
                        "body": "See the chart below.",
                        "charts": ["embed_test.png"],
                    },
                ],
            ))
            assert result["success"] is True
            assert (tmp_path / "test_with_chart.docx").exists()


class TestXlsxBuilder:
    """Test XLSX creation."""

    def test_create_basic_xlsx(self, tmp_path):
        from tools.xlsx_builder import execute_create_xlsx

        with patch("tools.xlsx_builder.OUTPUT_DIR", tmp_path):
            result = json.loads(execute_create_xlsx(
                filename="test_model.xlsx",
                sheets=[
                    {
                        "name": "Summary",
                        "headers": ["Metric", "FY2023", "FY2024", "FY2025E"],
                        "rows": [
                            ["Revenue ($M)", 1000, 1150, 1300],
                            ["EBITDA ($M)", 300, 350, 420],
                            ["EBITDA Margin", 0.30, 0.304, 0.323],
                        ],
                    },
                    {
                        "name": "DCF",
                        "headers": ["Year", "UFCF", "Discount Factor", "PV"],
                        "rows": [
                            ["FY2025E", 200, "=1/(1.09^1)", "=B2*C2"],
                            ["FY2026E", 230, "=1/(1.09^2)", "=B3*C3"],
                        ],
                        "formulas": [
                            {"cell": "B5", "formula": "=SUM(B2:B3)"},
                        ],
                    },
                ],
            ))
            assert result["success"] is True
            assert "Summary" in result["sheets"]
            assert "DCF" in result["sheets"]
            assert (tmp_path / "test_model.xlsx").exists()


class TestSchemaValidation:
    """Test the coordinator's schema validation logic."""

    def test_valid_research_state(self, tmp_path):
        from agents.coordinator import _validate_state_file

        # Minimal valid research_state
        data = {
            "company": {
                "ticker": "AAPL", "name": "Apple Inc.", "sector": "Technology",
                "market_cap_b": 3000, "price": 195, "shares_outstanding_m": 15400,
                "currency": "USD", "exchange": "NASDAQ",
            },
            "thesis": {
                "one_line": "test thesis",
                "variant_perception": "test variant",
                "pivotal_points": ["point 1"],
            },
            "business": {
                "description": "Makes phones",
                "segments": [{"name": "iPhone", "description": "smartphones"}],
                "revenue_model": "hardware + services",
            },
            "industry": {"competitive_dynamics": "oligopoly"},
            "financials": {"historical": {}},
            "modeling_guidance": {
                "revenue_approach": "bottom_up",
                "key_drivers": [{"driver": "units", "base_case": 230, "rationale": "test"}],
            },
            "sources": [{"document": "10-K", "key_data_extracted": "revenue"}],
            "meta": {
                "research_completed_at": "2025-01-01T00:00:00Z",
                "coverage_assessment": {},
            },
        }

        state_file = tmp_path / "research_state.json"
        state_file.write_text(json.dumps(data))

        with patch("agents.coordinator.OUTPUT_DIR", tmp_path):
            parsed, errors = _validate_state_file(
                "research_state.json", "research_state.json", "test",
            )
            assert errors == []
            assert parsed["company"]["ticker"] == "AAPL"

    def test_missing_required_fields(self, tmp_path):
        from agents.coordinator import _validate_state_file

        # Missing thesis, business, etc.
        data = {"company": {"ticker": "AAPL"}}

        state_file = tmp_path / "research_state.json"
        state_file.write_text(json.dumps(data))

        with patch("agents.coordinator.OUTPUT_DIR", tmp_path):
            parsed, errors = _validate_state_file(
                "research_state.json", "research_state.json", "test",
            )
            assert len(errors) > 0

    def test_research_completeness_bottom_up_no_segments(self):
        from agents.coordinator import _validate_research_completeness

        data = {
            "thesis": {"one_line": "test", "pivotal_points": ["p1"]},
            "modeling_guidance": {
                "revenue_approach": "bottom_up",
                "key_drivers": [{"driver": "x", "base_case": 1, "rationale": "y"}],
            },
            "business": {"segments": [{"name": "only_one", "description": "no revenue data"}]},
            "financials": {"historical": {"income_statement": [{}, {}]}},
            "sources": [{}, {}, {}],
        }

        warnings = _validate_research_completeness(data)
        # Should warn about bottom_up with insufficient segment data
        assert any("bottom_up" in w for w in warnings)

    def test_model_completeness_bad_probabilities(self):
        from agents.coordinator import _validate_model_completeness

        data = {
            "consistency_checks": {"all_checks_passed": True},
            "valuation": {"synthesis": {"fair_value_per_share": 150}},
            "scenarios": {
                "bull": {"probability_pct": 30},
                "base": {"probability_pct": 50},
                "bear": {"probability_pct": 10},  # sums to 90, not 100
            },
        }

        warnings = _validate_model_completeness(data)
        assert any("probabilities" in w.lower() for w in warnings)

    def test_nonexistent_file(self, tmp_path):
        from agents.coordinator import _validate_state_file

        with patch("agents.coordinator.OUTPUT_DIR", tmp_path):
            parsed, errors = _validate_state_file(
                "nonexistent.json", "research_state.json", "test",
            )
            assert len(errors) == 1
            assert "does not exist" in errors[0]
