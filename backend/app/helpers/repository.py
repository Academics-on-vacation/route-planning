from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.orm.engineer import Engineer
from app.orm.region import Region
from app.orm.request import Request
from app.orm.route_cache import RouteCache
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


async def list_engineers(session: AsyncSession, region_id: int) -> list[Engineer]:
    rows = await session.scalars(
        select(Engineer)
        .where(Engineer.region_id == region_id, Engineer.is_active.is_(True))
        .order_by(Engineer.id)
    )
    return list(rows)


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
