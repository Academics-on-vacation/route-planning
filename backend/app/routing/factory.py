from dataclasses import dataclass
from datetime import date

from app.routing.estimated import EstimatedProvider
from app.routing.interface import RoutingProvider
from app.routing.twogis.provider import TwoGisProvider


@dataclass(frozen=True)
class RoutingProviders:
    travel_provider: RoutingProvider
    estimate_provider: RoutingProvider


def create_routing(work_date: date, use_api: bool) -> RoutingProviders:
    estimate_provider = EstimatedProvider()
    # Отключение сети сохраняет чтение ранее рассчитанных маршрутов из БД.
    travel_provider = TwoGisProvider(work_date, estimate_provider, allow_network=use_api)
    return RoutingProviders(travel_provider=travel_provider, estimate_provider=estimate_provider)
