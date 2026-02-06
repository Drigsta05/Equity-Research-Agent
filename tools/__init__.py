"""Tool definitions for the equity research agent pipeline."""

from tools.web_search import WEB_SEARCH_TOOL, execute_web_search
from tools.web_fetch import WEB_FETCH_TOOL, execute_web_fetch
from tools.file_io import FILE_READ_TOOL, FILE_WRITE_TOOL, execute_file_read, execute_file_write
from tools.calculator import CALCULATOR_TOOL, execute_calculator
from tools.financial_calculator import FINANCIAL_CALCULATOR_TOOL, execute_financial_calculator
from tools.chart_builder import CHART_TOOL, execute_create_chart
from tools.docx_builder import DOCX_TOOL, execute_create_docx
from tools.xlsx_builder import XLSX_TOOL, execute_create_xlsx

# Tool registries per agent
AGENT1_TOOLS = [WEB_SEARCH_TOOL, WEB_FETCH_TOOL, FILE_READ_TOOL, FILE_WRITE_TOOL]
AGENT2_TOOLS = [FILE_READ_TOOL, FILE_WRITE_TOOL, CALCULATOR_TOOL, FINANCIAL_CALCULATOR_TOOL]
AGENT3_TOOLS = [FILE_READ_TOOL, FILE_WRITE_TOOL, CHART_TOOL, DOCX_TOOL, XLSX_TOOL, CALCULATOR_TOOL, FINANCIAL_CALCULATOR_TOOL]

# Execution dispatch
TOOL_EXECUTORS = {
    "web_search": execute_web_search,
    "web_fetch": execute_web_fetch,
    "file_read": execute_file_read,
    "file_write": execute_file_write,
    "calculator": execute_calculator,
    "financial_calculator": execute_financial_calculator,
    "create_chart": execute_create_chart,
    "create_docx": execute_create_docx,
    "create_xlsx": execute_create_xlsx,
}
