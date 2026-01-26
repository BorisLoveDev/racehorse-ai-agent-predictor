#!/usr/bin/env python3
"""
Пример интеграции парсера с AI агентами для анализа ставок

Этот файл показывает как:
1. Получить данные ближайшего заезда
2. Подготовить данные для AI анализа
3. Дождаться результатов и сравнить с прогнозом
"""

import asyncio
import json
from datetime import datetime
from typing import Optional

from tabtouch_parser import (
    RaceTracker,
    RaceDetails,
    RaceResult,
    format_race_for_analysis
)


# ============== AI Integration Interface ==============

class AIAnalysisResult:
    """Результат анализа от AI агента"""

    def __init__(
        self,
        predicted_winner: int,  # Номер лошади
        predicted_places: list[int],  # Топ-3 по мнению AI
        confidence: float,  # 0.0 - 1.0
        reasoning: str,
        timestamp: str = None
    ):
        self.predicted_winner = predicted_winner
        self.predicted_places = predicted_places
        self.confidence = confidence
        self.reasoning = reasoning
        self.timestamp = timestamp or datetime.now().isoformat()


def prepare_prompt_for_ai(race_data: dict) -> str:
    """
    Подготовить промпт для AI агента

    Возвращает структурированный текст для анализа
    """
    race_info = race_data["race_info"]
    runners = race_data["runners"]

    prompt = f"""
Analyze this horse race and predict the most likely winner and places (top 3).

RACE INFORMATION:
- Location: {race_info['location']}
- Track Condition: {race_info['track_condition']}
- Distance: {race_info['distance']}
- Race Type: {race_info['race_type']}

RUNNERS (sorted by fixed odds):
"""

    # Сортируем по коэффициентам (фавориты первые)
    sorted_runners = sorted(
        runners,
        key=lambda x: x['odds']['fixed_win'] if x['odds']['fixed_win'] > 0 else 999
    )

    for r in sorted_runners:
        prompt += f"""
#{r['number']} {r['name']}
  - Form: {r['form']}
  - Barrier: {r['barrier']}
  - Weight: {r['weight']}
  - Jockey: {r['jockey']}
  - Trainer: {r['trainer']}
  - Rating: {r['rating']}
  - Fixed Odds: Win {r['odds']['fixed_win']:.2f} / Place {r['odds']['fixed_place']:.2f}
"""

    prompt += """

Based on the form, barrier position, weight, jockey quality, trainer statistics,
and current odds, provide your analysis:

1. PREDICTED WINNER: [number and name]
2. PREDICTED PLACES (top 3): [numbers]
3. CONFIDENCE LEVEL: [0.0 to 1.0]
4. KEY REASONING: [brief explanation]

Format your response as JSON:
{
  "predicted_winner": <number>,
  "predicted_places": [<num1>, <num2>, <num3>],
  "confidence": <0.0-1.0>,
  "reasoning": "<explanation>"
}
"""

    return prompt


def evaluate_prediction(prediction: AIAnalysisResult, result: RaceResult) -> dict:
    """
    Оценить точность прогноза после заезда

    Returns:
        dict с метриками точности
    """
    actual_order = [pos['number'] for pos in result.finishing_order]

    # Проверяем победителя
    winner_correct = prediction.predicted_winner == actual_order[0] if actual_order else False

    # Проверяем попадание в топ-3
    actual_top3 = set(actual_order[:3])
    predicted_top3 = set(prediction.predicted_places[:3])
    top3_hits = len(actual_top3 & predicted_top3)

    # Точная последовательность
    exact_trifecta = prediction.predicted_places[:3] == actual_order[:3]

    return {
        "winner_correct": winner_correct,
        "top3_hits": top3_hits,
        "top3_accuracy": top3_hits / 3,
        "exact_trifecta": exact_trifecta,
        "prediction": {
            "winner": prediction.predicted_winner,
            "places": prediction.predicted_places,
            "confidence": prediction.confidence
        },
        "actual": {
            "winner": actual_order[0] if actual_order else None,
            "places": actual_order[:3]
        }
    }


# ============== Main Analysis Flow ==============

class RaceAnalyzer:
    """
    Система анализа заездов

    Workflow:
    1. Получить данные ближайшего заезда
    2. Отправить на анализ AI агенту
    3. Сохранить прогноз
    4. Дождаться результатов
    5. Оценить точность прогноза
    """

    def __init__(self):
        self.tracker = RaceTracker(headless=True)
        self.predictions: dict[str, AIAnalysisResult] = {}
        self.results: dict[str, dict] = {}

    async def analyze_next_race(self, ai_callback=None) -> dict:
        """
        Полный цикл анализа ближайшего заезда

        Args:
            ai_callback: Функция для вызова AI агента
                         async def callback(prompt: str) -> AIAnalysisResult
        """
        # 1. Получаем данные заезда
        print("Fetching next race...")
        race_details = await self.tracker.get_next_race_details()

        if not race_details:
            return {"error": "No upcoming races"}

        print(f"Race: {race_details.race_name}")
        print(f"Location: {race_details.location}")
        print(f"Start: {race_details.start_time}")
        print(f"Runners: {len(race_details.runners)}")

        # 2. Подготавливаем данные для AI
        race_data = format_race_for_analysis(race_details)
        prompt = prepare_prompt_for_ai(race_data)

        # 3. Получаем прогноз от AI
        if ai_callback:
            print("\nSending to AI for analysis...")
            prediction = await ai_callback(prompt)
        else:
            # Демо-прогноз на основе коэффициентов
            print("\nUsing demo prediction (based on odds)...")
            prediction = self._demo_prediction(race_details)

        self.predictions[race_details.url] = prediction

        print(f"\n--- AI PREDICTION ---")
        print(f"Winner: #{prediction.predicted_winner}")
        print(f"Top 3: {prediction.predicted_places}")
        print(f"Confidence: {prediction.confidence:.1%}")
        print(f"Reasoning: {prediction.reasoning}")

        return {
            "race_url": race_details.url,
            "race_data": race_data,
            "prediction": {
                "winner": prediction.predicted_winner,
                "places": prediction.predicted_places,
                "confidence": prediction.confidence,
                "reasoning": prediction.reasoning
            }
        }

    def _demo_prediction(self, race: RaceDetails) -> AIAnalysisResult:
        """Демо-прогноз на основе коэффициентов"""
        # Сортируем по fixed_win (меньше = фаворит)
        sorted_runners = sorted(
            [r for r in race.runners if r.fixed_win > 0],
            key=lambda x: x.fixed_win
        )

        if len(sorted_runners) < 3:
            return AIAnalysisResult(
                predicted_winner=race.runners[0].number if race.runners else 0,
                predicted_places=[r.number for r in race.runners[:3]],
                confidence=0.3,
                reasoning="Not enough data"
            )

        return AIAnalysisResult(
            predicted_winner=sorted_runners[0].number,
            predicted_places=[r.number for r in sorted_runners[:3]],
            confidence=0.5,
            reasoning=f"Based on odds: #{sorted_runners[0].number} {sorted_runners[0].name} is the favorite at ${sorted_runners[0].fixed_win}"
        )

    async def wait_for_result(self, race_url: str, check_interval: int = 60) -> Optional[dict]:
        """
        Дождаться результатов и оценить прогноз

        Args:
            race_url: URL заезда
            check_interval: Интервал проверки в секундах
        """
        if race_url not in self.predictions:
            return {"error": "No prediction found for this race"}

        prediction = self.predictions[race_url]

        print(f"\nWaiting for results...")
        print(f"Our prediction: Winner #{prediction.predicted_winner}, Top-3: {prediction.predicted_places}")

        while True:
            result = await self.tracker.check_race_result(race_url)

            if result and result.finishing_order:
                print("\n" + "="*60)
                print("RACE FINISHED!")
                print("="*60)

                # Показываем результаты
                print("\nActual results:")
                for pos in result.finishing_order:
                    print(f"  {pos['position']}: #{pos['number']} {pos['name']}")

                # Оцениваем прогноз
                evaluation = evaluate_prediction(prediction, result)
                self.results[race_url] = evaluation

                print("\n--- PREDICTION EVALUATION ---")
                print(f"Winner correct: {'✓' if evaluation['winner_correct'] else '✗'}")
                print(f"Top-3 hits: {evaluation['top3_hits']}/3 ({evaluation['top3_accuracy']:.1%})")
                print(f"Exact trifecta: {'✓' if evaluation['exact_trifecta'] else '✗'}")

                return evaluation

            print(f"Race not finished. Checking again in {check_interval}s...")
            await asyncio.sleep(check_interval)

    def get_statistics(self) -> dict:
        """Получить статистику по всем прогнозам"""
        if not self.results:
            return {"total_races": 0}

        total = len(self.results)
        winners_correct = sum(1 for r in self.results.values() if r['winner_correct'])
        avg_top3_accuracy = sum(r['top3_accuracy'] for r in self.results.values()) / total
        exact_trifectas = sum(1 for r in self.results.values() if r['exact_trifecta'])

        return {
            "total_races": total,
            "winners_correct": winners_correct,
            "winner_accuracy": winners_correct / total,
            "avg_top3_accuracy": avg_top3_accuracy,
            "exact_trifectas": exact_trifectas
        }


# ============== Example Usage ==============

async def main():
    """Пример полного цикла анализа"""

    analyzer = RaceAnalyzer()

    print("="*60)
    print("RACE ANALYSIS SYSTEM")
    print("="*60)

    # Анализируем ближайший заезд
    analysis = await analyzer.analyze_next_race()

    if "error" in analysis:
        print(f"Error: {analysis['error']}")
        return

    # Сохраняем для дальнейшего использования
    with open("current_analysis.json", "w") as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False)

    print(f"\nAnalysis saved to: current_analysis.json")
    print(f"Race URL: {analysis['race_url']}")

    # Опционально: ждать результаты
    print("\nWould you like to wait for results? (This may take a while)")
    print("Press Ctrl+C to exit, or the script will continue monitoring...")

    try:
        evaluation = await analyzer.wait_for_result(
            analysis['race_url'],
            check_interval=60
        )

        # Сохраняем оценку
        with open("evaluation_result.json", "w") as f:
            json.dump(evaluation, f, indent=2)

        print(f"\nEvaluation saved to: evaluation_result.json")

    except KeyboardInterrupt:
        print("\nMonitoring stopped. You can check results later.")


async def demo_batch_analysis():
    """Демо пакетного анализа нескольких заездов"""

    tracker = RaceTracker(headless=True)

    print("Fetching upcoming races...")
    races = await tracker.get_upcoming_races(limit=5)

    print(f"\nFound {len(races)} races:\n")

    all_data = []

    for race in races:
        print(f"Processing: {race.location} {race.race_number}...")
        details = await tracker.get_race_details(race.url)

        if details:
            data = format_race_for_analysis(details)
            data['url'] = race.url

            all_data.append(data)

            # Показываем краткую сводку
            runners_sorted = sorted(
                details.runners,
                key=lambda x: x.fixed_win if x.fixed_win > 0 else 999
            )

            print(f"  {details.race_name}")
            print(f"  Distance: {details.distance}")
            print(f"  Favorite: #{runners_sorted[0].number} {runners_sorted[0].name} @ ${runners_sorted[0].fixed_win}")
            print()

    # Сохраняем все данные
    with open("batch_races.json", "w") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)

    print(f"All race data saved to: batch_races.json")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--batch":
        asyncio.run(demo_batch_analysis())
    else:
        asyncio.run(main())
