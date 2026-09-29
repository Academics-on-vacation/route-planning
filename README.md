# Route Planning

Прототип сервиса планирования маршрутов выездных инженеров для кейса «Билайн Бизнес».
Стек: Vue 3 + Vite, FastAPI, PostgreSQL.
Задание и тестовые данные находятся в `data/`.

## Настройки

Создайте `.env` в корне проекта из шаблона:

```sh
cp .env.example .env
```

| Переменная | Назначение |
| --- | --- |
| `POSTGRES_DB`, `POSTGRES_USER` | БД и пользователь; по умолчанию `route_planning` |
| `POSTGRES_PASSWORD` | Обязательный пароль БД |
| `YANDEX_GEOCODER_API_KEY` | Геокодирование адресов при импорте |
| `TWOGIS_API_KEY` | Маршруты 2ГИС |
| `VITE_API_URL` | Backend для прокси Vite; Compose задаёт `http://backend:8000` |

`make install` не создаёт `.env`. После изменения окружения контейнеров выполните
`make up`, чтобы применить настройки.

## Запуск в Docker

Требуются Docker с Compose plugin и Make. Все команды выполняются из корня проекта.

```sh
make up       # Сборка, запуск PostgreSQL, миграций, backend и frontend
make ps       # Состояние сервисов
make logs     # Логи
make down     # Остановка с сохранением данных БД
```

- Интерфейс: <http://localhost:5173>
- Проверка API и БД: <http://localhost:8000/api/health/db>

CSV загружаются через `POST /api/imports/csv` (Swagger).

`make migrate` запускает миграции отдельно. `make clean` удаляет контейнеры вместе с данными PostgreSQL.

## Проверки

```sh
make check    # Проверки backend, frontend и Compose
make test     # Тесты
make format   # Форматирование
```
