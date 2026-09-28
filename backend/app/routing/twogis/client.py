from __future__ import annotations

import logging
import os
import random
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from typing import NamedTuple

import requests

from app.logging_config import configure_logging
from app.routing.twogis import cache

logger = logging.getLogger(__name__)

LOCAL_KEYS: list[str] = [
    "9121801e-66c2-451b-a8dc-b3d6bb780795",
    "db573e6b-0eda-4ab0-a91e-717ccc1c8df8",
    "71ada5ad-f2a9-42e4-9ed2-2b1c36faa712",
    "dbe5d172-baa8-4f8d-8a0f-706d30ae2d9c",
    "ff653d2e-dfb6-4a55-8ce6-e1f4db340670",
    "23d1bebb-3a48-4d01-89f6-a870cf7e4a2a",
    "8c7bfb89-6eb0-4adf-8d8b-06d4f945855c",
    "6bf28269-afd2-4afc-b2d6-d106196283ce",
    "d996a3e9-5ecf-4868-888b-aaad2feeab95",
    "924251c3-ff7b-4106-bd00-d20f6f0a61ad",
]


def _load_keys() -> list[str]:
    found: list[str] = []
    for raw in (os.environ.get("TWOGIS_API_KEYS", ""), os.environ.get("TWOGIS_API_KEY", "")):
        found += [part for part in re.split(r"[\s,;]+", raw) if part]
    found += LOCAL_KEYS

    seen: set[str] = set()
    keys: list[str] = []
    for key in found:
        if key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


KEYS = _load_keys()
# Совместимость: старые скрипты и ручные проверки смотрят на client.KEY.
KEY = KEYS[0] if KEYS else None

# Каким ключом ходим сейчас. Переключение липкое: уйдя с мёртвого ключа,
# остальные плечи идут уже по новому, а не долбятся в исчерпанный
# по четыре раза каждое.
_key_index = 0

TIMEOUT = 5

RETRIES = 3  # попыток ПОСЛЕ первой одним ключом
BACKOFF_BASE = 0.8  # секунды до первого повтора
BACKOFF_CAP = 8.0  # потолок одной паузы

RETRY_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})

KEY_STATUS = frozenset({401})

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
    from_cache: bool = False


@dataclass
class _PendingRoute:
    origin: cache.Coordinates
    destination: cache.Coordinates
    result_indices: list[int]


def _context(departure: datetime | None) -> tuple[datetime, cache.RouteMode]:
    when = departure or datetime.now()
    if when.tzinfo is not None:
        when = when.astimezone(timezone.utc).replace(tzinfo=None)
    return when, "scheduled" if departure is not None else "live"


def _cached(key: cache.RouteCacheKey, *, detailed: bool, mode: cache.RouteMode) -> Leg | None:
    found = cache.read(key, detailed=detailed, mode=mode)
    if found is None:
        return None
    return Leg(
        minutes=found.travel_minutes, km=found.distance_km, raw=found.payload, from_cache=True
    )


def _leg(seconds, meters, raw) -> Leg:
    if not all(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(value)
        and value >= 0
        for value in (seconds, meters)
    ):
        raise RuntimeError("2ГИС: некорректные время или расстояние маршрута")
    return Leg(round(seconds / 60), meters / 1000, raw)


def _save(key: cache.RouteCacheKey, leg: Leg, *, detailed: bool, mode: cache.RouteMode) -> Leg:
    route = cache.CachedRoute(travel_minutes=leg.minutes, distance_km=leg.km, payload=leg.raw)
    cache.write(key, route, detailed=detailed, mode=mode)
    return leg


def car_route(
    origin: cache.Coordinates,
    destination: cache.Coordinates,
    departure: datetime | None = None,
    *,
    allow_network: bool = True,
    require_geometry: bool = True,
) -> Leg | None:
    """
    Маршрут на автомобиле.
    """
    when, mode = _context(departure)
    key = cache.make_cache_key("car", origin, destination, when)
    found = _cached(key, detailed=require_geometry, mode=mode)
    if found is not None or not allow_network:
        return found
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
    leg = _leg(
        route.get("total_duration", route.get("duration")),
        route.get("total_distance", route.get("length")),
        route,
    )
    return _save(key, leg, detailed=True, mode=mode)


def pedestrian_route(
    origin: cache.Coordinates,
    destination: cache.Coordinates,
    departure: datetime | None = None,
    *,
    allow_network: bool = True,
    require_geometry: bool = True,
) -> Leg | None:
    """
    Маршрут пешком с общественным транспортом.
    """
    when, mode = _context(departure)
    key = cache.make_cache_key("transit", origin, destination, when)
    found = _cached(key, detailed=require_geometry, mode=mode)
    if found is not None or not allow_network:
        return found
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

    return _save(
        key, _leg(best["total_duration"], best["total_distance"], best), detailed=True, mode=mode
    )


def car_routes(
    pairs: Iterable[tuple[cache.Coordinates, cache.Coordinates]],
    departure: datetime | None = None,
    *,
    allow_network: bool = True,
) -> list[Leg | None]:
    """
    Много автомобильных плеч одним запросом (до 50 пар за раз).

    Это не украшательство: матрица 66×66 — это 4356 плеч. Поштучно —
    больше часа, пачками — полторы минуты. У пешеходной ручки такого
    режима нет, там только по одному.

    Ненайденное плечо возвращается как None и не роняет остальные.
    """
    pairs = list(pairs)
    out: list[Leg | None] = [None] * len(pairs)
    when, mode = _context(departure)
    missing: dict[cache.RouteCacheKey, _PendingRoute] = {}
    for index, (origin, destination) in enumerate(pairs):
        key = cache.make_cache_key("car", origin, destination, when)
        if key in missing:
            missing[key].result_indices.append(index)
            continue
        found = _cached(key, detailed=False, mode=mode)
        if found is not None:
            out[index] = found
        elif allow_network:
            missing[key] = _PendingRoute(
                origin=origin, destination=destination, result_indices=[index]
            )

    keys = list(missing)
    for i in range(0, len(keys), 50):
        chunk = keys[i : i + 50]
        body = {
            "points": [
                [
                    {"type": "stop", "lat": missing[key].origin[0], "lon": missing[key].origin[1]},
                    {
                        "type": "stop",
                        "lat": missing[key].destination[0],
                        "lon": missing[key].destination[1],
                    },
                ]
                for key in chunk
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
        items = _post(body=body, url=ROUTING_URL)
        for key, item in zip(chunk, items):
            if item.get("status") != "OK":
                continue
            try:
                leg = _leg(item.get("duration"), item.get("distance"), item)
            except RuntimeError:
                continue
            _save(key, leg, detailed=False, mode=mode)
            for index in missing[key].result_indices:
                out[index] = leg
        if len(items) != len(chunk):
            raise RuntimeError("2ГИС: число ответов не совпадает с числом запрошенных маршрутов")
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


def _rotate(used: int) -> bool:
    """Перейти на следующий ключ. False — ключей вообще нет.

    Сверяемся с `used`: если параллельный вызов уже переключил ключ,
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

    Порядок такой: четыре попытки текущим ключом с нарастающей паузой;
    не вышло — берём следующий ключ и начинаем счёт заново. Обошли все
    ключи — отдаём наружу ошибку последней попытки, и вызывающий код
    откатывается к оценке по прямой.

    Ошибка, которую повторять бессмысленно (400, 404 и прочее, чего нет
    в RETRY_STATUS), по-прежнему летит наружу сразу: перебирать из-за
    неё ключи незачем, дело не в них.
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
                "2ГИС[ключ %d из %d]: попытка %d из %d не удалась (%s), повтор через %.1f с",
                used + 1,
                len(KEYS) or 1,
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

    logger.error("2ГИС: ключи кончились (%d шт.), последняя ошибка: %s", len(KEYS) or 1, last)
    assert last is not None
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
