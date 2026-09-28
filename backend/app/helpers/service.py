import copy
import logging
from collections.abc import Callable
from datetime import date, datetime, time
from time import monotonic

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.helpers import repository
from app.helpers.mapping import engineer_from_row, region_from_row, ticket_from_row
from app.models.domain import Engeneer, Plan, Point, Region, Stop, Ticket
from app.presentation import planning_result_to_json, stored_plan_to_json
from app.results import PlanningResult
from app.routing.factory import create_routing
from app.routing.geometry import build_geometries
from app.routing.interface import RoutingProvider
from app.schemas import RequestCreate
from app.solver.evaluation import evaluate_plan
from app.solver.greedy import GreedySolver
from app.solver.vrp import VRPSolver
from app.solver.interface import Solver
from app.solver.validation import validate_plan

logger = logging.getLogger(__name__)
SolverFactory = Callable[[RoutingProvider, RoutingProvider], Solver]


class NoActivePlanError(Exception):
    """Перепланировать нечего: на этот день нет действующего плана."""


class DuplicateRequestError(Exception):
    def __init__(self, external_id: str):
        self.external_id = external_id
        super().__init__(f"Заявка с external_id={external_id!r} уже существует в этом регионе")


async def load_region(session: AsyncSession, region_id: int) -> Region | None:
    row = await repository.get_region(session, region_id)
    return region_from_row(row) if row else None


async def load_tickets(
    session: AsyncSession, region_id: int, work_date: date, office: Point
) -> list[Ticket]:
    rows = await repository.list_requests(session, region_id, work_date)
    ids = repository.public_ids(rows)
    return [ticket_from_row(r, ids[r.id], office) for r in rows]


async def create_request(session: AsyncSession, region_id: int, payload: RequestCreate):
    if await repository.request_exists(session, region_id, payload.external_id):
        raise DuplicateRequestError(payload.external_id)
    return await repository.create_request(session, region_id, payload)


async def load_engineers(session: AsyncSession, region_id: int, office) -> list[Engeneer]:
    rows = await repository.list_engineers(session, region_id)
    return [engineer_from_row(r, office) for r in rows]


async def build_plan(
    session: AsyncSession,
    region: Region,
    work_date: date | None = None,
    use_api: bool = True,
    persist: bool = True,
    solver_factory: SolverFactory = VRPSolver,
) -> PlanningResult:
    work_date = work_date or await repository.first_work_date(session, region.id)
    if work_date is None:
        return _empty(region.id, None, "в базе нет заявок для этого региона")

    tickets = await load_tickets(session, region.id, work_date, region.office)
    engineers = await load_engineers(session, region.id, region.office)
    if not tickets:
        return _empty(region.id, work_date, "на эту дату заявок нет")
    if not engineers:
        return _empty(region.id, work_date, "в регионе нет активных исполнителей")

    started = monotonic()
    providers = create_routing(work_date, use_api)
    solver = solver_factory(providers.travel_provider, providers.estimate_provider)
    plan = await run_in_threadpool(solver.solve, tickets, engineers)
    metrics = evaluate_plan(plan, tickets, engineers)
    geometries = await run_in_threadpool(build_geometries, plan, providers.travel_provider)

    result = PlanningResult(
        region.id,
        work_date,
        plan,
        metrics,
        {
            "solver": type(solver).__name__,
            "runtime_ms": int((monotonic() - started) * 1000),
            **providers.travel_provider.diagnostics,
        },
        geometries,
    )
    return await _publish_result(session, result, persist)


def _empty(region_id: int, work_date: date | None, note: str) -> PlanningResult:
    return PlanningResult(region_id, work_date, Plan([], []), metadata={"note": note})


async def _publish_result(
    session: AsyncSession, result: PlanningResult, persist: bool
) -> PlanningResult:
    if persist:
        result.metadata["plan_id"] = await repository.save_plan(session, result)
    if result.metrics is not None:
        logger.info("cost=%s", result.metrics.cost)
    return result


def _minutes(moment: datetime, day: date) -> int:
    return int((moment - datetime.combine(day, time.min)).total_seconds() // 60)


def _freeze(eng: Engeneer, at_minutes: int, last: Stop | None) -> Engeneer:
    """Инженер на момент аварии: где стоит и когда освободится."""
    clone = copy.copy(eng)
    clone.deployed = last is not None
    if last is not None:
        clone.start_point = last.ticket.point
        clone.work_shift_start_minutes = max(at_minutes, last.end)
    else:
        clone.work_shift_start_minutes = max(at_minutes, eng.work_shift_start_minutes)
    return clone


def _split(snapshot, tickets_by_request: dict[int, Ticket], day: date, at_minutes: int):
    """Разложить визиты прошлого плана на замороженные и свободные."""
    frozen: dict[int, list[Stop]] = {}
    was_with: dict[int, int] = {}  # заявка -> инженер в прошлом плане

    for route in snapshot.routes:
        for row in route.stops:
            ticket = tickets_by_request.get(row.request_id)
            if ticket is None:
                # Заявку успели выключить или перенести на другой день.
                continue
            was_with[row.request_id] = route.engineer_id
            if _minutes(row.start_at, day) >= at_minutes:
                continue  # ещё не начат — свободен
            frozen.setdefault(route.engineer_id, []).append(
                Stop(
                    ticket,
                    _minutes(row.depart_at, day),
                    _minutes(row.arrive_at, day),
                    _minutes(row.start_at, day),
                    _minutes(row.end_at, day),
                    row.travel_min,
                    row.travel_km,
                    frozen=True,
                )
            )

    for stops in frozen.values():
        stops.sort(key=lambda s: s.start)
    return frozen, was_with


async def replan(
    session: AsyncSession,
    region: Region,
    at: datetime,
    work_date: date | None = None,
    use_api: bool = True,
    persist: bool = True,
    solver_factory: SolverFactory = VRPSolver,
) -> PlanningResult:
    """Пересчитать день с момента `at`, оставив сделанное нетронутым."""
    work_date = work_date or at.date()
    snapshot = await repository.active_plan(session, region.id, work_date)
    if snapshot is None:
        raise NoActivePlanError

    tickets = await load_tickets(session, region.id, work_date, region.office)
    engineers = await load_engineers(session, region.id, region.office)
    if not tickets or not engineers:
        return _empty(region.id, work_date, "нечего перепланировать")

    at_minutes = _minutes(at, work_date)
    by_request = {t.request_id: t for t in tickets if t.request_id is not None}
    frozen, was_with = _split(snapshot, by_request, work_date, at_minutes)

    done = {s.ticket.request_id for stops in frozen.values() for s in stops}
    free = [t for t in tickets if t.request_id not in done]

    # Инженеры «как есть на момент T». Порядок совпадает с engineers —
    # он нужен, чтобы потом вернуть в маршруты настоящие объекты.
    by_id = {e.id: e for e in engineers}
    state = [_freeze(e, at_minutes, (frozen.get(e.id) or [None])[-1]) for e in engineers]

    started = monotonic()
    providers = create_routing(work_date, use_api)
    solver = solver_factory(providers.travel_provider, providers.estimate_provider)
    plan = await run_in_threadpool(solver.solve, free, state)
    validate_plan(plan, free, state, not_before=at_minutes).raise_if_invalid()

    moves = []
    for route in plan.routes:
        eng_id = route.engeneer.id
        for stop in route.stops:
            before = (
                was_with.get(stop.ticket.request_id) if stop.ticket.request_id is not None else None
            )
            if before not in (None, eng_id):
                stop.moved_from = before
                moves.append({"request_id": str(stop.ticket.id), "from": before, "to": eng_id})
        route.stops = frozen.get(eng_id, []) + route.stops
        route.engeneer = by_id[eng_id]

    metrics = evaluate_plan(plan, tickets, engineers, frozen=frozen, not_before=at_minutes)
    geometries = await run_in_threadpool(build_geometries, plan, providers.travel_provider)

    replan_metadata = {
        "frozen_at": at.isoformat(timespec="minutes"),
        "frozen_stops": sum(len(v) for v in frozen.values()),
        "replanned_stops": sum(len(r.stops) for r in plan.used_routes)
        - sum(len(v) for v in frozen.values()),
        "moved": len(moves),
        "moves": moves,
        "base_plan_id": snapshot.id,
    }

    result = PlanningResult(
        region.id,
        work_date,
        plan,
        metrics,
        {
            "solver": type(solver).__name__,
            "runtime_ms": int((monotonic() - started) * 1000),
            **providers.travel_provider.diagnostics,
            "replan": replan_metadata,
        },
        geometries,
    )
    return await _publish_result(session, result, persist)


async def stored_plan(session: AsyncSession, region: Region, work_date: date | None = None) -> dict:
    """Действующий план из базы. Солвер не запускается.

    Плана нет — отдаём пустой каркас с meta.stored = false: фронту этого
    достаточно, чтобы предложить рассчитать день, и это не ошибка.
    """
    work_date = work_date or await repository.first_work_date(session, region.id)
    if work_date is None:
        return planning_result_to_json(
            _empty(region.id, None, "в базе нет заявок для этого региона")
        )

    snapshot = await repository.active_plan(session, region.id, work_date)
    if snapshot is None:
        empty = _empty(region.id, work_date, "план ещё не рассчитан")
        empty.metadata["stored"] = False
        return planning_result_to_json(empty)

    rows = await repository.list_requests(session, region.id, work_date)
    engineers = await load_engineers(session, region.id, region.office)
    result = stored_plan_to_json(
        snapshot, region.id, work_date, repository.public_ids(rows), engineers
    )
    cost = result["metrics"]["cost"]
    logger.info("cost=%s", cost if cost is not None else "unavailable")
    return result
