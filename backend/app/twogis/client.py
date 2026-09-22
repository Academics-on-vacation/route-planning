from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import NamedTuple

import requests

from app.logging_config import configure_logging

logger = logging.getLogger(__name__)

KEY = os.environ.get("TWOGIS_API_KEY")

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
        "output": "summary",
    }
    if departure:
        body["utc"] = int(departure.timestamp())

    result = _post(ROUTING_URL, body).get("result") or []
    if not result:
        raise RuntimeError("2ГИС: маршрут на машине не построен")

    # Внимание: при output='summary' поля называются duration и length,
    # а total_duration и total_distance бывают только у 'detailed'.
    # Читать только total_* — значит молча получать нули.
    return Leg(round(result[0]["duration"] / 60), result[0]["length"] / 1000, result[0])


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


def _post(url: str, body: dict):
    resp = requests.post(url, params={"key": KEY}, json=body, timeout=15)
    if not resp.ok:
        # Текст ответа здесь — самое полезное, что есть: 2ГИС пишет
        # в нём, какое поле не понравилось.
        raise RuntimeError(f"2ГИС {resp.status_code}: {resp.text[:200]}")
    return resp.json()


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
