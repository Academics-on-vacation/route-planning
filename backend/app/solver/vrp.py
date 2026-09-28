from __future__ import annotations

import logging

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from app.models.domain import (
    Engeneer,
    Plan,
    Point,
    Route,
    Stop,
    Ticket,
    TransportType,
    Unassigned,
)
from app.routing.interface import RoutingProvider
from app.solver.interface import Solver

logger = logging.getLogger(__name__)

# Значения для пар, до которых не смог добраться ни travel, ни estimate.
# Не бесконечность (сломает горизонт), но достаточно много, чтобы солвер
# их избегал, если есть альтернатива.
UNREACHABLE_MINUTES = 24 * 60
UNREACHABLE_METERS = 10_000_000  # 10 000 км


class VRPSolver(Solver):
    """VRP на OR-Tools.

    Приоритеты оптимизации (лексикографически):
      1. Минимум задействованных исполнителей  — fixed cost за машину.
      2. Минимум суммарного пробега            — arc cost = расстояние, м.
      3. Максимум обслуженных заявок           — drop penalty, ×priority.

    Провайдеры: travel — основной, estimate — fallback при исключении/None.
    """

    def __init__(
        self,
        travel: RoutingProvider,
        estimate: RoutingProvider,
        *,
        planning_departure: int = 14 * 60,
        time_limit_seconds: int = 30,
        random_seed: int = 42,
    ):
        self._travel = travel
        self._estimate = estimate
        self._planning_departure = planning_departure
        self._time_limit_seconds = time_limit_seconds
        self._random_seed = random_seed

    def get_name(self) -> str:
        return "VRPSolver"

    # -----------------------------------------------------------------
    # Public
    # -----------------------------------------------------------------

    def solve(self, tickets: list[Ticket], engineers: list[Engeneer]) -> Plan:
        if not tickets:
            return Plan(routes=[], unassigned=[])
        if not engineers:
            return Plan(
                routes=[],
                unassigned=[
                    Unassigned(t, "no_engineer", "нет доступных исполнителей") for t in tickets
                ],
            )

        eligible, pre_unassigned = self._filter_incompatible(tickets, engineers)
        if not eligible:
            return Plan(routes=[], unassigned=pre_unassigned)

        data = self._build_data(eligible, engineers)
        manager, routing, time_dim = self._build_routing(data)
        solution = self._solve(routing)

        if solution is None:
            return Plan(
                routes=[],
                unassigned=list(pre_unassigned)
                + [Unassigned(t, "no_solution", "не удалось построить решение") for t in eligible],
            )

        return self._extract_plan(data, manager, routing, time_dim, solution, pre_unassigned)

    # -----------------------------------------------------------------
    # Providers
    # -----------------------------------------------------------------

    def _get_leg(
        self, origin: Point, dest: Point, transport: TransportType, departure: int
    ) -> tuple[int, float] | None:
        for provider in (self._travel, self._estimate):
            try:
                leg = provider.get_leg(origin, dest, transport, departure)
            except Exception as exc:
                logger.debug("get_leg via %s failed: %s", type(provider).__name__, exc)
                continue
            if leg is not None:
                return leg
        return None

    # -----------------------------------------------------------------
    # Pre-filter
    # -----------------------------------------------------------------

    def _filter_incompatible(
        self, tickets: list[Ticket], engineers: list[Engeneer]
    ) -> tuple[list[Ticket], list[Unassigned]]:
        eligible: list[Ticket] = []
        unassigned: list[Unassigned] = []

        for t in tickets:
            if t.work_start > t.work_finish:
                unassigned.append(Unassigned(t, "window", "некорректное окно"))
                continue
            if t.duration_minutes <= 0:
                unassigned.append(Unassigned(t, "window", "нулевая или отрицательная длительность"))
                continue
            if not any(e.skills.has(t.skill) for e in engineers):
                unassigned.append(
                    Unassigned(t, "skill", f"нет исполнителя с навыком {t.skill.value}")
                )
                continue
            if t.required_transport is not None and not any(
                e.skills.has(t.skill) and e.transport == t.required_transport for e in engineers
            ):
                unassigned.append(
                    Unassigned(
                        t,
                        "transport",
                        f"нет исполнителя с навыком {t.skill.value} "
                        f"и транспортом {t.required_transport.value}",
                    )
                )
                continue
            fits = any(
                self._can_serve(e, t)
                and e.work_shift_start_minutes <= t.work_finish
                and t.work_start + t.duration_minutes <= e.work_shift_end_minutes
                for e in engineers
            )
            if not fits:
                unassigned.append(Unassigned(t, "window", "окно не вписывается ни в одну смену"))
                continue
            eligible.append(t)

        return eligible, unassigned

    def _can_serve(self, eng: Engeneer, ticket: Ticket) -> bool:
        if not eng.skills.has(ticket.skill):
            return False
        if ticket.required_transport is not None:
            return eng.transport == ticket.required_transport
        return True

    # -----------------------------------------------------------------
    # Data
    # -----------------------------------------------------------------

    def _build_data(self, tickets: list[Ticket], engineers: list[Engeneer]) -> dict:
        """Узлы: 0..N-1 заявки; N..N+M-1 старты; N+M..N+2M-1 финиши."""
        N, M = len(tickets), len(engineers)

        points: list[Point] = (
            [t.point for t in tickets]
            + [e.start_point for e in engineers]
            + [e.start_point for e in engineers]
        )
        service_times = [t.duration_minutes for t in tickets] + [0] * (2 * M)

        transports = {e.transport for e in engineers}
        time_by_tr, dist_by_tr = self._build_matrices(points, transports)

        return {
            "tickets": tickets,
            "engineers": engineers,
            "points": points,
            "num_vehicles": M,
            "starts": [N + i for i in range(M)],
            "ends": [N + M + i for i in range(M)],
            "service_times": service_times,
            "time_matrix_by_transport": time_by_tr,
            "dist_matrix_by_transport": dist_by_tr,
        }

    def _build_matrices(
        self, points: list[Point], transports: set[TransportType]
    ) -> tuple[
        dict[TransportType, list[list[int]]],
        dict[TransportType, list[list[int]]],
    ]:
        n = len(points)
        time_by_tr: dict[TransportType, list[list[int]]] = {}
        dist_by_tr: dict[TransportType, list[list[int]]] = {}

        for tr in transports:
            tm = [[0] * n for _ in range(n)]
            dm = [[0] * n for _ in range(n)]
            for i in range(n):
                for j in range(n):
                    if i == j:
                        continue
                    leg = self._get_leg(points[i], points[j], tr, self._planning_departure)
                    if leg is None:
                        tm[i][j] = UNREACHABLE_MINUTES
                        dm[i][j] = UNREACHABLE_METERS
                    else:
                        tm[i][j] = leg[0]
                        dm[i][j] = int(round(leg[1] * 1000))
            time_by_tr[tr] = tm
            dist_by_tr[tr] = dm

        return time_by_tr, dist_by_tr

    # -----------------------------------------------------------------
    # Model
    # -----------------------------------------------------------------

    def _build_routing(self, data: dict):
        manager = pywrapcp.RoutingIndexManager(
            len(data["points"]),
            data["num_vehicles"],
            data["starts"],
            data["ends"],
        )
        routing = pywrapcp.RoutingModel(manager)
        service = data["service_times"]

        def dist_cb_maker(matrix):
            def cb(fi: int, ti: int) -> int:
                return matrix[manager.IndexToNode(fi)][manager.IndexToNode(ti)]

            return cb

        def time_cb_maker(matrix):
            def cb(fi: int, ti: int) -> int:
                f = manager.IndexToNode(fi)
                t = manager.IndexToNode(ti)
                return matrix[f][t] + service[f]

            return cb

        dist_cb: list[int] = []
        time_cb: list[int] = []
        for eng in data["engineers"]:
            dist_cb.append(
                routing.RegisterTransitCallback(
                    dist_cb_maker(data["dist_matrix_by_transport"][eng.transport])
                )
            )
            time_cb.append(
                routing.RegisterTransitCallback(
                    time_cb_maker(data["time_matrix_by_transport"][eng.transport])
                )
            )

        # 1) Стоимость = расстояние (вторая по важности цель после fixed cost).
        for v in range(data["num_vehicles"]):
            routing.SetArcCostEvaluatorOfVehicle(dist_cb[v], v)

        # 2) Fixed cost за машину. Должен доминировать над любым пробегом одного
        #    маршрута, иначе солвер предпочтёт добавить машину ради экономии км.
        max_edge = max(
            (max(row) for m in data["dist_matrix_by_transport"].values() for row in m),
            default=0,
        )
        max_route_dist = max_edge * len(data["points"])
        fixed_cost = max_route_dist + 1

        for v in range(data["num_vehicles"]):
            routing.SetFixedCostOfVehicle(fixed_cost, v)

        # 3) Drop penalty. Базовый минимум должен перевешивать экономию
        #    от отказа (fixed_cost + пробег), иначе солвер начнёт бросать
        #    заявки ради сокращения парка.
        min_drop = fixed_cost + max_route_dist + 1
        drop_weight = max(min_drop // 100, 1)  # priority=100 → 2× min_drop

        # Time dimension — только для окон и смен, в цель не входит.
        max_shift_end = max(e.work_shift_end_minutes for e in data["engineers"])
        max_ticket_finish = max((t.work_finish for t in data["tickets"]), default=0)
        horizon = max(max_shift_end, max_ticket_finish, self._planning_departure) + 120

        routing.AddDimensionWithVehicleTransits(time_cb, horizon, horizon, False, "Time")
        time_dim = routing.GetDimensionOrDie("Time")

        for i, ticket in enumerate(data["tickets"]):
            time_dim.CumulVar(manager.NodeToIndex(i)).SetRange(
                ticket.work_start, ticket.work_finish
            )

        for v, eng in enumerate(data["engineers"]):
            time_dim.CumulVar(routing.Start(v)).SetRange(
                eng.work_shift_start_minutes, eng.work_shift_end_minutes
            )
            time_dim.CumulVar(routing.End(v)).SetRange(
                eng.work_shift_start_minutes, eng.work_shift_end_minutes
            )

        for i, ticket in enumerate(data["tickets"]):
            idx = manager.NodeToIndex(i)
            allowed = [v for v, eng in enumerate(data["engineers"]) if self._can_serve(eng, ticket)]
            vehicle_var = routing.VehicleVar(idx)
            for v in range(data["num_vehicles"]):
                if v not in allowed:
                    vehicle_var.RemoveValue(v)

            routing.AddDisjunction([idx], min_drop + ticket.priority * drop_weight)

        return manager, routing, time_dim

    # -----------------------------------------------------------------
    # Solve
    # -----------------------------------------------------------------

    def _solve(self, routing):
        params = pywrapcp.DefaultRoutingSearchParameters()
        params.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
        )
        params.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        )
        params.time_limit.FromSeconds(self._time_limit_seconds)
        self._apply_random_seed(params)
        return routing.SolveWithParameters(params)

    def _apply_random_seed(self, params) -> None:
        """Сид RNG: поле в разных сборках OR-Tools живёт в разных местах."""
        if "random_seed" in params.DESCRIPTOR.fields_by_name:
            params.random_seed = self._random_seed
            return
        sat = getattr(params, "sat_parameters", None)
        if sat is not None and "random_seed" in sat.DESCRIPTOR.fields_by_name:
            sat.random_seed = self._random_seed

    # -----------------------------------------------------------------
    # Extract
    # -----------------------------------------------------------------

    def _extract_plan(self, data, manager, routing, time_dim, solution, pre_unassigned) -> Plan:
        routes: list[Route] = []
        served: set[str] = set()

        for v, eng in enumerate(data["engineers"]):
            if not routing.IsVehicleUsed(solution, v):
                continue

            tmatrix = data["time_matrix_by_transport"][eng.transport]
            dmatrix = data["dist_matrix_by_transport"][eng.transport]
            stops: list[Stop] = []

            index = routing.Start(v)
            prev_node = manager.IndexToNode(index)
            prev_depart = solution.Value(time_dim.CumulVar(index))

            while not routing.IsEnd(index):
                next_index = solution.Value(routing.NextVar(index))
                next_node = manager.IndexToNode(next_index)
                if routing.IsEnd(next_index):
                    break

                ticket: Ticket = data["tickets"][next_node]
                travel_min = tmatrix[prev_node][next_node]
                travel_km = dmatrix[prev_node][next_node] / 1000.0

                arrive = prev_depart + travel_min
                start = solution.Value(time_dim.CumulVar(next_index))
                if arrive > start:
                    arrive = start
                end = start + ticket.duration_minutes

                stops.append(
                    Stop(
                        ticket=ticket,
                        depart=prev_depart,
                        arrive=arrive,
                        start=start,
                        end=end,
                        travel_minutes=travel_min,
                        travel_km=travel_km,
                    )
                )
                served.add(ticket.id)

                prev_node = next_node
                prev_depart = end
                index = next_index

            routes.append(Route(engeneer=eng, stops=stops))

        unassigned = list(pre_unassigned)
        for t in data["tickets"]:
            if t.id not in served:
                unassigned.append(Unassigned(t, "window", "не удалось вписать в маршрут"))

        return Plan(routes=routes, unassigned=unassigned)
