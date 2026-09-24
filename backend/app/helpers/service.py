from datetime import date, datetime, time

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.helpers import repository
from app.helpers.cache import LegCache
from app.models.domain import Engeneer, Point, Region, Ticket
from app.schemas import RequestCreate
from app.solver.greedy import GreedySolver


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
