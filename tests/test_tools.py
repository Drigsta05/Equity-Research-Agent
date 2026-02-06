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
                        "table": {
                            "headers": ["Metric", "Value"],
                            "rows": [["Revenue", "$1,000M"], ["EBITDA", "$300M"]],
                        },
                    },
                ],
            ))
            assert result["success"] is True
            assert (tmp_path / "test_report.docx").exists()


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
