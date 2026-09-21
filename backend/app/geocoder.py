import asyncio
import logging

from sqlalchemy import select
from yandex_geocoder import Client, NothingFound, YandexGeocoderException

from app.config import settings
from app.db import session_factory

from app.orm import Request


async def geocode_all_requests() -> None:
    if not settings.yandex_geocoder_api_key:
        raise RuntimeError("YANDEX_GEOCODER_API_KEY is not set")

    client = Client(settings.yandex_geocoder_api_key)

    async with session_factory() as session:
        requests = (await session.scalars(select(Request))).all()

        for request in requests:
            try:
                longitude, latitude = client.coordinates(request.address)
            except NothingFound:
                print(f"Координаты не найдены: заявка #{ request.id}, адрес {request.address}")
                continue
            except YandexGeocoderException as error:
                print(f"Ошибка геокодирования заявки #{request.id}: {error}")
                continue

            request.lat = float(latitude)
            request.lon = float(longitude)
            await session.commit()
            print(f"Заявка #{request.id} -> lat={request.lat} lon={request.lon}")

            await asyncio.sleep(0.5)


if __name__ == "__main__":
    asyncio.run(geocode_all_requests())
