from datetime import date, datetime

from fastapi import Body, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import geocoder
from app.config import settings
from app.db import get_session
from app.helpers import repository, service
from app.importing.router import router as import_router
from app.logging_config import configure_logging
from app.models.domain import Region
from app.schemas import EngineerStartPointUpdate, RequestCreate, engineer_to_json, request_to_json

configure_logging()

app = FastAPI(title="Route Planning API", version="0.1.0")
app.include_router(import_router)
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
    region = await _region(session, region_id)
    work_date = work_date or await repository.first_work_date(session, region_id)
    if work_date is None:
        return []

    tickets = await service.load_tickets(session, region_id, work_date, region.office)
    return [t.to_json(work_date) for t in tickets]


@app.post("/api/regions/{region_id}/requests", status_code=201)
async def create_request(
    region_id: int,
    payload: RequestCreate,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Создать заявку. lat/lon опциональны: без них заявка сохранится
    с NULL-координатами и будет стартовать из офиса, пока её не геокодируют."""
    await _region(session, region_id)
    try:
        row = await service.create_request(session, region_id, payload)
    except service.DuplicateRequestError as error:
        raise HTTPException(409, str(error)) from error
    return request_to_json(row)


@app.post("/api/plan/replan")
async def post_replan(
    body: dict = Body(default_factory=dict),
    session: AsyncSession = Depends(get_session),
) -> dict:
    raw_at = body.get("at")
    if not raw_at:
        raise HTTPException(422, "нужно передать момент перепланирования `at`")
    try:
        at = datetime.fromisoformat(raw_at).replace(tzinfo=None)
    except ValueError:
        raise HTTPException(422, f"не разобрал время {raw_at!r}") from None

    raw_date = body.get("work_date")
    options = body.get("options") or {}
    region = await _region(session, int(body.get("region_id", 1)))
    try:
        return await service.replan(
            session,
            region,
            at=at,
            work_date=date.fromisoformat(raw_date) if raw_date else None,
            use_api=bool(options.get("use_api", False)),
        )
    except service.NoActivePlanError:
        raise HTTPException(
            409, "на эту дату нет действующего плана — сначала рассчитайте день"
        ) from None


@app.get("/api/geocode")
async def get_geocode(
    q: str,
    region_id: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    around = None
    if region_id is not None:
        region = await service.load_region(session, region_id)
        if region:
            around = (region.office.latitude, region.office.longitude)
    try:
        found = await geocoder.suggest_addresses(q, settings.yandex_geocoder_api_key, around)
    except geocoder.GeocodingError as e:
        raise HTTPException(503, str(e)) from None
    return [s.model_dump() for s in found]


@app.get("/api/engineers")
async def get_all_engineers(
    region_id: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    rows = await repository.list_all_engineers(session, region_id)
    return [engineer_to_json(row) for row in rows]


@app.patch("/api/engineers/{engineer_id}")
async def patch_engineer(
    engineer_id: int,
    payload: EngineerStartPointUpdate,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Задать/сбросить точку старта инженера. start_lat/start_lon оба null —
    инженер снова стартует из офиса региона"""
    row = await repository.update_engineer_start_point(
        session, engineer_id, payload.start_lat, payload.start_lon
    )
    if row is None:
        raise HTTPException(404, f"Инженера {engineer_id} нет")
    return engineer_to_json(row)


@app.delete("/api/requests/{request_id}", status_code=204)
async def delete_request(
    request_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Удаление: is_active=false. Заявка исчезает из GET /requests
    и перестаёт участвовать в планировании, но остаётся в БД."""
    if not await repository.soft_delete_request(session, request_id):
        raise HTTPException(404, f"Заявки {request_id} нет")


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
    session: AsyncSession = Depends(get_session),
) -> dict:
    region = await _region(session, region_id)
    return await service.stored_plan(session, region, work_date)
