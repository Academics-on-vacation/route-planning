import logging
from datetime import date, datetime, time, timedelta

from app.models.domain import Point, TransportType
from app.routing.estimated import OVERHEAD_MIN
from app.routing.interface import RoutingProvider
from app.routing.twogis import client
from app.routing.twogis.geometry import leg_points

logger = logging.getLogger(__name__)


class TwoGisProvider(RoutingProvider):
    """Адаптер клиента 2ГИС. Чтение и немедленная запись кеша остаются в клиенте."""

    def __init__(
        self,
        work_date: date,
        fallback_provider: RoutingProvider,
        *,
        allow_network: bool = True,
    ):
        self._day = datetime.combine(work_date, time.min)
        self._fallback_provider = fallback_provider
        self._allow_network = allow_network
        self._api_calls = 0
        self._cache_hits = 0
        self._cache_saved = 0

    @property
    def diagnostics(self) -> dict:
        return {
            "provider": "2gis" if self._allow_network else "haversine",
            "api_calls": self._api_calls,
            "cache_hits": self._cache_hits,
            "cache_saved": self._cache_saved,
        }

    def _fetch(
        self,
        origin: Point,
        destination: Point,
        transport: TransportType,
        departure_minutes: int,
        *,
        require_geometry: bool = False,
    ) -> client.Leg | None:
        request = client.car_route if transport == TransportType.CAR else client.pedestrian_route
        departure = self._day + timedelta(minutes=departure_minutes)
        try:
            leg = request(
                origin.coords,
                destination.coords,
                departure,
                allow_network=self._allow_network,
                require_geometry=require_geometry,
            )
        except Exception:
            logger.warning("Не удалось получить маршрут 2ГИС, используется оценка", exc_info=True)
            return None
        if leg is not None:
            if leg.from_cache:
                self._cache_hits += 1
            else:
                self._api_calls += 1
                self._cache_saved += 1
        return leg

    def get_leg(
        self, origin: Point, destination: Point, transport: TransportType, departure_minutes: int
    ) -> tuple[int, float]:
        leg = self._fetch(origin, destination, transport, departure_minutes)
        if leg is not None:
            return leg.minutes + OVERHEAD_MIN, round(leg.km, 2)
        return self._fallback_provider.get_leg(origin, destination, transport, departure_minutes)

    def get_geometry(
        self, origin: Point, destination: Point, transport: TransportType, departure_minutes: int
    ) -> list[list[float]]:
        leg = self._fetch(origin, destination, transport, departure_minutes, require_geometry=True)
        points = leg_points(leg.raw if leg is not None else {})
        return points or self._fallback_provider.get_geometry(
            origin, destination, transport, departure_minutes
        )
