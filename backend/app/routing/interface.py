from abc import ABC, abstractmethod

from app.models.domain import Point, TransportType


class RoutingProvider(ABC):
    """Общий контракт дороги; не зависит от HTTP, кеша или конкретного сервиса."""

    @abstractmethod
    def get_leg(
        self, origin: Point, destination: Point, transport: TransportType, departure_minutes: int
    ) -> tuple[int, float]:
        """Время переезда в минутах и расстояние в километрах."""
        raise NotImplementedError

    @abstractmethod
    def get_geometry(
        self, origin: Point, destination: Point, transport: TransportType, departure_minutes: int
    ) -> list[list[float]]:
        """Линия переезда: точки в порядке [широта, долгота]."""
        raise NotImplementedError

    @property
    def diagnostics(self) -> dict:
        """Необязательная диагностика провайдера для сервисного слоя."""
        return {}
