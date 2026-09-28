"""Кеш провайдера 2ГИС в route_cache с отдельной транзакцией записи."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Literal, cast

from sqlalchemy import Table, and_, create_engine, func, or_, select
from sqlalchemy.dialects.postgresql import insert

from app.orm.route_cache import RouteCache

table = cast(Table, RouteCache.__table__)
MARKER = "_route_cache"
PRECISION = 5

RouteProfile = Literal["car", "transit"]
RouteMode = Literal["scheduled", "live"]
Coordinates = tuple[float, float]  # Широта, долгота.


@dataclass(frozen=True)
class RouteCacheKey:
    transport_profile: RouteProfile
    origin_latitude: float
    origin_longitude: float
    destination_latitude: float
    destination_longitude: float
    departure_hour: datetime


@dataclass(frozen=True)
class CachedRoute:
    travel_minutes: int
    distance_km: float
    payload: dict


def hour_bucket(when: datetime) -> datetime:
    base = when.replace(minute=0, second=0, microsecond=0)
    return base + timedelta(hours=1) if when.minute >= 30 else base


def make_cache_key(
    transport_profile: RouteProfile,
    origin: Coordinates,
    destination: Coordinates,
    departure: datetime,
) -> RouteCacheKey:
    """Единая нормализация координат и часа для чтения и записи кеша."""
    return RouteCacheKey(
        transport_profile=transport_profile,
        origin_latitude=round(origin[0], PRECISION),
        origin_longitude=round(origin[1], PRECISION),
        destination_latitude=round(destination[0], PRECISION),
        destination_longitude=round(destination[1], PRECISION),
        departure_hour=hour_bucket(departure),
    )


@lru_cache(maxsize=1)
def get_engine():
    # Ленивое создание: импорт клиента сам по себе не требует настроек/соединения БД.
    from app.config import settings

    return create_engine(
        settings.database_url.set(drivername="postgresql+psycopg"), pool_pre_ping=True
    )


def read(key: RouteCacheKey, *, detailed: bool, mode: RouteMode) -> CachedRoute | None:
    statement = select(table).where(
        table.c.transport == key.transport_profile,
        table.c.from_lat == key.origin_latitude,
        table.c.from_lon == key.origin_longitude,
        table.c.to_lat == key.destination_latitude,
        table.c.to_lon == key.destination_longitude,
        table.c.departure_at == key.departure_hour,
    )
    with get_engine().connect() as connection:
        row = connection.execute(statement).mappings().first()
    if row is None:
        return None
    payload = dict(row["payload"] or {})
    metadata = payload.pop(MARKER, {})
    # Старый кеш расчётов содержал raw-ответ без служебной обёртки.
    if metadata.get("mode", "scheduled") != mode:
        return None
    has_details = metadata.get(
        "detailed", any(field in payload for field in ("maneuvers", "movements", "total_duration"))
    )
    if detailed and not has_details:
        return None
    return CachedRoute(travel_minutes=row["minutes"], distance_km=row["km"], payload=payload)


def write(key: RouteCacheKey, route: CachedRoute, *, detailed: bool, mode: RouteMode) -> None:
    payload = {**route.payload, MARKER: {"detailed": detailed, "mode": mode}}
    statement = insert(table).values(
        transport=key.transport_profile,
        from_lat=key.origin_latitude,
        from_lon=key.origin_longitude,
        to_lat=key.destination_latitude,
        to_lon=key.destination_longitude,
        departure_at=key.departure_hour,
        minutes=route.travel_minutes,
        km=route.distance_km,
        payload=payload,
    )
    # Краткий пакетный ответ не должен затирать ранее полученную геометрию.
    protected = table.c.payload.contains({MARKER: {"detailed": True, "mode": mode}})
    if mode == "scheduled":
        protected = or_(
            protected,
            and_(
                ~table.c.payload.has_key(MARKER),
                or_(
                    *(
                        table.c.payload.has_key(field)
                        for field in ("maneuvers", "movements", "total_duration")
                    )
                ),
            ),
        )
    statement = statement.on_conflict_do_update(
        constraint="uq_route_cache_leg",
        set_={
            "minutes": statement.excluded.minutes,
            "km": statement.excluded.km,
            "payload": statement.excluded.payload,
            "created_at": func.now(),
        },
        where=None if detailed else ~protected,
    )
    # COMMIT до возврата из функции: запись переживёт ошибку/отмену планирования.
    with get_engine().begin() as connection:
        connection.execute(statement)
