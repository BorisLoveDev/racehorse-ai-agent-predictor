"""
View agent statistics from the database.
Usage: python3 view_stats.py
"""

import sys
from src.config.settings import get_settings
from src.database.repositories import StatisticsRepository, PredictionRepository


def print_header(title: str):
    """Print a formatted header."""
    print(f"\n{'='*70}")
    print(f" {title}")
    print(f"{'='*70}\n")


def print_agent_stats(stats: dict):
    """Print detailed statistics for an agent."""
    agent_name = stats["agent_name"].capitalize()

    print(f"🤖 {agent_name} Agent")
    print(f"{'─'*70}")

    # Overall statistics
    total_predictions = stats["total_predictions"]
    total_bets = stats["total_bets"]
    total_wins = stats["total_wins"]
    total_losses = stats["total_losses"]

    print(f"\n📊 Overall Performance:")
    print(f"  Total Predictions: {total_predictions}")
    print(f"  Total Bets Placed: {total_bets}")
    print(f"  Wins: {total_wins} ({total_wins/total_bets*100 if total_bets > 0 else 0:.1f}%)")
    print(f"  Losses: {total_losses}")

    # Financial statistics
    total_bet_amount = stats["total_bet_amount"]
    total_payout = stats["total_payout"]
    net_profit_loss = stats["net_profit_loss"]
    roi = stats["roi_percentage"]

    print(f"\n💰 Financial Performance:")
    print(f"  Total Wagered: ${total_bet_amount:.2f}")
    print(f"  Total Returns: ${total_payout:.2f}")
    print(f"  Net P/L: ${net_profit_loss:+.2f}")
    print(f"  ROI: {roi:+.2f}%")

    # Bet type breakdown
    print(f"\n📈 Bet Type Performance:")

    bet_types = {
        "Win": stats["win_bets"],
        "Place": stats["place_bets"],
        "Exacta": stats["exacta_bets"],
        "Quinella": stats["quinella_bets"],
        "Trifecta": stats["trifecta_bets"],
        "First4": stats["first4_bets"],
        "QPS": stats["qps_bets"]
    }

    for bet_type, bet_stats in bet_types.items():
        placed = bet_stats["placed"]
        won = bet_stats["won"]

        if placed > 0:
            win_rate = won / placed * 100
            print(f"  {bet_type:10s}: {placed:3d} placed, {won:3d} won ({win_rate:5.1f}%)")

    print(f"\n  Last Updated: {stats['last_updated']}")
    print()


def view_recent_predictions(limit: int = 10):
    """View recent predictions."""
    print_header("Recent Predictions")

    settings = get_settings()
    pred_repo = PredictionRepository(db_path=settings.database.path)

    # Get predictions (this would need a method in the repo)
    # For now, we'll just show the statistics
    print("Note: Recent predictions view requires additional repository methods.")
    print("Use: sqlite3 races.db 'SELECT * FROM predictions ORDER BY created_at DESC LIMIT 10'")


def main():
    """Main entry point."""
    settings = get_settings()
    stats_repo = StatisticsRepository(db_path=settings.database.path)

    print_header("🏇 Horse Racing Agent Statistics")

    # Get all agent statistics
    all_stats = stats_repo.get_all_statistics()

    if not all_stats:
        print("❌ No statistics found!")
        print("\nPossible reasons:")
        print("  1. No races have been analyzed yet")
        print("  2. No race results have been evaluated yet")
        print("  3. Database migrations not run")
        print("\nRun: python3 src/database/migrations.py")
        return

    # Print statistics for each agent
    for stats in all_stats:
        print_agent_stats(stats)

    # Comparison
    if len(all_stats) > 1:
        print_header("Agent Comparison")

        print(f"{'Agent':<15} {'Predictions':<12} {'Win Rate':<12} {'ROI':<12} {'P/L':<12}")
        print(f"{'─'*15} {'─'*12} {'─'*12} {'─'*12} {'─'*12}")

        for stats in sorted(all_stats, key=lambda x: x["roi_percentage"], reverse=True):
            agent_name = stats["agent_name"].capitalize()
            predictions = stats["total_predictions"]
            total_bets = stats["total_bets"]
            total_wins = stats["total_wins"]
            win_rate = (total_wins / total_bets * 100) if total_bets > 0 else 0
            roi = stats["roi_percentage"]
            profit_loss = stats["net_profit_loss"]

            print(f"{agent_name:<15} {predictions:<12} {win_rate:>10.1f}% {roi:>10.1f}% ${profit_loss:>9.2f}")

        print()

        # Determine best agent
        best_roi = max(all_stats, key=lambda x: x["roi_percentage"])
        best_profit = max(all_stats, key=lambda x: x["net_profit_loss"])

        print(f"🏆 Best ROI: {best_roi['agent_name'].capitalize()} ({best_roi['roi_percentage']:+.1f}%)")
        print(f"💰 Best P/L: {best_profit['agent_name'].capitalize()} (${best_profit['net_profit_loss']:+.2f})")
        print()

    # Tips for improvement
    print_header("💡 Performance Insights")

    for stats in all_stats:
        agent_name = stats["agent_name"].capitalize()
        roi = stats["roi_percentage"]
        win_rate = (stats["total_wins"] / stats["total_bets"] * 100) if stats["total_bets"] > 0 else 0

        if roi < -10:
            print(f"⚠️  {agent_name} has poor ROI ({roi:+.1f}%)")
            print(f"   Consider increasing MIN_CONFIDENCE_TO_BET threshold")
            print()
        elif roi > 20:
            print(f"✅ {agent_name} performing excellently ({roi:+.1f}%)")
            print(f"   Current strategy is working well")
            print()

        if win_rate < 20:
            print(f"⚠️  {agent_name} has low win rate ({win_rate:.1f}%)")
            print(f"   May be taking too many risky bets")
            print()
        elif win_rate > 40:
            print(f"✅ {agent_name} has strong win rate ({win_rate:.1f}%)")
            print(f"   Good bet selection")
            print()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
