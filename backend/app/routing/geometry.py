"""Сборка геометрии плана через общий интерфейс дорожного провайдера."""

from app.models.domain import Plan
from app.routing.interface import RoutingProvider

MIN_STEP = 0.00002


def thin(points: list[list[float]]) -> list[list[float]]:
    out: list[list[float]] = []
    for point in points:
        if not out or abs(point[0] - out[-1][0]) + abs(point[1] - out[-1][1]) > MIN_STEP:
            out.append(point)
    return out


def build_geometries(plan: Plan, provider: RoutingProvider) -> dict[int, list[list[float]] | None]:
    geometries = {}
    for route in plan.used_routes:
        origin, points = route.engeneer.start_point, []
        for stop in route.stops:
            points += provider.get_geometry(
                origin, stop.ticket.point, route.engeneer.transport, stop.depart
            )
            origin = stop.ticket.point
        geometries[route.engeneer.id] = thin(points) or None
    return geometries
