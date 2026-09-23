import asyncio
import logging
from collections.abc import Awaitable, Callable

import requests
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool
from yandex_geocoder import Client, NothingFound, YandexGeocoderException

from app.logging_config import configure_logging

logger = logging.getLogger(__name__)


class Coordinates(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class GeocodingError(ValueError):
    """Geocoding failure without provider URLs, API keys or raw responses."""


CoordinateResolver = Callable[[str], Awaitable[Coordinates]]


async def geocode_address(address: str, api_key: str | None) -> Coordinates:
    """Use the existing Yandex client without blocking the application's event loop."""
    if not api_key:
        raise GeocodingError("Для геокодирования требуется YANDEX_GEOCODER_API_KEY")
    client = Client(api_key)
    try:
        longitude, latitude = await run_in_threadpool(client.coordinates, address)
        point = Coordinates(lat=float(latitude), lon=float(longitude))
    except NothingFound:
        raise GeocodingError("Геокодер не нашёл адрес; передайте coordinates вручную") from None
    except (
        YandexGeocoderException,
        requests.RequestException,
        KeyError,
        IndexError,
        TypeError,
        ValueError,
        ArithmeticError,
    ):
        raise GeocodingError(
            "Не удалось геокодировать адрес; проверьте ключ или coordinates"
        ) from None
    await asyncio.sleep(0.5)
    return point


def yandex_resolver(api_key: str | None) -> CoordinateResolver:
    async def resolve(address: str) -> Coordinates:
        return await geocode_address(address, api_key)

    return resolve


async def geocode_all_requests() -> None:
    from app.config import settings
    from app.db import session_factory
    from app.orm.engineer import Engineer  # noqa: F401
    from app.orm.region import Region  # noqa: F401
    from app.orm.request import Request

    if not settings.yandex_geocoder_api_key:
        raise RuntimeError("YANDEX_GEOCODER_API_KEY is not set")

    async with session_factory() as session:
        rows = (await session.scalars(select(Request))).all()

        for request in rows:
            try:
                point = await geocode_address(request.address, settings.yandex_geocoder_api_key)
            except GeocodingError as exc:
                logger.warning("Ошибка геокодирования заявки #%s: %s", request.id, exc)
                continue

            request.lat = point.lat
            request.lon = point.lon
            await session.commit()
            logger.info(f"Заявка #{request.id} -> lat={request.lat} lon={request.lon}")


if __name__ == "__main__":
    configure_logging()
    asyncio.run(geocode_all_requests())
