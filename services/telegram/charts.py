"""
Chart generation for Telegram notifications.
"""

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from io import BytesIO
from datetime import datetime


def generate_pl_chart(chart_data: list[dict], period: str) -> BytesIO:
    """Generate cumulative P/L chart.

    Args:
        chart_data: List of dicts with keys: agent, race_time, cumulative_pl
        period: Period label for chart title

    Returns:
        BytesIO buffer containing PNG image
    """
    if not chart_data:
        # Create empty chart
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.text(0.5, 0.5, "No data available for this period",
                ha='center', va='center', fontsize=14)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')
    else:
        fig, ax = plt.subplots(figsize=(10, 6))

        # Group by agent
        agents = {}
        for row in chart_data:
            agent = row["agent"]
            if agent not in agents:
                agents[agent] = {"times": [], "pl": []}
            agents[agent]["times"].append(row["race_time"])
            agents[agent]["pl"].append(row["cumulative_pl"])

        # Plot each agent
        colors = {"gemini": "#4285F4", "grok": "#FF6B6B"}
        for agent, data in agents.items():
            ax.plot(data["times"], data["pl"], label=agent.capitalize(),
                    color=colors.get(agent, "#888"), linewidth=2, marker='o', markersize=4)

        # Zero line
        ax.axhline(y=0, color='gray', linestyle='--', alpha=0.5)

        # Labels and styling
        ax.set_xlabel("Race Time", fontsize=11)
        ax.set_ylabel("Cumulative P/L ($)", fontsize=11)
        ax.set_title(f"P/L by Agent ({period})", fontsize=13, fontweight='bold')
        ax.legend(loc='best')
        ax.grid(True, alpha=0.3)

        # Format dates on x-axis
        if chart_data:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M'))
            plt.xticks(rotation=45)

        plt.tight_layout()

    # Save to buffer
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)

    return buf
