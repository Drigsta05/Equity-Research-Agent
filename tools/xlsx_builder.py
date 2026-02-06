"""Excel model builder tool using openpyxl."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("output")

XLSX_TOOL = {
    "name": "create_xlsx",
    "description": (
        "Create a formatted Excel workbook with multiple sheets. Each sheet can contain "
        "headers, data rows, formulas, and formatting. Use this to build the financial "
        "model output with 9 sheets: Summary, Income Statement, Balance Sheet, Cash Flow, "
        "Revenue Build, DCF, Comps, ROIC, Scenarios."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Output filename, e.g., 'AAPL_model.xlsx'",
            },
            "sheets": {
                "type": "array",
                "description": "List of sheets to create in the workbook.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Sheet name (max 31 chars)",
                        },
                        "headers": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Column headers for the first row.",
                        },
                        "rows": {
                            "type": "array",
                            "description": "Data rows. Each row is an array of values.",
                            "items": {
                                "type": "array",
                                "items": {},
                            },
                        },
                        "column_widths": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "Optional column widths in characters.",
                        },
                        "formulas": {
                            "type": "array",
                            "description": "Optional Excel formulas to place in specific cells.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "cell": {
                                        "type": "string",
                                        "description": "Cell reference, e.g., 'C10'",
                                    },
                                    "formula": {
                                        "type": "string",
                                        "description": "Excel formula, e.g., '=B10*1.15'",
                                    },
                                },
                                "required": ["cell", "formula"],
                            },
                        },
                        "assumption_cells": {
                            "type": "array",
                            "description": "Cells containing assumptions (will be formatted in blue).",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["name"],
                },
            },
        },
        "required": ["filename", "sheets"],
    },
}


def execute_create_xlsx(filename: str, sheets: list[dict]) -> str:
    """Create a formatted Excel workbook."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, numbers
        from openpyxl.utils import get_column_letter

        wb = Workbook()

        # Style definitions
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="003366", end_color="003366", fill_type="solid")
        header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        assumption_font = Font(name="Calibri", size=11, color="0055CC")  # Blue for assumptions
        data_font = Font(name="Calibri", size=11, color="333333")
        number_font = Font(name="Calibri", size=11, color="333333")

        label_font = Font(name="Calibri", size=11, bold=True, color="333333")
        section_fill = PatternFill(start_color="E8F0FE", end_color="E8F0FE", fill_type="solid")

        thin_border = Border(
            left=Side(style="thin", color="CCCCCC"),
            right=Side(style="thin", color="CCCCCC"),
            top=Side(style="thin", color="CCCCCC"),
            bottom=Side(style="thin", color="CCCCCC"),
        )

        sheets_created = []

        for idx, sheet_def in enumerate(sheets):
            sheet_name = sheet_def.get("name", f"Sheet{idx + 1}")[:31]
            headers = sheet_def.get("headers", [])
            rows = sheet_def.get("rows", [])
            col_widths = sheet_def.get("column_widths", [])
            formulas = sheet_def.get("formulas", [])
            assumption_cells = set(sheet_def.get("assumption_cells", []))

            if idx == 0:
                ws = wb.active
                ws.title = sheet_name
            else:
                ws = wb.create_sheet(title=sheet_name)

            # Write headers
            if headers:
                for col_idx, header in enumerate(headers, start=1):
                    cell = ws.cell(row=1, column=col_idx, value=header)
                    cell.font = header_font
                    cell.fill = header_fill
                    cell.alignment = header_alignment
                    cell.border = thin_border

            # Write data rows
            start_row = 2 if headers else 1
            for row_idx, row_data in enumerate(rows, start=start_row):
                for col_idx, value in enumerate(row_data, start=1):
                    cell_ref = f"{get_column_letter(col_idx)}{row_idx}"
                    cell = ws.cell(row=row_idx, column=col_idx)

                    # Handle formula strings
                    if isinstance(value, str) and value.startswith("="):
                        cell.value = value
                    else:
                        cell.value = value

                    cell.border = thin_border

                    # Style: first column is labels (bold)
                    if col_idx == 1 and isinstance(value, str):
                        cell.font = label_font
                    elif cell_ref in assumption_cells:
                        cell.font = assumption_font
                    else:
                        cell.font = data_font

                    # Number formatting
                    if isinstance(value, (int, float)):
                        if abs(value) < 1 and value != 0:
                            cell.number_format = "0.0%"
                        elif abs(value) >= 1000:
                            cell.number_format = "#,##0"
                        elif abs(value) >= 1:
                            cell.number_format = "#,##0.0"

            # Apply explicit formulas
            for formula_def in formulas:
                cell_ref = formula_def.get("cell", "")
                formula = formula_def.get("formula", "")
                if cell_ref and formula:
                    ws[cell_ref] = formula
                    ws[cell_ref].border = thin_border
                    if cell_ref in assumption_cells:
                        ws[cell_ref].font = assumption_font
                    else:
                        ws[cell_ref].font = number_font

            # Column widths
            if col_widths:
                for col_idx, width in enumerate(col_widths, start=1):
                    ws.column_dimensions[get_column_letter(col_idx)].width = width
            else:
                # Auto-size: minimum 12, first column 30
                for col_idx in range(1, max(len(headers), max((len(r) for r in rows), default=0)) + 1):
                    width = 30 if col_idx == 1 else 14
                    ws.column_dimensions[get_column_letter(col_idx)].width = width

            # Freeze top row
            if headers:
                ws.freeze_panes = "A2"

            sheets_created.append(sheet_name)

        # Save
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        filepath = OUTPUT_DIR / filename
        wb.save(str(filepath))

        return json.dumps({
            "success": True,
            "filename": filename,
            "sheets": sheets_created,
            "path": str(filepath),
        })

    except ImportError:
        return json.dumps({
            "error": "openpyxl not installed. Run: pip install openpyxl"
        })
    except Exception as e:
        logger.exception("XLSX creation failed")
        return json.dumps({"error": f"XLSX creation failed: {str(e)}"})
