import logging
import time
from datetime import datetime
from time import sleep

from ..helpers.cache import LegCache
from ..helpers.estimator import OVERHEAD_MIN, REASONS, estimate
from ..helpers.geometry import leg_points, thin
from ..models.domain import (
    Engeneer,
    Plan,
    Point,
    Route,
    Stop,
    Ticket,
    TransportType,
    Unassigned,
)
from .improve import improve
from .improve import schedule as replay
from .interface import Solver

logger = logging.getLogger(__name__)

"""
Жадный планировщик.

1. Сортируем заявки.
2. Для каждой ищем исполнителя ПО ПРЯМОЙ — быстро и бесплатно.
3. Выбранному считаем настоящее плечо через 2ГИС и проверяем ещё раз.

"""


# Потолок одного переезда.
MAX_LEG_MIN = 90

# Обеденный перерыв: длительность и целевое окно (минуты от полуночи).
LUNCH_DURATION_MIN = 40
LUNCH_WINDOW_START = 12 * 60  # 720
LUNCH_WINDOW_END = 15 * 60  # 900


class GreedySolver(Solver):
    def __init__(
        self,
        work_date: datetime | None = None,
        use_api: bool = False,
        cache: LegCache | None = None,
        max_leg_min: int = MAX_LEG_MIN,
        polish: bool = True,
    ):
        super().__init__()
        self.work_date = work_date
        self.use_api = use_api
        self.cache = cache or LegCache()
        self.max_leg_min = max_leg_min
        self.polish = polish
        self.cache_taken = 0
        self.api_calls = 0

    def get_name(self) -> str:
        return "GreedySolver"

    def solve(self, tickets: list[Ticket], engeneers: list[Engeneer]) -> Plan:
        started = time.monotonic()
        self.api_calls = 0
        self.cache_taken = 0

        # Состояние на время прогона: маршрут, где инженер сейчас и когда освободится.
        routes = {e.id: Route(e) for e in engeneers}
        position = {e.id: e.start_point for e in engeneers}
        free_at = {e.id: e.work_shift_start_minutes for e in engeneers}

        unassigned: list[Unassigned] = []
        order = sorted(
            tickets, key=lambda t: (t.work_start, t.priority, t.work_finish - t.work_start)
        )

        # for index, ticket in enumerate(order):
        #     print(f"{index} - {ticket.id} ({ticket.work_start}, {ticket.work_finish}, {ticket.priority}, {ticket.duration_minutes})")

        for ticket in order:
            reason = self._place(ticket, engeneers, routes, position, free_at)
            if reason:
                unassigned.append(Unassigned(ticket, reason, REASONS[reason]))

        polish = {}
        if self.polish:
            routes, unassigned, polish = self._polish(routes, unassigned, engeneers)

        for route in routes.values():
            route.geometry = self._geometry(route.engeneer, route.stops)

        lunch_missing = self._insert_lunch(routes)

        return Plan(
            routes=list(routes.values()),
            unassigned=unassigned,
            meta={
                "solver": self.get_name(),
                "provider": "2gis" if self.use_api else "haversine",
                "api_calls": self.api_calls,
                "cache_hits": self.cache_taken,
                "max_leg_min": self.max_leg_min,
                "polish": polish,
                "lunch_missing": lunch_missing,
                "runtime_ms": int((time.monotonic() - started) * 1000),
            },
        )

    def _polish(self, routes, unassigned, engeneers):
        """
        Улучшаем план с помощью перестановок
        """
        order = {e.id: [s.ticket for s in routes[e.id].stops] for e in engeneers}
        why = {u.ticket.id: (u.reason, u.reason_text) for u in unassigned}
        order, dropped, stats = improve(
            order, [u.ticket for u in unassigned], engeneers, estimate, self.max_leg_min
        )

        stats["broken"] = sum(
            1 for eng in engeneers if replay(eng, order[eng.id], estimate, self.max_leg_min) is None
        )

        rough = 0
        for eng in engeneers:
            got = replay(eng, order[eng.id], self._road) if self.use_api else None
            if got is None:
                got = replay(eng, order[eng.id], estimate)
                rough += 1 if self.use_api else 0
            routes[eng.id].stops = got[0] if got else []

        stats["rough_routes"] = rough
        return routes, [Unassigned(t, *why[t.id]) for t in dropped], stats

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
                    # print(f"{code} error---------")
                    return code
            return "capacity"

        candidates.sort(key=lambda c: (c[0], c[1]))
        # Шаг 3: подтверждаем настоящей дорогой.
        logger.debug("Candidated:")
        for _score, _km, eng in candidates[:3]:
            depart = free_at[eng.id]
            minutes, km = self._road(position[eng.id], ticket.point, eng.transport, depart)
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
        """Влезает ли заявка в конец маршрута: (приезд, начало, конец)."""
        arrive = depart + travel_minutes
        start = max(arrive, ticket.work_start)  # приехал рано — ждёт окна
        end = start + ticket.duration_minutes

        if start > ticket.work_finish:  # приехал после закрытия окна
            return None
        if end > eng.work_shift_end_minutes:  # не успевает до конца смены
            return None
        return arrive, start, end

    def _insert_lunch(self, routes: dict[int, Route]) -> int:
        """
        Пытаемся впихнуть обед (LUNCH_DURATION_MIN) в уже посчитанный простой
        маршрута, ориентировочно между LUNCH_WINDOW_START и LUNCH_WINDOW_END.

        Обед — заявка-заглушка (Ticket.id is None), вставленная обычным Stop
        внутрь простоя. Плечо (travel) до точки, где раньше начинался простой,
        "переезжает" на обеденный Stop, а у соседнего реального визита
        travel_minutes/travel_km обнуляются (он теперь стартует с той же точки,
        где только что пообедали) — сумма travel/km по маршруту не меняется,
        а start/end реальных визитов остаются побайтово теми же.

        Возвращает количество маршрутов с визитами, куда обед не влез.
        """
        missing = 0
        for route in routes.values():
            eng = route.engeneer
            stops = route.stops
            if not stops:
                continue  # пустой маршрут — обедать некому

            # (индекс вставки, начало окна простоя, конец окна, точка)
            windows: list[tuple[int, int, int, Point]] = []
            for i, stop in enumerate(stops):
                if stop.wait_minutes > 0:
                    windows.append((i, stop.arrive, stop.start, stop.ticket.point))
            last = stops[-1]
            if eng.work_shift_end_minutes > last.end:
                windows.append((len(stops), last.end, eng.work_shift_end_minutes, last.ticket.point))

            candidates = [w for w in windows if w[2] - w[1] >= LUNCH_DURATION_MIN]
            if not candidates:
                missing += 1
                continue

            def score(window: tuple[int, int, int, Point]) -> tuple[int, int]:
                _, start, end, _ = window
                overlap = max(0, min(end, LUNCH_WINDOW_END) - max(start, LUNCH_WINDOW_START))
                break_start = min(max(LUNCH_WINDOW_START, start), end - LUNCH_DURATION_MIN)
                # больше перекрытие -> лучше; при равенстве -> более раннее окно
                return (-overlap, break_start)

            idx, win_start, win_end, point = min(candidates, key=score)
            break_start = min(max(LUNCH_WINDOW_START, win_start), win_end - LUNCH_DURATION_MIN)
            break_end = break_start + LUNCH_DURATION_MIN

            lunch_ticket = Ticket(
                id=None,
                point=point,
                duration_minutes=LUNCH_DURATION_MIN,
                work_start=break_start,
                work_finish=break_end,
            )

            if idx < len(stops):
                neighbour = stops[idx]
                lunch_stop = Stop(
                    lunch_ticket,
                    neighbour.depart,
                    neighbour.arrive,
                    break_start,
                    break_end,
                    neighbour.travel_minutes,
                    neighbour.travel_km,
                )
                neighbour.depart = break_end
                neighbour.arrive = break_end
                neighbour.travel_minutes = 0
                neighbour.travel_km = 0.0
                stops.insert(idx, lunch_stop)
            else:
                lunch_stop = Stop(lunch_ticket, last.end, last.end, break_start, break_end, 0, 0.0)
                stops.append(lunch_stop)

        return missing

    def _when(self, depart: int) -> datetime | None:
        if not self.work_date:
            return None
        return self.work_date.replace(
            hour=min(23, depart // 60), minute=depart % 60, second=0, microsecond=0
        )

    def _geometry(self, eng: Engeneer, stops: list[Stop]) -> list[list[float]] | None:
        where, points = eng.start_point, []
        for stop in stops:
            to = stop.ticket.point
            leg = leg_points(
                self.cache.raw(eng.transport, where.coords, to.coords, self._when(stop.depart))
            )
            points += leg or [[where.latitude, where.longitude], [to.latitude, to.longitude]]
            where = to
        return thin(points) or None

    def _road(self, a: Point, b: Point, transport: TransportType, depart: int) -> tuple[int, float]:
        when = self._when(depart)
        cached = self.cache.get(transport, a.coords, b.coords, when)
        if cached is not None:
            self.cache_taken += 1
            return cached[0] + OVERHEAD_MIN, round(cached[1], 2)

        if not self.use_api:
            return estimate(a, b, transport, depart)

        from ..twogis.client import car_route, pedestrian_route

        try:
            self.api_calls += 1
            fn = car_route if transport == TransportType.CAR else pedestrian_route
            sleep(3)
            leg = fn(a.coords, b.coords, when)
        except Exception:
            logger.warning(
                "Ошибка построения маршрута 2ГИС, используется оценка расстояния",
                exc_info=True,
            )
            #             exit()
            return estimate(a, b, transport, depart)

        self.cache.put(transport, a.coords, b.coords, when, leg.minutes, leg.km, leg.raw)
        return leg.minutes + OVERHEAD_MIN, round(leg.km, 2)
