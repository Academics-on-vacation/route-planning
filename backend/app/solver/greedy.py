import math
import time
from datetime import datetime

from ..helpers.estimator import estimate, OVERHEAD_MIN, REASONS
from ..models.domain import Engeneer, Plan, Point, Route, Stop, Ticket, TransportType, Unassigned
from .interface import Solver

"""
Жадный планировщик.

1. Сортируем заявки.
2. Для каждой ищем исполнителя ПО ПРЯМОЙ — быстро и бесплатно.
3. Выбранному считаем настоящее плечо через 2ГИС и проверяем ещё раз.

"""
class GreedySolver(Solver):

    def __init__(self, work_date: datetime | None = None, use_api: bool = False):
        super().__init__()
        self.work_date = work_date
        self.use_api = use_api
        self.api_calls = 0


    def get_name(self) -> str:
        return "GreedySolver"

    def solve(self, tickets: list[Ticket], engeneers: list[Engeneer]) -> Plan:
        started = time.monotonic()
        self.api_calls = 0

        # Состояние на время прогона: маршрут, где инженер сейчас и когда освободится.
        routes = {e.id: Route(e) for e in engeneers}
        position = {e.id: e.start_point for e in engeneers}
        free_at = {e.id: e.work_shift_start_minutes for e in engeneers}

        unassigned: list[Unassigned] = []
        order = sorted(
            tickets, key=lambda t: (t.work_start, t.priority, t.work_finish - t.work_start)
        )

        for ticket in order:
            reason = self._place(ticket, engeneers, routes, position, free_at)
            if reason:
                unassigned.append(Unassigned(ticket, reason, REASONS[reason]))

        print(f"Api calls: {self.api_calls}")
        return Plan(
            routes=list(routes.values()),
            unassigned=unassigned,
            meta={
                "solver": self.get_name(),
                "provider": "2gis" if self.use_api else "haversine",
                "api_calls": self.api_calls,
                "runtime_ms": int((time.monotonic() - started) * 1000),
            },
        )


    def _place(self, ticket, engeneers, routes, position, free_at) -> str | None:
        """Пристроить заявку. Возвращает код причины, если не вышло."""
        rejected: set[str] = set()
        candidates = []

        for eng in engeneers:
            if not eng.skills.has(ticket.skill):
                rejected.add("skill")
                continue
            if (
                ticket.required_transport == TransportType.CAR
                and eng.transport != TransportType.CAR
            ):
                rejected.add("transport")
                continue

            minutes, km = estimate(position[eng.id], ticket.point, eng.transport, free_at[eng.id])
            fit = self._fit(ticket, eng, free_at[eng.id], minutes)
            if fit is None:
                rejected.add("capacity")
                continue

            wait = fit[1] - (free_at[eng.id] + minutes)
            candidates.append((minutes + wait, km, eng))

        if not candidates:
            for code in ("skill", "transport", "capacity"):
                if code in rejected:
                    return code
            return "capacity"

        candidates.sort(key=lambda c: (c[0], c[1]))
        # Шаг 3: подтверждаем настоящей дорогой.
        print()
        print("Candidtaed:")
        for _score, _km, eng in candidates[:3]:
            depart = free_at[eng.id]
            minutes, km = self._road(position[eng.id], ticket.point, eng.transport, depart)
            print(f"Eng: {eng.name}, Minutes: {minutes}, KM: {km}, (_km: {_km}, score: {_score})")
            fit = self._fit(ticket, eng, depart, minutes)
            if fit is None:
                continue

            arrive, start, end = fit
            routes[eng.id].stops.append(Stop(ticket, depart, arrive, start, end, minutes, km))
            position[eng.id] = ticket.point
            free_at[eng.id] = end
            return None

        return "window"

    @staticmethod
    def _fit(ticket, eng, depart: int, travel_minutes: int) -> tuple[int, int, int] | None:
        """Влезает ли заявка в конец маршрута: (приезд, начало, конец)."""
        arrive = depart + travel_minutes
        start = max(arrive, ticket.work_start)  # приехал рано — ждёт окна
        end = start + ticket.duration_minutes

        if start > ticket.work_finish:  # приехал после закрытия окна
            return None
        if end > eng.work_shift_end_minutes:  # не успевает до конца смены
            return None
        return arrive, start, end

    def _road(self, a: Point, b: Point, transport: TransportType, depart: int) -> tuple[int, float]:

        if not self.use_api:
            return estimate(a, b, transport, depart)

        from ..twogis.client import car_route, pedestrian_route

        when = None
        if self.work_date:
            when = self.work_date.replace(
                hour=min(23, depart // 60), minute=depart % 60, second=0, microsecond=0
            )
        try:
            self.api_calls += 1
            fn = car_route if transport == TransportType.CAR else pedestrian_route
            leg = fn(a.coords, b.coords, when)
            return leg.minutes + OVERHEAD_MIN, round(leg.km, 2)
        except Exception:
            return estimate(a, b, transport, depart)



