import asyncio
import logging
import os
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



GEOCODER_URL = os.environ.get("GEOCODER_URL", "https://geocode-maps.yandex.ru/1.x/")


class Suggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    subtitle: str = ""
    address: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


def _parse(payload: dict) -> list[Suggestion]:
    members = (
        payload.get("response", {})
        .get("GeoObjectCollection", {})
        .get("featureMember", [])
    )
    out: list[Suggestion] = []
    for member in members:
        obj = member.get("GeoObject") or {}
        pos = (obj.get("Point") or {}).get("pos")
        if not pos:
            continue
        try:
            lon, lat = (float(x) for x in pos.split())
        except ValueError:
            continue
        meta = (obj.get("metaDataProperty") or {}).get("GeocoderMetaData") or {}
        out.append(
            Suggestion(
                title=obj.get("name") or meta.get("text", ""),
                subtitle=obj.get("description", ""),
                address=meta.get("text", "") or obj.get("name", ""),
                lat=lat,
                lon=lon,
            )
        )
    return out


async def suggest_addresses(
    query: str, api_key: str | None, around: tuple[float, float] | None = None, limit: int = 5
) -> list[Suggestion]:
    query = (query or "").strip()
    if len(query) < 3:
        return []
    if not api_key:
        raise GeocodingError("Подсказки недоступны: не задан YANDEX_GEOCODER_API_KEY")

    params = {
        "apikey": api_key,
        "geocode": query,
        "format": "json",
        "results": limit,
        "lang": "ru_RU",
    }
    if around:
        lat, lon = around
        params["ll"] = f"{lon},{lat}"
        params["spn"] = "0.9,0.6"
        params["rspn"] = 0

    def fetch() -> dict:
        response = requests.get(GEOCODER_URL, params=params, timeout=8)
        response.raise_for_status()
        return response.json()

    try:
        payload = await run_in_threadpool(fetch)
    except (requests.RequestException, ValueError):
        raise GeocodingError("Геокодер не ответил") from None

    return _parse(payload)