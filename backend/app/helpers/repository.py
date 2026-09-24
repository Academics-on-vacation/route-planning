from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.orm.engineer import Engineer
from app.orm.plan import Plan as PlanRow
from app.orm.region import Region
from app.orm.request import Request
from app.orm.route import Route as RouteRow
from app.orm.route_cache import RouteCache
from app.orm.stop import Stop as StopRow
from app.schemas import RequestCreate


async def get_region(session: AsyncSession, region_id: int) -> Region | None:
    return await session.get(Region, region_id)


async def list_regions(session: AsyncSession) -> list[Region]:
    return list(await session.scalars(select(Region).order_by(Region.id)))


async def first_work_date(session: AsyncSession, region_id: int) -> date | None:
    found = await session.scalar(
        select(func.min(Request.window_start)).where(Request.region_id == region_id)
    )
    return found.date() if found else None


async def list_requests(session: AsyncSession, region_id: int, work_date: date) -> list[Request]:
    rows = await session.scalars(
        select(Request)
        .where(
            Request.region_id == region_id,
            Request.is_active.is_(True),
            Request.window_start >= datetime.combine(work_date, time.min),
            Request.window_start < datetime.combine(work_date + timedelta(days=1), time.min),
        )
        .order_by(Request.window_start, Request.id)
    )
    return list(rows)


async def list_all_engineers(session: AsyncSession, region_id: int | None = None) -> list[Engineer]:
    query = select(Engineer).order_by(Engineer.region_id, Engineer.id)
    if region_id is not None:
        query = query.where(Engineer.region_id == region_id)
    return list(await session.scalars(query))


async def list_engineers(session: AsyncSession, region_id: int) -> list[Engineer]:
    rows = await session.scalars(
        select(Engineer)
        .where(Engineer.region_id == region_id, Engineer.is_active.is_(True))
        .order_by(Engineer.id)
    )
    return list(rows)


async def update_engineer_start_point(
    session: AsyncSession, engineer_id: int, start_lat: float | None, start_lon: float | None
) -> Engineer | None:
    row = await session.get(Engineer, engineer_id)
    if row is None:
        return None
    row.start_lat = start_lat
    row.start_lon = start_lon
    await session.commit()
    await session.refresh(row)
    return row


async def soft_delete_request(session: AsyncSession, request_id: int) -> bool:
    row = await session.get(Request, request_id)
    if row is None:
        return False
    row.is_active = False
    await session.commit()
    return True


async def request_exists(session: AsyncSession, region_id: int, external_id: str) -> bool:
    found = await session.scalar(
        select(Request.id).where(Request.region_id == region_id, Request.external_id == external_id)
    )
    return found is not None


async def create_request(session: AsyncSession, region_id: int, data: RequestCreate) -> Request:
    row = Request(region_id=region_id, **data.model_dump())
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


def public_ids(rows: list[Request]) -> dict[int, str]:
    seen = Counter(r.external_id for r in rows)
    return {
        r.id: (r.external_id if seen[r.external_id] == 1 else f"{r.external_id}-{r.id}")
        for r in rows
    }


async def load_leg_cache(session: AsyncSession, work_date: date) -> list[RouteCache]:
    """Сохранённые плечи на этот день — все разом, перед запуском солвера."""
    rows = await session.scalars(
        select(RouteCache).where(
            RouteCache.departure_at >= datetime.combine(work_date - timedelta(days=1), time.min),
            RouteCache.departure_at < datetime.combine(work_date + timedelta(days=2), time.min),
        )
    )
    return list(rows)


async def save_leg_cache(session: AsyncSession, rows: list[dict]) -> int:
    if not rows:
        return 0
    result = await session.execute(
        pg_insert(RouteCache).values(rows).on_conflict_do_nothing(constraint="uq_route_cache_leg")
    )
    await session.commit()
    return result.rowcount


async def save_plan(session: AsyncSession, region_id: int, work_date: date, plan) -> int:
    """Сохранить снимок плана и вернуть его id."""
    day = datetime.combine(work_date, time.min)

    await session.execute(
        update(PlanRow)
        .where(
            PlanRow.region_id == region_id,
            PlanRow.work_date == work_date,
            PlanRow.is_active.is_(True),
        )
        .values(is_active=False)
    )

    row = PlanRow(
        region_id=region_id,
        work_date=work_date,
        solver=str(plan.meta.get("solver", ""))[:64],
        provider=str(plan.meta.get("provider", ""))[:16],
        metrics=plan.metrics(),
        meta={**plan.meta, "unassigned": [u.to_json() for u in plan.unassigned]},
    )

    for route in plan.used_routes:
        route_row = RouteRow(
            engineer_id=route.engeneer.id,
            distance_km=round(route.distance_km, 3),
            travel_min=route.travel_minutes,
            service_min=route.service_minutes,
            wait_min=route.wait_minutes,
            geometry=route.geometry,
        )
        for seq, stop in enumerate(route.stops, 1):
            if stop.ticket.request_id is None:
                continue
            route_row.stops.append(
                StopRow(
                    request_id=stop.ticket.request_id,
                    seq=seq,
                    depart_at=day + timedelta(minutes=stop.depart),
                    arrive_at=day + timedelta(minutes=stop.arrive),
                    start_at=day + timedelta(minutes=stop.start),
                    end_at=day + timedelta(minutes=stop.end),
                    travel_min=stop.travel_minutes,
                    travel_km=round(stop.travel_km, 3),
                )
            )
        row.routes.append(route_row)

    session.add(row)
    await session.flush()
    plan_id = row.id
    await session.commit()
    return plan_id


async def active_plan(session: AsyncSession, region_id: int, work_date: date) -> PlanRow | None:
    """Действующий план на день — основа для перепланирования"""
    return await session.scalar(
        select(PlanRow)
        .where(
            PlanRow.region_id == region_id,
            PlanRow.work_date == work_date,
            PlanRow.is_active.is_(True),
        )
        .options(selectinload(PlanRow.routes).selectinload(RouteRow.stops))
    )
