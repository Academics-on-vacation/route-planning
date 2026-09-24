import copy
from datetime import date, datetime, time

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.helpers import repository
from app.helpers.cache import LegCache
from app.models.domain import Engeneer, Point, Region, Stop, Ticket, at
from app.schemas import RequestCreate
from app.solver.greedy import GreedySolver


class NoActivePlanError(Exception):
    """Перепланировать нечего: на этот день нет действующего плана."""


class DuplicateRequestError(Exception):
    def __init__(self, external_id: str):
        self.external_id = external_id
        super().__init__(f"Заявка с external_id={external_id!r} уже существует в этом регионе")


async def load_region(session: AsyncSession, region_id: int) -> Region | None:
    row = await repository.get_region(session, region_id)
    return Region.from_row(row) if row else None


async def load_tickets(
    session: AsyncSession, region_id: int, work_date: date, office: Point
) -> list[Ticket]:
    rows = await repository.list_requests(session, region_id, work_date)
    ids = repository.public_ids(rows)
    return [Ticket.from_row(r, ids[r.id], office) for r in rows]


async def create_request(session: AsyncSession, region_id: int, payload: RequestCreate):
    if await repository.request_exists(session, region_id, payload.external_id):
        raise DuplicateRequestError(payload.external_id)
    return await repository.create_request(session, region_id, payload)


async def load_engineers(session: AsyncSession, region_id: int, office) -> list[Engeneer]:
    rows = await repository.list_engineers(session, region_id)
    return [Engeneer.from_row(r, office) for r in rows]


async def build_plan(
    session: AsyncSession,
    region: Region,
    work_date: date | None = None,
    use_api: bool = True,
    persist: bool = True,
) -> dict:
    work_date = work_date or await repository.first_work_date(session, region.id)
    if work_date is None:
        return _empty(region.id, None, "в базе нет заявок для этого региона")

    tickets = await load_tickets(session, region.id, work_date, region.office)
    engineers = await load_engineers(session, region.id, region.office)
    if not tickets:
        return _empty(region.id, work_date, "на эту дату заявок нет")
    if not engineers:
        return _empty(region.id, work_date, "в регионе нет активных исполнителей")

    cache = LegCache(await repository.load_leg_cache(session, work_date))

    solver = GreedySolver(
        work_date=datetime.combine(work_date, time.min), use_api=use_api, cache=cache
    )

    plan = await run_in_threadpool(solver.solve, tickets, engineers)

    plan.meta["cache_saved"] = await repository.save_leg_cache(session, cache.pending)

    # Снимок плана в базе: с него будет стартовать перепланирование.
    if persist:
        plan.meta["plan_id"] = await repository.save_plan(session, region.id, work_date, plan)

    return plan.to_json(region.id, work_date)


def _empty(region_id: int, work_date: date | None, note: str) -> dict:
    return {
        "region_id": region_id,
        "work_date": work_date.isoformat() if work_date else None,
        "routes": [],
        "unassigned": [],
        "metrics": {},
        "meta": {"note": note},
    }


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
) -> dict:
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
    by_request = {t.request_id: t for t in tickets}
    frozen, was_with = _split(snapshot, by_request, work_date, at_minutes)

    done = {s.ticket.request_id for stops in frozen.values() for s in stops}
    free = [t for t in tickets if t.request_id not in done]

    # Инженеры «как есть на момент T». Порядок совпадает с engineers —
    # он нужен, чтобы потом вернуть в маршруты настоящие объекты.
    by_id = {e.id: e for e in engineers}
    state = [_freeze(e, at_minutes, (frozen.get(e.id) or [None])[-1]) for e in engineers]

    cache = LegCache(await repository.load_leg_cache(session, work_date))
    solver = GreedySolver(
        work_date=datetime.combine(work_date, time.min), use_api=use_api, cache=cache
    )
    plan = await run_in_threadpool(solver.solve, free, state)

    # Склейка: день должен остаться целым, иначе Гант покажет огрызок
    # с середины. Сделанное идёт первым, пересчитанное — следом.
    moves = []
    for route in plan.routes:
        eng_id = route.engeneer.id
        for stop in route.stops:
            before = was_with.get(stop.ticket.request_id)
            if before not in (None, eng_id):
                # Помечаем и сам визит, и общий список перестановок:
                # первое нужно строке в списке, второе — тому, у кого
                # заявку забрали, он про неё иначе не узнает.
                stop.moved_from = before
                moves.append({"request_id": str(stop.ticket.id), "from": before, "to": eng_id})
        route.stops = frozen.get(eng_id, []) + route.stops
        route.engeneer = by_id[eng_id]
        # Нитку рисуем заново уже по всему дню — от настоящей точки
        # старта, а не от той, где инженер оказался к моменту аварии.
        route.geometry = solver._geometry(route.engeneer, route.stops)

    plan.meta["cache_saved"] = await repository.save_leg_cache(session, cache.pending)
    plan.meta["replan"] = {
        "frozen_at": at.isoformat(timespec="minutes"),
        "frozen_stops": sum(len(v) for v in frozen.values()),
        "replanned_stops": sum(len(r.stops) for r in plan.used_routes)
        - sum(len(v) for v in frozen.values()),
        "moved": len(moves),
        "moves": moves,
        "base_plan_id": snapshot.id,
    }

    if persist:
        plan.meta["plan_id"] = await repository.save_plan(session, region.id, work_date, plan)

    return plan.to_json(region.id, work_date)


def _stored_json(snapshot, region_id: int, work_date: date, public: dict, engineers) -> dict:
    replan_meta = (snapshot.meta or {}).get("replan") or {}
    frozen_at = replan_meta.get("frozen_at")
    came_from = {m["request_id"]: m["from"] for m in replan_meta.get("moves", [])}
    by_id = {e.id: e for e in engineers}

    routes = []
    for row in sorted(snapshot.routes, key=lambda r: r.engineer_id):
        eng = by_id.get(row.engineer_id)
        if eng is None or not row.stops:
            # Инженера выключили после расчёта — маршрут показывать не на чем.
            continue
        stops = []
        for st in row.stops:
            request_id = public.get(st.request_id, str(st.request_id))
            stops.append(
                {
                    "seq": st.seq,
                    "request_id": request_id,
                    "arrive_at": st.arrive_at.isoformat(),
                    "start_at": st.start_at.isoformat(),
                    "end_at": st.end_at.isoformat(),
                    "wait_min": int((st.start_at - st.arrive_at).total_seconds() // 60),
                    "travel_min": st.travel_min,
                    "travel_km": st.travel_km,
                    "frozen": bool(frozen_at and st.start_at.isoformat() < frozen_at),
                    "moved_from": came_from.get(request_id),
                }
            )
        routes.append(
            {
                "engineer_id": row.engineer_id,
                "engineer_name": eng.name,
                "start": {
                    "lat": eng.start_point.latitude,
                    "lon": eng.start_point.longitude,
                    "at": at(work_date, eng.work_shift_start_minutes),
                },
                "stops": stops,
                "distance_km": round(row.distance_km, 1),
                "travel_min": row.travel_min,
                "service_min": row.service_min,
                "wait_min": row.wait_min,
                "finish_at": stops[-1]["end_at"],
                "geometry": row.geometry,
            }
        )

    return {
        "region_id": region_id,
        "work_date": work_date.isoformat(),
        "routes": routes,
        "unassigned": (snapshot.meta or {}).get("unassigned", []),
        "metrics": snapshot.metrics or {},
        "meta": {
            **(snapshot.meta or {}),
            "stored": True,
            "plan_id": snapshot.id,
            "created_at": snapshot.created_at.isoformat(timespec="seconds"),
        },
    }


async def stored_plan(session: AsyncSession, region: Region, work_date: date | None = None) -> dict:
    """Действующий план из базы. Солвер не запускается.

    Плана нет — отдаём пустой каркас с meta.stored = false: фронту этого
    достаточно, чтобы предложить рассчитать день, и это не ошибка.
    """
    work_date = work_date or await repository.first_work_date(session, region.id)
    if work_date is None:
        return {
            **_empty(region.id, None, "в базе нет заявок для этого региона"),
        }

    snapshot = await repository.active_plan(session, region.id, work_date)
    if snapshot is None:
        empty = _empty(region.id, work_date, "план ещё не рассчитан")
        empty["meta"]["stored"] = False
        return empty

    rows = await repository.list_requests(session, region.id, work_date)
    engineers = await load_engineers(session, region.id, region.office)
    return _stored_json(snapshot, region.id, work_date, repository.public_ids(rows), engineers)
