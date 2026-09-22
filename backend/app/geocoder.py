import asyncio
import logging

from sqlalchemy import select
from yandex_geocoder import Client, NothingFound, YandexGeocoderException

from app.config import settings
from app.db import session_factory
from app.logging_config import configure_logging
from app.orm.request import Request

logger = logging.getLogger(__name__)


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
                logger.warning(
                    f"Координаты не найдены: заявка #{request.id}, адрес {request.address}"
                )
                continue
            except YandexGeocoderException:
                logger.exception(f"Ошибка геокодирования заявки #{request.id}")
                continue

            request.lat = float(latitude)
            request.lon = float(longitude)
            await session.commit()
            logger.info(f"Заявка #{request.id} -> lat={request.lat} lon={request.lon}")

            await asyncio.sleep(0.5)


if __name__ == "__main__":
    configure_logging()
    asyncio.run(geocode_all_requests())
