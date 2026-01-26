"""
Скрипт для массовой оценки результатов всех неоценённых предсказаний.
"""

import asyncio
import sqlite3
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from tabtouch_parser import TabTouchParser


def get_unevaluated_races(db_path: str = "races.db") -> list[dict]:
    """Получить все неоценённые предсказания сгруппированные по заездам."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        SELECT DISTINCT p.race_url, p.race_location, p.race_number
        FROM predictions p
        WHERE p.prediction_id NOT IN (SELECT prediction_id FROM prediction_outcomes)
    ''')
    races = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return races


def get_predictions_for_race(db_path: str, race_url: str) -> list[dict]:
    """Получить все предсказания для конкретного заезда."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        SELECT p.prediction_id, a.agent_name, p.structured_bet_json, p.confidence_score
        FROM predictions p
        JOIN agents a ON p.agent_id = a.agent_id
        WHERE p.race_url = ?
        AND p.prediction_id NOT IN (SELECT prediction_id FROM prediction_outcomes)
    ''', (race_url,))

    predictions = []
    for row in cursor.fetchall():
        pred = dict(row)
        pred['structured_bet'] = json.loads(pred['structured_bet_json']) if pred['structured_bet_json'] else {}
        predictions.append(pred)

    conn.close()
    return predictions


def save_outcome(db_path: str, prediction_id: int, finishing_order: list,
                 dividends: dict, bet_results: dict, payouts: dict, total_bet_amount: float):
    """Сохранить результат оценки в БД."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    total_payout = sum(payouts.values())
    profit_loss = total_payout - total_bet_amount

    cursor.execute('''
        INSERT INTO prediction_outcomes (
            prediction_id, finishing_order, dividends_json,
            win_result, place_result, exacta_result, quinella_result,
            trifecta_result, first4_result, qps_result,
            win_payout, place_payout, exacta_payout, quinella_payout,
            trifecta_payout, first4_payout, qps_payout,
            total_bet_amount, total_payout, net_profit_loss
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        prediction_id,
        json.dumps(finishing_order),
        json.dumps(dividends),
        bet_results.get('win', False),
        bet_results.get('place', False),
        bet_results.get('exacta', False),
        bet_results.get('quinella', False),
        bet_results.get('trifecta', False),
        bet_results.get('first4', False),
        bet_results.get('qps', False),
        payouts.get('win', 0),
        payouts.get('place', 0),
        payouts.get('exacta', 0),
        payouts.get('quinella', 0),
        payouts.get('trifecta', 0),
        payouts.get('first4', 0),
        payouts.get('qps', 0),
        total_bet_amount,
        total_payout,
        profit_loss
    ))

    conn.commit()
    conn.close()
    return cursor.lastrowid


def extract_numbers_from_dividends(dividends: dict) -> list[int]:
    """Извлечь номера лошадей из комбинаций дивидендов."""
    numbers = []

    # Приоритет: trifecta (3 номера), exacta (2 номера), quinella (2 номера)
    for key in ['trifecta', 'first_4', 'exacta', 'quinella']:
        if key in dividends:
            combo = dividends[key].get('combination', '')
            if combo:
                parts = combo.split('-')
                try:
                    nums = [int(p) for p in parts]
                    if len(nums) >= 2:
                        return nums
                except ValueError:
                    continue
    return numbers


def parse_dividend_amount(dividend_info: dict) -> float:
    """Парсинг суммы дивиденда из формата {'combination': '1-5', 'amount': '$1.70'}."""
    if not dividend_info:
        return 0.0
    amount_str = dividend_info.get('amount', '')
    if not amount_str:
        return 0.0
    # Убираем $ и запятые, парсим float
    try:
        return float(amount_str.replace('$', '').replace(',', ''))
    except ValueError:
        return 0.0


def evaluate_prediction(prediction: dict, race_result) -> tuple[dict, dict, float]:
    """Оценить предсказание против результатов."""
    structured_bet = prediction['structured_bet']
    finishing_order = race_result.finishing_order
    dividends = race_result.dividends or {}

    if not finishing_order:
        return {}, {}, 0

    # Если номера лошадей не извлечены из HTML, берём из дивидендов
    order_numbers = extract_numbers_from_dividends(dividends)
    if order_numbers:
        # Дополняем finishing_order номерами из дивидендов
        for i, horse in enumerate(finishing_order):
            if i < len(order_numbers) and horse.get('number', 0) == 0:
                horse['number'] = order_numbers[i]

    # Позиции
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
        if is_exacta:
            div_amount = parse_dividend_amount(dividends.get("exacta"))
            if div_amount:
                payouts["exacta"] = exacta_bet["amount"] * div_amount

    # Quinella bet
    if structured_bet.get("quinella_bet"):
        quinella_bet = structured_bet["quinella_bet"]
        horses = set(quinella_bet["horses"])
        top_two = {winner.get("number"), second.get("number")} if winner and second else set()
        is_quinella = horses == top_two
        bet_results["quinella"] = is_quinella
        if is_quinella:
            div_amount = parse_dividend_amount(dividends.get("quinella"))
            if div_amount:
                payouts["quinella"] = quinella_bet["amount"] * div_amount

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
        if is_trifecta:
            div_amount = parse_dividend_amount(dividends.get("trifecta"))
            if div_amount:
                payouts["trifecta"] = trifecta_bet["amount"] * div_amount

    # First4 bet
    if structured_bet.get("first4_bet"):
        first4_bet = structured_bet["first4_bet"]
        actual_order = [h.get("number") for h in finishing_order[:4] if h]
        is_first4 = first4_bet["horses"] == actual_order
        bet_results["first4"] = is_first4
        if is_first4:
            div_amount = parse_dividend_amount(dividends.get("first_4"))
            if div_amount:
                payouts["first4"] = first4_bet["amount"] * div_amount

    # QPS bet
    if structured_bet.get("qps_bet"):
        qps_bet = structured_bet["qps_bet"]
        horses = set(qps_bet["horses"])
        top_three = {h.get("number") for h in finishing_order[:3] if h}
        is_qps = len(horses & top_three) >= 2
        bet_results["qps"] = is_qps
        if is_qps:
            div_amount = parse_dividend_amount(dividends.get("qps"))
            if div_amount:
                payouts["qps"] = qps_bet["amount"] * div_amount

    # Total bet amount
    total_bet_amount = sum(
        bet.get("amount", 0)
        for bet_type in ["win_bet", "place_bet", "exacta_bet", "quinella_bet",
                         "trifecta_bet", "first4_bet", "qps_bet"]
        if (bet := structured_bet.get(bet_type))
    )

    return bet_results, payouts, total_bet_amount


async def main():
    db_path = "races.db"

    races = get_unevaluated_races(db_path)
    print(f"Найдено {len(races)} заездов для оценки\n")

    if not races:
        print("Нет неоценённых заездов")
        return

    parser = TabTouchParser(headless=True)

    async with parser:
        results_found = 0
        results_not_found = 0
        predictions_evaluated = 0
        total_profit_loss = 0.0

        for race in races:
            race_url = race['race_url']
            print(f"\n{'='*60}")
            print(f"Заезд: {race_url}")

            try:
                # Получить результаты
                race_result = await parser.get_race_results(race_url)

                if not race_result or not race_result.finishing_order:
                    print(f"  ⚠ Результаты не найдены")
                    results_not_found += 1
                    continue

                results_found += 1
                print(f"  ✓ Результаты найдены: {[h.get('number') for h in race_result.finishing_order[:3]]}")

                # Получить предсказания для этого заезда
                predictions = get_predictions_for_race(db_path, race_url)
                print(f"  Предсказаний: {len(predictions)}")

                for pred in predictions:
                    bet_results, payouts, total_bet = evaluate_prediction(pred, race_result)

                    # Сохранить результат
                    finishing_order_data = [
                        {
                            "number": h.get("number"),
                            "name": h.get("name"),
                            "fixed_win": h.get("fixed_win"),
                            "fixed_place": h.get("fixed_place"),
                            "tote_win": h.get("tote_win"),
                            "tote_place": h.get("tote_place")
                        }
                        for h in race_result.finishing_order
                    ]

                    save_outcome(
                        db_path,
                        pred['prediction_id'],
                        finishing_order_data,
                        race_result.dividends or {},
                        bet_results,
                        payouts,
                        total_bet
                    )

                    total_payout = sum(payouts.values())
                    profit_loss = total_payout - total_bet
                    total_profit_loss += profit_loss
                    predictions_evaluated += 1

                    wins = [k for k, v in bet_results.items() if v]
                    wins_str = ", ".join(wins) if wins else "none"
                    print(f"    {pred['agent_name']}: Bet ${total_bet:.0f}, "
                          f"Won ${total_payout:.0f}, P/L: ${profit_loss:+.0f} | Wins: {wins_str}")

            except Exception as e:
                print(f"  ✗ Ошибка: {e}")
                import traceback
                traceback.print_exc()
                results_not_found += 1

    print(f"\n{'='*60}")
    print(f"ИТОГО:")
    print(f"  Заездов с результатами: {results_found}")
    print(f"  Заездов без результатов: {results_not_found}")
    print(f"  Предсказаний оценено: {predictions_evaluated}")
    print(f"  Общий P/L: ${total_profit_loss:+.2f}")


if __name__ == "__main__":
    asyncio.run(main())
