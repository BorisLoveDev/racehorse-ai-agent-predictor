# API для получения данных о скачках

## Результат тестирования

### ❌ The Odds API
- **Не поддерживает скачки!**
- Покрывает 150 видов спорта, но НЕТ horse racing
- Есть: футбол, баскетбол, теннис, MMA и т.д.

### ✅ The Racing API (Рекомендуется)
- **Специализируется на скачках**
- UK, Irish и глобальные скачки
- Результаты, коэффициенты, форма лошадей
- Бесплатный тариф доступен

---

## Как получить доступ к The Racing API

### 1. Регистрация
Перейдите на: **https://www.theracingapi.com/**

### 2. Получите credentials
После регистрации вы получите:
- **Username**
- **Password**

### 3. Добавьте в `.env` файл
```bash
RACING_API_USERNAME=ваш_username
RACING_API_PASSWORD=ваш_password
```

### 4. Запустите тест
```bash
venv/bin/python test_racing_api.py
```

---

## Доступные эндпоинты

### Бесплатные результаты сегодня
```python
GET https://api.theracingapi.com/v1/results/today/free
Auth: Basic (username:password)
```

### Расписание скачек
```python
GET https://api.theracingapi.com/v1/racecards
Params:
  - start_date: YYYY-MM-DD
  - end_date: YYYY-MM-DD
  - limit: число (по умолчанию 25)
```

### Коэффициенты на лошадь
```python
GET https://api.theracingapi.com/v1/odds/{race_id}/{horse_id}
```

### Результаты по лошади
```python
GET https://api.theracingapi.com/v1/racecards/{horse_id}/results
```

---

## Альтернативные API (если нужны коэффициенты от букмекеров)

### OpticOdds
- Real-time стриминг коэффициентов
- Поддерживает скачки
- Платный доступ
- https://developer.opticodds.com/

### BetsAPI
- Множество спортов включая скачки
- Данные от Bet365, Betfair
- https://betsapi.com/

---

## Следующие шаги

1. Зарегистрируйтесь на The Racing API
2. Добавьте credentials в `.env`
3. Запустите `test_racing_api.py`
4. Создайте скрипты для вашей задачи

---

## Структура проекта

```
racehorse-agent/
├── .env                    # API ключи
├── venv/                   # Виртуальное окружение
├── test_odds_api.py        # Тест The Odds API (не поддерживает скачки)
├── test_racing_api.py      # Тест The Racing API ✅
├── check_all_sports.py     # Полный список спортов в Odds API
└── README_API.md           # Эта инструкция
```
