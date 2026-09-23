"""Persistent cache owned by the synchronous 2GIS client.

Each operation uses its own short transaction; no connection is held during HTTP.
Departure times share a nearest-hour bucket; results are approximate estimates.
Versioned payloads distinguish this policy from previous cache formats.
"""

from datetime import UTC, datetime, timedelta
from functools import lru_cache

from sqlalchemy import create_engine, or_, select
from sqlalchemy.dialects.postgresql import insert

from app.orm.route_cache import RouteCache

CACHE_VERSION = 3


@lru_cache(maxsize=1)
def _engine():
    from app.config import settings

    return create_engine(
        settings.database_url.set(drivername="postgresql+psycopg"), pool_pre_ping=True
    )


def _key(transport, origin, destination, departure):
    if departure is None:
        # Live traffic/"leave now" responses cannot be reused indefinitely.
        return None
    when = datetime.fromtimestamp(departure.timestamp(), UTC)
    bucket = (when + timedelta(minutes=30)).replace(minute=0, second=0, microsecond=0, tzinfo=None)
    return {
        "transport": transport,
        "from_lat": origin[0],
        "from_lon": origin[1],
        "to_lat": destination[0],
        "to_lon": destination[1],
        # Round the cache key only; HTTP still uses the requested departure time.
        "departure_at": bucket,
    }


def get(transport, origin, destination, departure, *, detailed=True):
    key = _key(transport, origin, destination, departure)
    if key is None:
        return None
    table = RouteCache.__table__
    query = select(table).where(*(table.c[name] == value for name, value in key.items()))
    with _engine().connect() as connection:
        row = connection.execute(query).mappings().first()
    if row is None:
        return None
    payload = row["payload"] or {}
    if payload.get("cache_version") != CACHE_VERSION:
        return None
    if detailed and not payload.get("detailed"):
        return None
    return row["minutes"], row["km"], payload["raw"]


def put(transport, origin, destination, departure, leg, *, detailed=True):
    key = _key(transport, origin, destination, departure)
    if key is None:
        return
    statement = insert(RouteCache).values(
        **key,
        minutes=leg.minutes,
        km=leg.km,
        payload={"cache_version": CACHE_VERSION, "detailed": detailed, "raw": leg.raw},
    )
    statement = statement.on_conflict_do_update(
        constraint="uq_route_cache_leg",
        set_={
            "minutes": statement.excluded.minutes,
            "km": statement.excluded.km,
            "payload": statement.excluded.payload,
            "created_at": datetime.now(UTC).replace(tzinfo=None),
        },
        # A concurrent summary response must not overwrite route geometry.
        where=(
            None
            if detailed
            else or_(
                RouteCache.payload["cache_version"].as_integer().is_distinct_from(CACHE_VERSION),
                RouteCache.payload["detailed"].as_boolean().is_not(True),
            )
        ),
    )
    with _engine().begin() as connection:
        connection.execute(statement)
