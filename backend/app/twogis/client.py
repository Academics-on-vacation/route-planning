from __future__ import annotations

import logging
import os
import random
import time
from datetime import datetime
from typing import NamedTuple

import requests

from app.logging_config import configure_logging

logger = logging.getLogger(__name__)

# Ключи пачкой: лимит на один ключ маленький, а плеч в регионе под сотню.
# Клиент идёт по списку сверху вниз и переключается, когда текущий ключ
# перестаёт отвечать. Временная мера на время отладки — в проде ключ
# один и берётся из окружения.
KEYS = [
    "23d1bebb-3a48-4d01-89f6-a870cf7e4a2a",
    "8c7bfb89-6eb0-4adf-8d8b-06d4f945855c",
    "6bf28269-afd2-4afc-b2d6-d106196283ce",
    "d996a3e9-5ecf-4868-888b-aaad2feeab95",
    "924251c3-ff7b-4106-bd00-d20f6f0a61ad"
]

# Без списка работаем как раньше — по ключу из окружения.
KEY = os.environ.get("TWOGIS_API_KEY")
KEYS = KEYS or [k for k in (KEY,) if k]

# Каким ключом ходим сейчас. Переключение липкое: после ухода с мёртвого
# ключа остальные девяносто плеч идут уже по новому, а не долбятся
# в исчерпанный по четыре раза каждое.
_key_index = 0

TIMEOUT = 15

RETRIES = 3  # попыток ПОСЛЕ первой
BACKOFF_BASE = 0.8  # секунды до первого повтора
BACKOFF_CAP = 8.0  # потолок одной паузы

RETRY_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})

# Ключ не приняли: повторять с ним бессмысленно даже раз — сразу
# следующий. 429 сюда не входит: лимит может быть и посекундным,
# поэтому ему сперва дают отлежаться положенные попытки.
KEY_STATUS = frozenset({401, 403})

# Пауза между РЕАЛЬНЫМИ запросами: бесплатный тариф не любит очередь
# из сотни плеч подряд. Попадания в кэш её не ждут — троттлинг стоит
# после проверки кэша, а не перед.
MIN_INTERVAL = 3.0
_last_call = 0.0

ROUTING_URL = "https://routing.api.2gis.com/routing/7.0.0/global"
TRANSIT_URL = "https://routing.api.2gis.com/public_transport/2.0"

TRANSIT_MODES = [
    "pedestrian",
    "metro",
    "light_metro",
    "premetro",
    "monorail",
    "mcc",
    "mcd",
    "suburban_train",
    "tram",
    "bus",
    "trolleybus",
    "shuttle_bus",
]


class Leg(NamedTuple):
    minutes: int
    km: float
    raw: dict = {}


def car_route(origin, destination, departure: datetime | None = None) -> Leg:
    """
    Маршрут на автомобиле.
    """
    body = {
        "points": [
            {"type": "stop", "lat": origin[0], "lon": origin[1]},
            {"type": "stop", "lat": destination[0], "lon": destination[1]},
        ],
        "transport": "driving",
        "route_mode": "fastest",
        "traffic_mode": "statistics" if departure else "jam",
        "output": "detailed",
    }
    if departure:
        body["utc"] = int(departure.timestamp())

    result = _post(ROUTING_URL, body).get("result") or []
    if not result:
        raise RuntimeError("2ГИС: маршрут на машине не построен")

    route = result[0]
    seconds = route.get("total_duration", route.get("duration")) or 0
    meters = route.get("total_distance", route.get("length")) or 0
    return Leg(round(seconds / 60), meters / 1000, route)


def pedestrian_route(origin, destination, departure: datetime | None = None) -> Leg:
    """
    Маршрут пешком с общественным транспортом.
    """
    body = {
        "source": {"point": {"lat": origin[0], "lon": origin[1]}},
        "target": {"point": {"lat": destination[0], "lon": destination[1]}},
        "transport": TRANSIT_MODES,
    }
    if departure:
        body["start_time"] = int(departure.timestamp())  # тоже Unix-время

    variants = _post(TRANSIT_URL, body)
    if not variants:
        raise RuntimeError("2ГИС: маршрут на транспорте не построен")

    best = min(variants, key=lambda v: v["total_duration"])

    # print("Car route")
    # print(variants)
    # print()

    return Leg(round(best["total_duration"] / 60), best["total_distance"] / 1000, best)


def route(transport, origin, destination, departure: datetime | None = None, cache=None) -> Leg:
    """
    Плечо через 2ГИС — с проверкой кэша до запроса и записью после.

    Кэш живёт здесь, а не в солвере: солверу незачем знать, что ответы
    где-то лежат, ему нужны минуты и километры. Ключ кэша — транспорт,
    округлённые координаты и час выезда, поэтому проверка стоит тут,
    а не внутри `_post`: там уже только URL и тело запроса.
    """
    if cache is not None:
        hit = cache.get(transport, origin, destination, departure)
        if hit is not None:
            minutes, km = hit
            # Сырой ответ нужен геометрии маршрута; у старых строк кэша
            # он пустой, и нитка рисуется прямой.
            return Leg(minutes, km, cache.raw(transport, origin, destination, departure))

    _throttle()
    if cache is not None:
        cache.calls += 1

    mode = getattr(transport, "value", transport)
    fn = car_route if mode == "car" else pedestrian_route
    leg = fn(origin, destination, departure)

    if cache is not None:
        cache.put(transport, origin, destination, departure, leg.minutes, leg.km, leg.raw)
    return leg


def car_routes(pairs, departure: datetime | None = None) -> list[Leg | None]:
    """
    Много автомобильных плеч одним запросом (до 50 пар за раз).

    Это не украшательство: матрица 66×66 — это 4356 плеч. Поштучно —
    больше часа, пачками — полторы минуты. У пешеходной ручки такого
    режима нет, там только по одному.

    Ненайденное плечо возвращается как None и не роняет остальные.
    """
    out: list[Leg | None] = []
    for i in range(0, len(pairs), 50):
        chunk = pairs[i : i + 50]
        body = {
            "points": [
                [
                    {"type": "stop", "lat": a[0], "lon": a[1]},
                    {"type": "stop", "lat": b[0], "lon": b[1]},
                ]
                for a, b in chunk
            ],
            "transport": "driving",
            "route_mode": "fastest",
            "traffic_mode": "statistics" if departure else "jam",
            "output": "summary",
        }
        if departure:
            body["utc"] = int(departure.timestamp())

        # Пакетный ответ — плоский список в порядке запроса,
        # у каждого плеча свой status.
        for item in _post(body=body, url=ROUTING_URL):
            out.append(
                Leg(round(item["duration"] / 60), item["distance"] / 1000, item)
                if item.get("status") == "OK" and item.get("duration") is not None
                else None
            )
    return out


def _throttle() -> None:
    """Выдержать MIN_INTERVAL между запросами в 2ГИС."""
    global _last_call
    wait = MIN_INTERVAL - (time.monotonic() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.monotonic()


def _retry_after(resp) -> float | None:
    value = resp.headers.get("Retry-After")
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None


def _pause(attempt: int, asked: float | None) -> float:
    if asked is not None:
        return min(BACKOFF_CAP, asked)
    delay = min(BACKOFF_CAP, BACKOFF_BASE * 2**attempt)
    return delay * (0.5 + random.random() / 2)


def _rotate(used: int) -> bool:
    """Перейти на следующий ключ. False — ключи кончились.

    Сверяемся с `used`: если параллельный запрос уже переключил ключ,
    второй раз крутить не надо, иначе на двух потоках мы перепрыгнем
    через живой ключ.
    """
    global _key_index
    if not KEYS:
        return False
    if _key_index == used:
        _key_index = (used + 1) % len(KEYS)
    return True


def _post(url: str, body: dict):
    """POST с повторами и сменой ключа.

    Порядок такой: четыре попытки текущим ключом с нарастающей паузой,
    не вышло — берём следующий ключ и начинаем счёт заново. Обошли все
    ключи — отдаём наружу ошибку последней попытки, и вызывающий код
    откатывается к оценке по прямой.
    """
    last: Exception | None = None
    tried_keys = 0

    while tried_keys < max(1, len(KEYS)):
        used = _key_index
        key = KEYS[used] if KEYS else None
        tried_keys += 1
        switch = False

        for attempt in range(RETRIES + 1):
            asked = None
            try:
                resp = requests.post(url, params={"key": key}, json=body, timeout=TIMEOUT)
            except requests.RequestException as e:
                last = RuntimeError(f"2ГИС недоступен: {type(e).__name__}")
            else:
                if resp.ok:
                    try:
                        return resp.json()
                    except ValueError:
                        last = RuntimeError("2ГИС: ответ не разобрался как JSON")
                else:
                    last = RuntimeError(f"2ГИС {resp.status_code}: {resp.text[:200]}")
                    if resp.status_code in KEY_STATUS:
                        # Ключ отвергли — ждать нечего, меняем немедленно.
                        switch = True
                        break
                    if resp.status_code not in RETRY_STATUS:
                        raise last
                    asked = _retry_after(resp)

            if attempt == RETRIES:
                switch = True
                break

            pause = _pause(attempt, asked)
            logger.warning(
                "2ГИС[ключ %d]: попытка %d из %d не удалась (%s), повтор через %.1f с",
                used + 1,
                attempt + 1,
                RETRIES + 1,
                last,
                pause,
            )
            time.sleep(pause)

        if not switch or not _rotate(used):
            break

        logger.warning(
            "2ГИС: ключ %d из %d не отвечает (%s), переключаюсь на %d",
            used + 1,
            len(KEYS),
            last,
            _key_index + 1,
        )

    logger.error("2ГИС: ключи кончились, последняя ошибка: %s", last)
    raise last


if __name__ == "__main__":
    configure_logging()
    # python twogis.py — проверить, что ключ работает и время влияет
    office = (55.702267, 37.773852)
    client = (55.740094, 37.657031)
    day = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)

    for hour in (9, 15, 23):
        when = day.replace(hour=hour)
        logger.info(f"{hour:02d}:00 машина: {car_route(office, client, when)}")
    logger.info(f"транспорт: {pedestrian_route(office, client, day)}")
