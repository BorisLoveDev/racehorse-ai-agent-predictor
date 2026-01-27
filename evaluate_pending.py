#!/usr/bin/env python3
"""
Evaluate Pending Predictions Script

Finds all predictions without outcomes and attempts to evaluate them
by fetching results from TabTouch. Useful for:
- Manual recovery when result checking fails
- Processing races with missing race_start_time
- Catching up after service restarts
"""

import asyncio
import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from tabtouch_parser import TabTouchParser


def get_pending_predictions(db_path: str) -> list[dict]:
    """Get all predictions without outcomes."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        SELECT DISTINCT
            p.prediction_id,
            p.race_url,
            p.race_location,
            p.race_number,
            p.race_start_time,
            p.agent_id,
            p.structured_bet_json,
            p.created_at,
            a.agent_name
        FROM predictions p
        JOIN agents a ON p.agent_id = a.agent_id
        WHERE p.prediction_id NOT IN (
            SELECT prediction_id FROM prediction_outcomes
        )
        ORDER BY p.created_at
    ''')

    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def save_outcome(
    db_path: str,
    prediction_id: int,
    finishing_order: list[dict],
    dividends: dict,
    bet_results: dict[str, bool],
    payouts: dict[str, float],
    total_bet_amount: float,
    actual_dividends_json: str = None
) -> int:
    """Save prediction outcome to database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    total_payout = sum(payouts.values())
    net_profit_loss = total_payout - total_bet_amount

    cursor.execute("""
        INSERT INTO prediction_outcomes (
            prediction_id, race_finished_at, finishing_order,
            dividends_json, win_result, place_result, exacta_result,
            quinella_result, trifecta_result, first4_result, qps_result,
            win_payout, place_payout, exacta_payout, quinella_payout,
            trifecta_payout, first4_payout, qps_payout,
            total_bet_amount, total_payout, net_profit_loss, actual_dividends_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        prediction_id,
        datetime.utcnow().isoformat(),
        json.dumps(finishing_order),
        json.dumps(dividends),
        1 if bet_results.get("win") else 0 if "win" in bet_results else None,
        1 if bet_results.get("place") else 0 if "place" in bet_results else None,
        1 if bet_results.get("exacta") else 0 if "exacta" in bet_results else None,
        1 if bet_results.get("quinella") else 0 if "quinella" in bet_results else None,
        1 if bet_results.get("trifecta") else 0 if "trifecta" in bet_results else None,
        1 if bet_results.get("first4") else 0 if "first4" in bet_results else None,
        1 if bet_results.get("qps") else 0 if "qps" in bet_results else None,
        payouts.get("win", 0.0),
        payouts.get("place", 0.0),
        payouts.get("exacta", 0.0),
        payouts.get("quinella", 0.0),
        payouts.get("trifecta", 0.0),
        payouts.get("first4", 0.0),
        payouts.get("qps", 0.0),
        total_bet_amount,
        total_payout,
        net_profit_loss,
        actual_dividends_json
    ))

    outcome_id = cursor.lastrowid
    conn.commit()

    # Update agent statistics
    _update_agent_statistics(
        cursor, prediction_id, bet_results, payouts,
        total_bet_amount, total_payout, net_profit_loss
    )
    conn.commit()
    conn.close()

    return outcome_id


def _update_agent_statistics(
    cursor: sqlite3.Cursor,
    prediction_id: int,
    bet_results: dict[str, bool],
    payouts: dict[str, float],
    total_bet_amount: float,
    total_payout: float,
    net_profit_loss: float
) -> None:
    """Update agent statistics after recording an outcome."""
    cursor.execute(
        "SELECT agent_id FROM predictions WHERE prediction_id = ?",
        (prediction_id,)
    )
    result = cursor.fetchone()
    if not result:
        return
    agent_id = result[0]

    total_bets = len(bet_results)
    total_wins = sum(1 for won in bet_results.values() if won)
    total_losses = total_bets - total_wins

    cursor.execute("""
        UPDATE agent_statistics
        SET total_predictions = total_predictions + 1,
            total_bets = total_bets + ?,
            total_wins = total_wins + ?,
            total_losses = total_losses + ?,
            total_bet_amount = total_bet_amount + ?,
            total_payout = total_payout + ?,
            net_profit_loss = net_profit_loss + ?,
            roi_percentage = CASE
                WHEN (total_bet_amount + ?) > 0
                THEN ((total_payout + ? - total_bet_amount - ?) / (total_bet_amount + ?)) * 100
                ELSE 0
            END,
            win_bets_placed = win_bets_placed + ?,
            win_bets_won = win_bets_won + ?,
            place_bets_placed = place_bets_placed + ?,
            place_bets_won = place_bets_won + ?,
            exacta_bets_placed = exacta_bets_placed + ?,
            exacta_bets_won = exacta_bets_won + ?,
            quinella_bets_placed = quinella_bets_placed + ?,
            quinella_bets_won = quinella_bets_won + ?,
            trifecta_bets_placed = trifecta_bets_placed + ?,
            trifecta_bets_won = trifecta_bets_won + ?,
            first4_bets_placed = first4_bets_placed + ?,
            first4_bets_won = first4_bets_won + ?,
            qps_bets_placed = qps_bets_placed + ?,
            qps_bets_won = qps_bets_won + ?,
            last_updated = CURRENT_TIMESTAMP
        WHERE agent_id = ?
    """, (
        total_bets, total_wins, total_losses,
        total_bet_amount, total_payout, net_profit_loss,
        total_bet_amount, total_payout, total_bet_amount, total_bet_amount,
        1 if "win" in bet_results else 0,
        1 if bet_results.get("win") else 0,
        1 if "place" in bet_results else 0,
        1 if bet_results.get("place") else 0,
        1 if "exacta" in bet_results else 0,
        1 if bet_results.get("exacta") else 0,
        1 if "quinella" in bet_results else 0,
        1 if bet_results.get("quinella") else 0,
        1 if "trifecta" in bet_results else 0,
        1 if bet_results.get("trifecta") else 0,
        1 if "first4" in bet_results else 0,
        1 if bet_results.get("first4") else 0,
        1 if "qps" in bet_results else 0,
        1 if bet_results.get("qps") else 0,
        agent_id
    ))


def build_actual_dividends(race_result, finishing_order: list) -> dict:
    """Build structured actual dividends with combinations."""
    actual = {}
    dividends = race_result.dividends

    # Win dividend
    if finishing_order and dividends.get("win"):
        winner = finishing_order[0]["number"]
        actual["win"] = {str(winner): dividends["win"]}

    # Place dividends
    if dividends.get("place") and len(finishing_order) >= 1:
        actual["place"] = {}
        place_div = dividends.get("place")
        if isinstance(place_div, list):
            for i, horse in enumerate(finishing_order[:min(3, len(place_div))]):
                actual["place"][str(horse["number"])] = place_div[i]
        elif isinstance(place_div, dict):
            for horse in finishing_order[:3]:
                num = str(horse["number"])
                if num in place_div:
                    actual["place"][num] = place_div[num]
        else:
            if finishing_order:
                actual["place"][str(finishing_order[0]["number"])] = place_div

    # Exacta
    if dividends.get("exacta") and len(finishing_order) >= 2:
        combo = f"{finishing_order[0]['number']}-{finishing_order[1]['number']}"
        div = dividends["exacta"]
        actual["exacta"] = {combo: div if not isinstance(div, dict) else div.get("amount", 0)}

    # Quinella
    if dividends.get("quinella") and len(finishing_order) >= 2:
        horses = sorted([finishing_order[0]["number"], finishing_order[1]["number"]])
        combo = f"{horses[0]}-{horses[1]}"
        div = dividends["quinella"]
        actual["quinella"] = {combo: div if not isinstance(div, dict) else div.get("amount", 0)}

    # Trifecta
    if dividends.get("trifecta") and len(finishing_order) >= 3:
        combo = f"{finishing_order[0]['number']}-{finishing_order[1]['number']}-{finishing_order[2]['number']}"
        div = dividends["trifecta"]
        actual["trifecta"] = {combo: div if not isinstance(div, dict) else div.get("amount", 0)}

    # First4
    if dividends.get("first4") and len(finishing_order) >= 4:
        combo = "-".join(str(h["number"]) for h in finishing_order[:4])
        div = dividends["first4"]
        actual["first4"] = {combo: div if not isinstance(div, dict) else div.get("amount", 0)}

    # QPS
    if dividends.get("qps"):
        div = dividends["qps"]
        actual["qps"] = {"qps": div if not isinstance(div, dict) else div.get("amount", 0)}

    return actual


def evaluate_prediction(prediction: dict, race_result) -> dict:
    """Evaluate a single prediction against results."""
    structured_bet = json.loads(prediction["structured_bet_json"])
    finishing_order = race_result.finishing_order

    if not finishing_order:
        return None

    # Extract positions
    winner = finishing_order[0] if len(finishing_order) > 0 else None
    second = finishing_order[1] if len(finishing_order) > 1 else None
    third = finishing_order[2] if len(finishing_order) > 2 else None
    fourth = finishing_order[3] if len(finishing_order) > 3 else None

    bet_results = {}
    payouts = {}

    # Win bet
    if structured_bet.get("win_bet"):
        win_bet = structured_bet["win_bet"]
        horse_num = win_bet["horse_number"]
        is_win = winner and winner.get("number") == horse_num

        bet_results["win"] = is_win
        if is_win and winner:
            odds = winner.get("fixed_win", 0) or winner.get("tote_win", 0)
            payouts["win"] = win_bet["amount"] * odds

    # Place bet
    if structured_bet.get("place_bet"):
        place_bet = structured_bet["place_bet"]
        horse_num = place_bet["horse_number"]
        placed_horses = [h.get("number") for h in finishing_order[:3] if h]
        is_place = horse_num in placed_horses

        bet_results["place"] = is_place
        if is_place:
            for horse in finishing_order[:3]:
                if horse.get("number") == horse_num:
                    odds = horse.get("fixed_place", 0) or horse.get("tote_place", 0)
                    payouts["place"] = place_bet["amount"] * odds
                    break

    # Exacta bet
    if structured_bet.get("exacta_bet"):
        exacta_bet = structured_bet["exacta_bet"]
        is_exacta = (
            winner and second and
            winner.get("number") == exacta_bet["first"] and
            second.get("number") == exacta_bet["second"]
        )
        bet_results["exacta"] = is_exacta
        if is_exacta and race_result.dividends.get("exacta"):
            div = race_result.dividends["exacta"]
            div_val = div if not isinstance(div, dict) else div.get("amount", 0)
            if isinstance(div_val, str):
                div_val = float(div_val.replace("$", "").replace(",", ""))
            payouts["exacta"] = exacta_bet["amount"] * div_val

    # Quinella bet
    if structured_bet.get("quinella_bet"):
        quinella_bet = structured_bet["quinella_bet"]
        horses = set(quinella_bet["horses"])
        top_two = {winner.get("number"), second.get("number")} if winner and second else set()
        is_quinella = horses == top_two

        bet_results["quinella"] = is_quinella
        if is_quinella and race_result.dividends.get("quinella"):
            div = race_result.dividends["quinella"]
            div_val = div if not isinstance(div, dict) else div.get("amount", 0)
            if isinstance(div_val, str):
                div_val = float(div_val.replace("$", "").replace(",", ""))
            payouts["quinella"] = quinella_bet["amount"] * div_val

    # Trifecta bet
    if structured_bet.get("trifecta_bet"):
        trifecta_bet = structured_bet["trifecta_bet"]
        is_trifecta = (
            winner and second and third and
            winner.get("number") == trifecta_bet["first"] and
            second.get("number") == trifecta_bet["second"] and
            third.get("number") == trifecta_bet["third"]
        )
        bet_results["trifecta"] = is_trifecta
        if is_trifecta and race_result.dividends.get("trifecta"):
            div = race_result.dividends["trifecta"]
            div_val = div if not isinstance(div, dict) else div.get("amount", 0)
            if isinstance(div_val, str):
                div_val = float(div_val.replace("$", "").replace(",", ""))
            payouts["trifecta"] = trifecta_bet["amount"] * div_val

    # First4 bet
    if structured_bet.get("first4_bet"):
        first4_bet = structured_bet["first4_bet"]
        actual_order = [h.get("number") for h in finishing_order[:4] if h]
        is_first4 = first4_bet["horses"] == actual_order

        bet_results["first4"] = is_first4
        if is_first4 and race_result.dividends.get("first4"):
            div = race_result.dividends["first4"]
            div_val = div if not isinstance(div, dict) else div.get("amount", 0)
            if isinstance(div_val, str):
                div_val = float(div_val.replace("$", "").replace(",", ""))
            payouts["first4"] = first4_bet["amount"] * div_val

    # QPS bet
    if structured_bet.get("qps_bet"):
        qps_bet = structured_bet["qps_bet"]
        horses = set(qps_bet["horses"])
        top_three = {h.get("number") for h in finishing_order[:3] if h}
        is_qps = len(horses & top_three) >= 2

        bet_results["qps"] = is_qps
        if is_qps and race_result.dividends.get("qps"):
            div = race_result.dividends["qps"]
            div_val = div if not isinstance(div, dict) else div.get("amount", 0)
            if isinstance(div_val, str):
                div_val = float(div_val.replace("$", "").replace(",", ""))
            payouts["qps"] = qps_bet["amount"] * div_val

    # Calculate total bet amount
    total_bet_amount = sum(
        bet.get("amount", 0)
        for bet_type in ["win_bet", "place_bet", "exacta_bet", "quinella_bet",
                         "trifecta_bet", "first4_bet", "qps_bet"]
        if (bet := structured_bet.get(bet_type))
    )

    actual_dividends = build_actual_dividends(race_result, finishing_order)

    return {
        "finishing_order": finishing_order,
        "dividends": race_result.dividends,
        "bet_results": bet_results,
        "payouts": payouts,
        "total_bet_amount": total_bet_amount,
        "actual_dividends_json": json.dumps(actual_dividends)
    }


async def evaluate_all_pending(db_path: str, dry_run: bool = False):
    """Evaluate all pending predictions."""
    print(f"Database: {db_path}")
    print(f"Dry run: {dry_run}")
    print()

    # Get pending predictions
    pending = get_pending_predictions(db_path)
    print(f"Found {len(pending)} pending predictions")

    if not pending:
        print("No pending predictions to evaluate.")
        return

    # Group by race_url to avoid duplicate fetches
    races = {}
    for pred in pending:
        url = pred["race_url"]
        if url not in races:
            races[url] = []
        races[url].append(pred)

    print(f"Across {len(races)} unique races")
    print()

    # Process each race
    evaluated = 0
    skipped = 0
    errors = 0

    async with TabTouchParser(headless=True) as parser:
        for race_url, predictions in races.items():
            print(f"\n{'='*60}")
            print(f"Race: {predictions[0]['race_location']} R{predictions[0]['race_number']}")
            print(f"URL: {race_url}")
            print(f"Predictions: {len(predictions)}")

            try:
                # Fetch results
                race_result = await parser.get_race_results(race_url)

                if not race_result or not race_result.finishing_order:
                    print("  No results available (race may not have finished)")
                    skipped += len(predictions)
                    continue

                print(f"  Results found! Finishing order:")
                for pos in race_result.finishing_order[:4]:
                    print(f"    {pos['position']}: #{pos['number']} {pos['name']}")

                # Evaluate each prediction
                for pred in predictions:
                    print(f"\n  Evaluating {pred['agent_name']} (ID: {pred['prediction_id']})...")

                    eval_result = evaluate_prediction(pred, race_result)

                    if not eval_result:
                        print("    Error: Could not evaluate (no finishing order)")
                        errors += 1
                        continue

                    total_payout = sum(eval_result["payouts"].values())
                    profit_loss = total_payout - eval_result["total_bet_amount"]

                    print(f"    Bet: ${eval_result['total_bet_amount']:.2f}")
                    print(f"    Won: ${total_payout:.2f}")
                    print(f"    P/L: ${profit_loss:+.2f}")

                    if not dry_run:
                        outcome_id = save_outcome(
                            db_path,
                            pred["prediction_id"],
                            eval_result["finishing_order"],
                            eval_result["dividends"],
                            eval_result["bet_results"],
                            eval_result["payouts"],
                            eval_result["total_bet_amount"],
                            eval_result["actual_dividends_json"]
                        )
                        print(f"    Saved outcome ID: {outcome_id}")

                    evaluated += 1

            except Exception as e:
                print(f"  Error: {e}")
                errors += len(predictions)

    print(f"\n{'='*60}")
    print("Summary:")
    print(f"  Evaluated: {evaluated}")
    print(f"  Skipped (no results): {skipped}")
    print(f"  Errors: {errors}")


def main():
    parser = argparse.ArgumentParser(description="Evaluate pending predictions")
    parser.add_argument(
        "--db",
        default="races.db",
        help="Path to database (default: races.db)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't save outcomes, just show what would be done"
    )
    args = parser.parse_args()

    # Check database exists
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Error: Database not found: {db_path}")
        sys.exit(1)

    asyncio.run(evaluate_all_pending(str(db_path), args.dry_run))


if __name__ == "__main__":
    main()
