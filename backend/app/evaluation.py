"""Метрики и сравнение допустимых планов, независимо от солвера и HTTP."""

from dataclasses import dataclass, fields
from decimal import Decimal
from math import isfinite
from typing import Literal

from app.models.domain import Engeneer, Plan, Stop, Ticket
from app.validation import validate_plan

# Текущее правило интерфейса: аварии из CSV (0) и диалога (10) — срочные.
URGENT_PRIORITY_MAX = 10


@dataclass(frozen=True)
class CostWeights:
    """Вес единицы: заявка, инженер, километр, минута ожидания соответственно."""

    per_unassigned_request: float = 10000
    per_used_engineer: float = 2000
    per_travel_km: float = 15
    per_waiting_minute: float = 3

    def __post_init__(self):
        for field in fields(self):
            value = getattr(self, field.name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or value < 0
            ):
                raise ValueError(f"Вес {field.name} должен быть конечным неотрицательным числом")


@dataclass(frozen=True)
class WeightedPlanCost:
    """Слагаемые численной стоимости в условных единицах; меньше — лучше."""

    unassigned_requests_cost: Decimal
    used_engineers_cost: Decimal
    travel_distance_cost: Decimal
    waiting_time_cost: Decimal

    @property
    def total(self) -> Decimal:
        return (
            self.unassigned_requests_cost
            + self.used_engineers_cost
            + self.travel_distance_cost
            + self.waiting_time_cost
        )


@dataclass(frozen=True, order=True)
class PlanScore:
    """Лексикографическая оценка: меньше — лучше. Порядок полей значим.

    Использовать только для одного набора заявок/инженеров и одной модели дороги.
    """

    unassigned_urgent_requests_count: int
    unassigned_requests_count: int
    used_engineers_count: int
    total_travel_distance_km: Decimal


@dataclass(frozen=True)
class RouteMetrics:
    engineer_id: int
    assigned_requests_count: int
    travel_distance_km: Decimal
    travel_minutes: float
    service_minutes: float
    waiting_minutes: float


@dataclass(frozen=True)
class PlanMetrics:
    total_requests_count: int
    assigned_requests_count: int
    unassigned_requests_count: int
    total_urgent_requests_count: int
    assigned_urgent_requests_count: int
    unassigned_urgent_requests_count: int
    used_engineers_count: int
    total_travel_distance_km: Decimal
    total_travel_minutes: float
    total_service_minutes: float
    total_waiting_minutes: float
    routes: tuple[RouteMetrics, ...]

    @property
    def score(self) -> PlanScore:
        return PlanScore(
            unassigned_urgent_requests_count=self.unassigned_urgent_requests_count,
            unassigned_requests_count=self.unassigned_requests_count,
            used_engineers_count=self.used_engineers_count,
            total_travel_distance_km=self.total_travel_distance_km,
        )

    @property
    def cost(self) -> Decimal:
        """Дополнительная численная стоимость с весами по умолчанию."""
        return self.weighted_cost().total

    def weighted_cost(self, weights: CostWeights = CostWeights()) -> WeightedPlanCost:
        """Взвешенная сумма, допускающая обмены между критериями.

        Срочные входят в общее число неназначенных без дополнительного штрафа.
        Простой — ожидание начала визитов, а не незанятый остаток смены.
        Для сопоставления стоимостей нужно использовать одинаковые веса.
        """
        return WeightedPlanCost(
            unassigned_requests_cost=Decimal(str(weights.per_unassigned_request))
            * self.unassigned_requests_count,
            used_engineers_cost=Decimal(str(weights.per_used_engineer)) * self.used_engineers_count,
            travel_distance_cost=Decimal(str(weights.per_travel_km))
            * self.total_travel_distance_km,
            waiting_time_cost=Decimal(str(weights.per_waiting_minute))
            * Decimal(str(self.total_waiting_minutes)),
        )


@dataclass(frozen=True)
class PlanComparison:
    left: PlanMetrics
    right: PlanMetrics

    @property
    def winner(self) -> Literal["left", "right", "tie"]:
        if self.left.score < self.right.score:
            return "left"
        if self.right.score < self.left.score:
            return "right"
        return "tie"

    @property
    def deciding_criterion(self) -> str | None:
        """Первый различающийся критерий; None означает равное качество."""
        left, right = self.left.score, self.right.score
        return next(
            (
                field.name
                for field in fields(PlanScore)
                if getattr(left, field.name) != getattr(right, field.name)
            ),
            None,
        )


def evaluate_plan(
    plan: Plan,
    tickets: list[Ticket],
    engineers: list[Engeneer],
    *,
    frozen: dict[int, list[Stop]] | None = None,
    not_before: int | None = None,
) -> PlanMetrics:
    """Валидирует план и возвращает метрики; некорректный план не получает оценку.

    Данные срочности и длительности берутся из исходных заявок. Расстояния —
    из плеч плана, включая первое плечо от старта, без добавления возврата.
    Decimal(str(km)) исключает артефакты двоичного суммирования и не округляет
    расстояние до точности отображения. HTTP-сериализация — задача вызывающего слоя.
    """
    validate_plan(plan, tickets, engineers, frozen=frozen, not_before=not_before).raise_if_invalid()
    tickets_by_id = {ticket.id: ticket for ticket in tickets}
    urgent_request_ids = {ticket.id for ticket in tickets if ticket.priority <= URGENT_PRIORITY_MAX}
    unassigned_request_ids = {item.ticket.id for item in plan.unassigned}
    route_metrics = tuple(
        RouteMetrics(
            engineer_id=route.engeneer.id,
            assigned_requests_count=len(route.stops),
            travel_distance_km=sum(
                (Decimal(str(stop.travel_km)) for stop in route.stops), Decimal(0)
            ),
            travel_minutes=sum(stop.travel_minutes for stop in route.stops),
            service_minutes=sum(
                tickets_by_id[stop.ticket.id].duration_minutes for stop in route.stops
            ),
            waiting_minutes=sum(stop.start - stop.arrive for stop in route.stops),
        )
        for route in sorted(plan.routes, key=lambda route: route.engeneer.id)
        if route.stops
    )
    unassigned_urgent_requests_count = len(urgent_request_ids & unassigned_request_ids)
    return PlanMetrics(
        total_requests_count=len(tickets),
        assigned_requests_count=len(tickets) - len(unassigned_request_ids),
        unassigned_requests_count=len(unassigned_request_ids),
        total_urgent_requests_count=len(urgent_request_ids),
        assigned_urgent_requests_count=len(urgent_request_ids) - unassigned_urgent_requests_count,
        unassigned_urgent_requests_count=unassigned_urgent_requests_count,
        used_engineers_count=len(route_metrics),
        total_travel_distance_km=sum(
            (route.travel_distance_km for route in route_metrics), Decimal(0)
        ),
        total_travel_minutes=sum(route.travel_minutes for route in route_metrics),
        total_service_minutes=sum(route.service_minutes for route in route_metrics),
        total_waiting_minutes=sum(route.waiting_minutes for route in route_metrics),
        routes=route_metrics,
    )


def compare_plans(
    left: Plan,
    right: Plan,
    tickets: list[Ticket],
    engineers: list[Engeneer],
    *,
    frozen: dict[int, list[Stop]] | None = None,
    not_before: int | None = None,
) -> PlanComparison:
    """Сравнивает два допустимых плана на одних входных данных и ограничениях.

    Модель времени/расстояний у обоих планов должна совпадать; эта функция
    не обращается к дорожному провайдеру и не читает plan.meta.
    """
    return PlanComparison(
        evaluate_plan(left, tickets, engineers, frozen=frozen, not_before=not_before),
        evaluate_plan(right, tickets, engineers, frozen=frozen, not_before=not_before),
    )
