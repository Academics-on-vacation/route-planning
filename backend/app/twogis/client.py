from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from functools import wraps
from random import uniform
from time import sleep
from typing import NamedTuple

import requests

from app.logging_config import configure_logging

from . import cache

logger = logging.getLogger(__name__)

KEY = os.environ.get("TWOGIS_API_KEY")

TIMEOUT = 15

ROUTING_URL = "https://routing.api.2gis.com/routing/7.0.0/global"
TRANSIT_URL = "https://routing.api.2gis.com/public_transport/2.0"

MAX_ATTEMPTS = 4
RETRY_STATUSES = {408, 425, 429, 500, 502, 503, 504}

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


def _cached(transport):
    def decorate(fn):
        @wraps(fn)
        def wrapped(origin, destination, departure=None):
            found = cache.get(transport, origin, destination, departure)
            if found is not None:
                return Leg(*found)
            leg = fn(origin, destination, departure)
            cache.put(transport, origin, destination, departure, leg)
            return leg

        return wrapped

    return decorate


@_cached("car")
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


@_cached("transit")
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

    return Leg(round(best["total_duration"] / 60), best["total_distance"] / 1000, best)


def car_routes(pairs, departure: datetime | None = None) -> list[Leg | None]:
    """
    Много автомобильных плеч одним запросом (до 50 пар за раз).

    Это не украшательство: матрица 66×66 — это 4356 плеч. Поштучно —
    больше часа, пачками — полторы минуты. У пешеходной ручки такого
    режима нет, там только по одному.

    Ненайденное плечо возвращается как None и не роняет остальные.
    """
    pairs = list(pairs)
    out: list[Leg | None] = [None] * len(pairs)
    missing = {}
    for index, (a, b) in enumerate(pairs):
        pair = (tuple(a), tuple(b))
        if pair in missing:
            missing[pair].append(index)
            continue
        found = cache.get("car", a, b, departure, detailed=False)
        if found is not None:
            out[index] = Leg(*found)
        else:
            missing[pair] = [index]

    pending = list(missing)
    for i in range(0, len(pending), 50):
        chunk = pending[i : i + 50]
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
        response = _post(body=body, url=ROUTING_URL)
        if len(response) != len(chunk):
            raise RuntimeError("2ГИС: неполный пакетный ответ")
        for (a, b), item in zip(chunk, response, strict=True):
            if item.get("status") != "OK" or item.get("duration") is None:
                continue
            leg = Leg(round(item["duration"] / 60), item["distance"] / 1000, item)
            cache.put("car", a, b, departure, leg, detailed=False)
            for index in missing[(a, b)]:
                out[index] = leg
    return out


def _retry_delay(attempt: int, retry_after: str | None = None) -> float:
    delay = 2**attempt + uniform(0, 1)
    if retry_after:
        try:
            seconds = int(retry_after)
        except ValueError:
            try:
                seconds = (parsedate_to_datetime(retry_after) - datetime.now(UTC)).total_seconds()
            except (TypeError, ValueError, OverflowError):
                return delay
        delay = max(delay, seconds)
    return delay


def _post(url: str, body: dict):
    for attempt in range(MAX_ATTEMPTS):
        retry_after = None
        try:
            resp = requests.post(url, params={"key": KEY}, json=body, timeout=TIMEOUT)
        except requests.RequestException:
            if attempt == MAX_ATTEMPTS - 1:
                raise
        else:
            try:
                if resp.ok:
                    try:
                        return resp.json()
                    except ValueError:
                        if attempt == MAX_ATTEMPTS - 1:
                            raise RuntimeError("2ГИС: ответ не разобрался как JSON") from None
                elif resp.status_code not in RETRY_STATUSES or attempt == MAX_ATTEMPTS - 1:
                    raise RuntimeError(f"2ГИС {resp.status_code}: {resp.text[:200]}")
                retry_after = resp.headers.get("Retry-After")
            finally:
                resp.close()

        delay = _retry_delay(attempt, retry_after)
        logger.warning("Повтор запроса 2ГИС: попытка %s, задержка %.2f с", attempt + 2, delay)
        sleep(delay)
    raise RuntimeError("2ГИС: исчерпаны попытки запроса")


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
