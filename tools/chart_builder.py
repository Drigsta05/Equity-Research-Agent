"""Chart builder tool using matplotlib — produces PNG files for embedding in reports."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("output")

CHART_TOOL = {
    "name": "create_chart",
    "description": (
        "Create a chart (PNG image) for embedding in the equity research report. "
        "Supports bar, grouped_bar, line, stacked_bar, and waterfall chart types. "
        "Returns the filename of the saved PNG. Use this instead of tables for "
        "visual data presentation in the report."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Output PNG filename, e.g., 'revenue_by_segment.png'",
            },
            "chart_type": {
                "type": "string",
                "enum": ["bar", "grouped_bar", "line", "stacked_bar", "waterfall"],
                "description": "Type of chart to create.",
            },
            "title": {
                "type": "string",
                "description": "Chart title displayed at top.",
            },
            "x_label": {
                "type": "string",
                "description": "Label for the x-axis.",
                "default": "",
            },
            "y_label": {
                "type": "string",
                "description": "Label for the y-axis.",
                "default": "",
            },
            "categories": {
                "type": "array",
                "items": {"type": "string"},
                "description": "X-axis category labels (e.g., ['FY2022', 'FY2023', 'FY2024']).",
            },
            "series": {
                "type": "array",
                "description": (
                    "Data series. Each series has a name and values array. "
                    "For single-series charts (bar, line), use one series. "
                    "For multi-series (grouped_bar, stacked_bar, line), use multiple."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Series label for the legend.",
                        },
                        "values": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "Data values, one per category.",
                        },
                    },
                    "required": ["name", "values"],
                },
            },
            "y_format": {
                "type": "string",
                "enum": ["number", "percent", "currency", "billions"],
                "description": "How to format y-axis tick labels.",
                "default": "number",
            },
            "show_values": {
                "type": "boolean",
                "description": "Whether to show data values on the chart.",
                "default": False,
            },
            "colors": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional custom hex colors for each series (e.g., ['#003366', '#0055CC']).",
            },
        },
        "required": ["filename", "chart_type", "title", "categories", "series"],
    },
}


# Professional color palette
DEFAULT_COLORS = [
    "#003366",  # dark navy
    "#0055CC",  # blue
    "#5B9BD5",  # light blue
    "#70AD47",  # green
    "#FFC000",  # gold
    "#C00000",  # dark red
    "#7030A0",  # purple
    "#ED7D31",  # orange
]


def execute_create_chart(
    filename: str,
    chart_type: str,
    title: str,
    categories: list[str],
    series: list[dict],
    x_label: str = "",
    y_label: str = "",
    y_format: str = "number",
    show_values: bool = False,
    colors: list[str] | None = None,
) -> str:
    """Create a chart and save as PNG."""
    try:
        import matplotlib
        matplotlib.use("Agg")  # non-interactive backend
        import matplotlib.pyplot as plt
        import matplotlib.ticker as mticker
        import numpy as np

        palette = colors if colors and len(colors) >= len(series) else DEFAULT_COLORS

        fig, ax = plt.subplots(figsize=(10, 6))
        fig.patch.set_facecolor("white")
        ax.set_facecolor("white")

        x = np.arange(len(categories))
        n_series = len(series)

        if chart_type == "bar":
            vals = series[0]["values"]
            bars = ax.bar(x, vals, color=palette[0], width=0.6, edgecolor="white")
            if show_values:
                _annotate_bars(ax, bars, y_format)

        elif chart_type == "grouped_bar":
            width = 0.8 / n_series
            for i, s in enumerate(series):
                offset = (i - n_series / 2 + 0.5) * width
                bars = ax.bar(x + offset, s["values"], width=width,
                              label=s["name"], color=palette[i % len(palette)],
                              edgecolor="white")
                if show_values:
                    _annotate_bars(ax, bars, y_format)
            ax.legend(frameon=False, fontsize=9)

        elif chart_type == "stacked_bar":
            bottom = np.zeros(len(categories))
            for i, s in enumerate(series):
                vals = np.array(s["values"])
                ax.bar(x, vals, bottom=bottom, label=s["name"],
                       color=palette[i % len(palette)], width=0.6, edgecolor="white")
                bottom += vals
            ax.legend(frameon=False, fontsize=9)

        elif chart_type == "line":
            for i, s in enumerate(series):
                ax.plot(x, s["values"], marker="o", linewidth=2.5, markersize=6,
                        label=s["name"], color=palette[i % len(palette)])
                if show_values:
                    for j, v in enumerate(s["values"]):
                        ax.annotate(_fmt_val(v, y_format),
                                    (x[j], v), textcoords="offset points",
                                    xytext=(0, 10), ha="center", fontsize=8)
            if n_series > 1:
                ax.legend(frameon=False, fontsize=9)

        elif chart_type == "waterfall":
            vals = series[0]["values"]
            cumulative = np.zeros(len(vals) + 1)
            for i, v in enumerate(vals):
                cumulative[i + 1] = cumulative[i] + v
            bar_colors = [palette[2] if v >= 0 else palette[5] for v in vals]
            ax.bar(x, vals, bottom=cumulative[:-1], color=bar_colors,
                   width=0.6, edgecolor="white")
            if show_values:
                for i, v in enumerate(vals):
                    y_pos = cumulative[i] + v / 2
                    ax.annotate(_fmt_val(v, y_format),
                                (x[i], y_pos), ha="center", fontsize=8)
        else:
            return json.dumps({"error": f"Unknown chart_type: {chart_type}"})

        # Formatting
        ax.set_xticks(x)
        ax.set_xticklabels(categories, fontsize=9)
        ax.set_title(title, fontsize=14, fontweight="bold", pad=15, color="#333333")
        if x_label:
            ax.set_xlabel(x_label, fontsize=10, color="#555555")
        if y_label:
            ax.set_ylabel(y_label, fontsize=10, color="#555555")

        # Y-axis formatting
        if y_format == "percent":
            ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.1f}%"))
        elif y_format == "currency":
            ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"${v:,.0f}"))
        elif y_format == "billions":
            ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"${v:,.1f}B"))

        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#CCCCCC")
        ax.spines["bottom"].set_color("#CCCCCC")
        ax.tick_params(colors="#555555")
        ax.grid(axis="y", alpha=0.3, color="#CCCCCC")

        plt.tight_layout()

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        filepath = OUTPUT_DIR / filename
        fig.savefig(str(filepath), dpi=150, bbox_inches="tight",
                    facecolor="white", edgecolor="none")
        plt.close(fig)

        return json.dumps({
            "success": True,
            "filename": filename,
            "path": str(filepath),
            "chart_type": chart_type,
        })

    except ImportError:
        return json.dumps({
            "error": "matplotlib not installed. Run: pip install matplotlib"
        })
    except Exception as e:
        logger.exception("Chart creation failed")
        return json.dumps({"error": f"Chart creation failed: {str(e)}"})


def _fmt_val(v: float, fmt: str) -> str:
    """Format a single value for annotation."""
    if fmt == "percent":
        return f"{v:.1f}%"
    elif fmt == "currency":
        return f"${v:,.0f}"
    elif fmt == "billions":
        return f"${v:.1f}B"
    else:
        if abs(v) >= 1000:
            return f"{v:,.0f}"
        elif abs(v) >= 1:
            return f"{v:.1f}"
        else:
            return f"{v:.2f}"


def _annotate_bars(ax, bars, fmt: str) -> None:
    """Add value labels on top of bars."""
    for bar in bars:
        height = bar.get_height()
        if height != 0:
            ax.annotate(_fmt_val(height, fmt),
                        xy=(bar.get_x() + bar.get_width() / 2, height),
                        xytext=(0, 4), textcoords="offset points",
                        ha="center", fontsize=8, color="#333333")
