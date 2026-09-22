from datetime import date

from fastapi import Body, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.helpers import repository, service
from app.logging_config import configure_logging
from app.models.domain import Region

configure_logging()

app = FastAPI(title="Route Planning API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/health/db")
async def database_health() -> dict[str, str]:
    async for session in get_session():
        await session.execute(text("SELECT 1"))
        return {"status": "ok"}
    raise RuntimeError("database session was not created")


async def _region(session: AsyncSession, region_id: int) -> Region:
    region = await service.load_region(session, region_id)
    if region is None:
        raise HTTPException(404, f"Региона {region_id} нет")
    return region


@app.get("/api/regions")
async def get_regions(session: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = await repository.list_regions(session)
    return [Region.from_row(r).to_json() for r in rows]


@app.get("/api/regions/{region_id}/requests")
async def get_requests(
    region_id: int,
    work_date: date | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Справочник заявок. Фронт держит его отдельно от плана: план
    ссылается на заявки по id и координаты в себе не носит."""
    await _region(session, region_id)
    work_date = work_date or await repository.first_work_date(session, region_id)
    if work_date is None:
        return []

    tickets = await service.load_tickets(session, region_id, work_date)
    return [t.to_json(work_date) for t in tickets]


@app.get("/api/regions/{region_id}/engineers")
async def get_engineers(
    region_id: int,
    work_date: date | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    region = await _region(session, region_id)
    day = work_date or await repository.first_work_date(session, region_id) or date.today()
    engineers = await service.load_engineers(session, region_id, region.office)
    return [e.to_json(day) for e in engineers]


@app.post("/api/plan")
async def post_plan(
    body: dict = Body(default_factory=dict),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Тело: {region_id, work_date?, options: {use_api}}.

    work_date не передали — берём ближайший день, на который есть заявки."""
    options = body.get("options") or {}
    raw_date = body.get("work_date")
    region = await _region(session, int(body.get("region_id", 1)))
    return await service.build_plan(
        session,
        region,
        work_date=date.fromisoformat(raw_date) if raw_date else None,
        use_api=bool(options.get("use_api", False)),
    )


@app.get("/api/plan")
async def get_plan(
    region_id: int = 1,
    work_date: date | None = None,
    use_api: bool = True,
    session: AsyncSession = Depends(get_session),
) -> dict:
    region = await _region(session, region_id)
    return await service.build_plan(session, region, work_date, use_api)
