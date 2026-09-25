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

KEY = os.environ.get("TWOGIS_API_KEY")

TIMEOUT = 15

RETRIES = 3  # попыток ПОСЛЕ первой
BACKOFF_BASE = 0.8  # секунды до первого повтора
BACKOFF_CAP = 8.0  # потолок одной паузы

RETRY_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})

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

    print("Car route")
    print(variants)
    print()

    return Leg(round(best["total_duration"] / 60), best["total_distance"] / 1000, best)


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


def _post(url: str, body: dict):
    """POST с повторами. Наружу отдаёт либо разобранный ответ, либо
    RuntimeError последней попытки — вызывающий код на исключении
    откатывается к оценке по прямой."""
    last: Exception | None = None

    for attempt in range(RETRIES + 1):
        asked = None
        try:
            resp = requests.post(url, params={"key": KEY}, json=body, timeout=TIMEOUT)
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
                if resp.status_code not in RETRY_STATUS:
                    raise last
                asked = _retry_after(resp)

        if attempt == RETRIES:
            break

        pause = _pause(attempt, asked)
        logger.warning(
            "2ГИС: попытка %d из %d не удалась (%s), повтор через %.1f с",
            attempt + 1,
            RETRIES + 1,
            last,
            pause,
        )
        time.sleep(pause)

    logger.error("2ГИС: %d попыток подряд без ответа (%s)", RETRIES + 1, last)
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
