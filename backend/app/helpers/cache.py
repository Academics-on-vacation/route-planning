from __future__ import annotations

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

PRECISION = 5


def hour_bucket(when: datetime) -> datetime:
    base = when.replace(minute=0, second=0, microsecond=0)
    return base + timedelta(hours=1) if when.minute >= 30 else base


def leg_key(transport, origin, destination, when: datetime) -> tuple:
    return (
        getattr(transport, "value", transport),
        round(origin[0], PRECISION),
        round(origin[1], PRECISION),
        round(destination[0], PRECISION),
        round(destination[1], PRECISION),
        hour_bucket(when),
    )


class LegCache:
    def __init__(self, rows=()):
        self._legs: dict[tuple, tuple[int, float]] = {}
        # Ответы 2ГИС целиком: из них берётся нитка маршрута для карты.
        # Хранятся отдельно от (минуты, км), потому что нужны только
        # в самом конце и только у плеч итогового плана.
        self._raw: dict[tuple, dict] = {}
        self._pending: list[dict] = []
        self.hits = 0
        self.misses = 0

        for row in rows:
            key = leg_key(
                row.transport,
                (row.from_lat, row.from_lon),
                (row.to_lat, row.to_lon),
                row.departure_at,
            )
            self._legs[key] = (row.minutes, row.km)
            self._raw[key] = row.payload or {}

    def get(self, transport, origin, destination, when) -> tuple[int, float] | None:
        """Минуты и километры из кэша. None — надо спрашивать API."""
        if when is None:
            return None  # без времени выезда ключ неполный, кэш не применим
        found = self._legs.get(leg_key(transport, origin, destination, when))
        if found is None:
            self.misses += 1
            return None
        self.hits += 1
        return found

    def raw(self, transport, origin, destination, when) -> dict:
        """Ответ 2ГИС по этому плечу — как пришёл. Пусто, если плечо
        считалось оценкой или строка кэша старая, без геометрии."""
        if when is None:
            return {}
        return self._raw.get(leg_key(transport, origin, destination, when), {})

    def put(self, transport, origin, destination, when, minutes, km, payload) -> None:
        """Запомнить ответ API. Кладём его как есть, без накидок солвера"""

        logger.debug(f"Готовлю запись в КЭШ: {transport}, {origin}, {destination}, {when}")
        if when is None:
            return
        key = leg_key(transport, origin, destination, when)
        if key in self._legs:
            return
        self._legs[key] = (minutes, km)
        self._pending.append(
            {
                "transport": key[0],
                "from_lat": key[1],
                "from_lon": key[2],
                "to_lat": key[3],
                "to_lon": key[4],
                "departure_at": key[5],
                "minutes": minutes,
                "km": km,
                "payload": payload or {},
            }
        )

    @property
    def pending(self) -> list[dict]:
        """Строки, которых в базе ещё нет."""
        return self._pending
