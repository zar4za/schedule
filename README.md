# Планировщик расписания

Сервис для решения задачи составления расписания с использованием CP-SAT solver от Google OR-Tools.

## Особенности

- Чтение запросов из Redis Stream
- Решение задачи оптимизации с учетом множества ограничений
- Запись результатов обратно в Redis
- Обработка ошибок и dead-letter очередь
- Полностью настраиваемый через переменные окружения

## Переменные окружения

- `REDIS_HOST` (по умолчанию: localhost)
- `REDIS_PORT` (по умолчанию: 6379)
- `REQUESTS_STREAM` (по умолчанию: schedule:requests)
- `RESULTS_STREAM` (по умолчанию: schedule:results)
- `CONSUMER_GROUP` (по умолчанию: scheduler-group)
- `CONSUMER_NAME` (по умолчанию: автогенерируемый UUID)
- `SOLVE_TIME_LIMIT` (по умолчанию: 30 секунд)
- `CPUS` (по умолчанию: 4)
- `WEIGHT_UNDERCOVERAGE` (по умолчанию: 1000)
- `WEIGHT_DEVIATION` (по умолчанию: 5)
- `WEIGHT_PREFERENCE` (по умолчанию: 2)

## Запуск через Docker

1. Сборка образа:
```bash
docker build -t scheduler-service .
```

2. Запуск контейнера:
```bash
docker run -d \
  --name scheduler \
  -e REDIS_HOST=your-redis-host \
  -e REDIS_PORT=6379 \
  scheduler-service
```

## Формат входных данных

Запросы должны быть отправлены в Redis Stream `schedule:requests` в формате JSON:

```json
{
  "request_id": "<uuid>",
  "week_start": "YYYY-MM-DDTHH:MM:SS",
  "staff": [
    {
      "id": 1,
      "max_week_hours": 40,
      "max_night_hours": 16,
      "telegram_id": 12345
    }
  ],
  "unavailability": [
    {
      "staff_id": 1,
      "from": "YYYY-MM-DDTHH:MM:SS",
      "to": "YYYY-MM-DDTHH:MM:SS"
    }
  ],
  "shifts": [
    {
      "shift_id": "S1",
      "start": "YYYY-MM-DDTHH:MM:SS",
      "end": "YYYY-MM-DDTHH:MM:SS",
      "required_count": 2,
      "is_night": true,
      "preference": 1
    }
  ]
}
```

## Формат выходных данных

Результаты записываются в Redis Stream `schedule:results`:

```json
{
  "request_id": "<uuid>",
  "status": "success|partial|error",
  "assignments": [
    {
      "shift_id": "S1",
      "staff_id": 1
    }
  ],
  "metrics": {
    "objective": 123,
    "solve_time_s": 4.2
  }
}
```

## Обработка ошибок

В случае ошибок при обработке запроса, сообщение будет помещено в очередь `schedule:dead-letter` с информацией об ошибке и оригинальным сообщением. 