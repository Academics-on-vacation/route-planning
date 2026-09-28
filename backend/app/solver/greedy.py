"""Жадное назначение и локальное улучшение, без HTTP, кеша и сериализации."""

import logging

from app.models.domain import Engeneer, Plan, Route, Stop, Ticket, TransportType, Unassigned
from app.routing.interface import RoutingProvider
from app.solver.improve import improve
from app.solver.improve import schedule as replay
from app.solver.interface import Solver

logger = logging.getLogger(__name__)

MAX_LEG_MIN = 90
REASONS = {
    "skill": "Нет свободного исполнителя с нужным навыком",
    "transport": "Нужен другой транспорт",
    "capacity": "Все подходящие исполнители заняты в это окно",
    "distance": "Слишком далеко: переезд длиннее допустимого",
    "window": "По реальной дороге заявка не успевает в окно",
}


class GreedySolver(Solver):
    def __init__(
        self,
        travel_provider: RoutingProvider,
        estimate_provider: RoutingProvider,
        max_leg_min: int = MAX_LEG_MIN,
        polish: bool = True,
    ):
        self.travel_provider = travel_provider
        self.estimate_provider = estimate_provider
        self.max_leg_min = max_leg_min
        self.polish = polish

    def solve(self, tickets: list[Ticket], engineers: list[Engeneer]) -> Plan:
        routes = {e.id: Route(e) for e in engineers}
        position = {e.id: e.start_point for e in engineers}
        free_at = {e.id: e.work_shift_start_minutes for e in engineers}
        unassigned: list[Unassigned] = []
        order = sorted(
            tickets, key=lambda t: (t.work_start, t.priority, t.work_finish - t.work_start)
        )
        for ticket in order:
            reason = self._place(ticket, engineers, routes, position, free_at)
            if reason:
                unassigned.append(Unassigned(ticket, reason, REASONS[reason]))

        if self.polish:
            routes, unassigned = self._polish(routes, unassigned, engineers)
        return Plan(list(routes.values()), unassigned)

    def _polish(self, routes, unassigned, engineers):
        order = {e.id: [s.ticket for s in routes[e.id].stops] for e in engineers}
        reasons_by_ticket_id = {u.ticket.id: (u.reason, u.reason_text) for u in unassigned}
        order, dropped, _ = improve(
            order,
            [u.ticket for u in unassigned],
            engineers,
            self.estimate_provider.get_leg,
            self.max_leg_min,
        )
        for eng in engineers:
            got = replay(eng, order[eng.id], self.travel_provider.get_leg)
            if got is None:
                got = replay(eng, order[eng.id], self.estimate_provider.get_leg)
            if got is None:
                logger.warning("Маршрут %s не проигрался, заявки в отказ", eng.id)
                dropped += order[eng.id]
                got = ([], 0.0)
            routes[eng.id].stops = got[0]

        default_reason = ("window", REASONS["window"])
        remaining_unassigned = []
        for ticket in dropped:
            reason, reason_text = reasons_by_ticket_id.get(ticket.id, default_reason)
            remaining_unassigned.append(
                Unassigned(ticket=ticket, reason=reason, reason_text=reason_text)
            )

        return routes, remaining_unassigned

    def _place(self, ticket, engineers, routes, position, free_at) -> str | None:
        rejected: set[str] = set()
        candidates = []
        for eng in engineers:
            if not eng.skills.has(ticket.skill):
                rejected.add("skill")
                continue
            if (
                ticket.required_transport == TransportType.CAR
                and eng.transport != TransportType.CAR
            ):
                rejected.add("transport")
                continue
            minutes, km = self.estimate_provider.get_leg(
                position[eng.id], ticket.point, eng.transport, free_at[eng.id]
            )
            if minutes > self.max_leg_min:
                rejected.add("distance")
                continue
            fit = self._fit(ticket, eng, free_at[eng.id], minutes)
            if fit is None:
                rejected.add("capacity")
                continue
            wait = fit[1] - (free_at[eng.id] + minutes)
            candidates.append((minutes + wait, km, eng))

        if not candidates:
            for code in ("capacity", "distance", "transport", "skill"):
                if code in rejected:
                    return code
            return "capacity"

        candidates.sort(key=lambda c: (c[0], c[1]))
        for _score, _km, eng in candidates[:3]:
            depart = free_at[eng.id]
            minutes, km = self.travel_provider.get_leg(
                position[eng.id], ticket.point, eng.transport, depart
            )
            if minutes > self.max_leg_min:
                continue
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
        arrive = depart + travel_minutes
        start = max(arrive, ticket.work_start)  # приехал рано — ждёт окна
        end = start + ticket.duration_minutes
        # приехал после закрытия окна или не успевает до конца смены
        if start > ticket.work_finish or end > eng.work_shift_end_minutes:
            return None
        return arrive, start, end
