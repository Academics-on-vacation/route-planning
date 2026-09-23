from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.geocoder import CoordinateResolver, Coordinates, GeocodingError
from app.importing.csv_parser import ParsedFile, parse_csv
from app.importing.schemas import EngineerInput, ImportError, ImportOptions
from app.orm.engineer import Engineer
from app.orm.region import Region
from app.orm.request import Request


def prepare_engineers(parsed: ParsedFile, options: ImportOptions) -> list[EngineerInput]:
    names = {r.engineer_name for r in parsed.requests if r.engineer_name}
    if options.engineers:
        if names - {e.name for e in options.engineers}:
            raise ImportError("В engineers отсутствуют бригады, указанные в CSV")
        return options.engineers
    if options.dataset == "control":
        return [EngineerInput(name=name) for name in sorted(names)]
    if options.engineer_count is None:
        raise ImportError("Для синтетики укажите engineers или engineer_count")
    return [EngineerInput(name=f"Инженер {n:03d}") for n in range(1, options.engineer_count + 1)]


async def resolve_coordinates(
    parsed: ParsedFile, options: ImportOptions, resolver: CoordinateResolver | None
) -> dict[str, Coordinates]:
    addresses = {parsed.office_address: "офис"}
    for request in parsed.requests:
        addresses.setdefault(request.values["address"], f"строка {request.line}")
    points = dict(options.coordinates)
    for address, location in addresses.items():
        if address in points:
            continue
        if not options.geocode or resolver is None:
            raise ImportError(f"{location}: нет координат; задайте coordinates или geocode=true")
        try:
            points[address] = await resolver(address)
        except (ImportError, GeocodingError) as exc:
            raise ImportError(f"{location}: {exc}") from None
    return points


async def write_import(
    session: AsyncSession,
    parsed: ParsedFile,
    options: ImportOptions,
    engineers: list[EngineerInput],
    points: dict[str, Coordinates],
) -> int:
    """Own the transaction: either the entire file is written or nothing is."""
    async with session.begin():
        office = points[parsed.office_address]
        statement = insert(Region).values(
            title=options.region_title,
            office_address=parsed.office_address,
            office_lat=office.lat,
            office_lon=office.lon,
        )
        region_id = await session.scalar(
            statement.on_conflict_do_update(
                index_elements=[Region.title],
                set_={
                    key: getattr(statement.excluded, key)
                    for key in ("office_address", "office_lat", "office_lon")
                },
            ).returning(Region.id)
        )
        if region_id is None:
            raise RuntimeError("Region insert did not return an id")
        engineer_ids = {}
        for engineer in sorted(engineers, key=lambda e: e.name):
            values = engineer.model_dump()
            values["skills"] = [s.value for s in engineer.skills]
            statement = insert(Engineer).values(region_id=region_id, **values)
            engineer_ids[engineer.name] = await session.scalar(
                statement.on_conflict_do_update(
                    index_elements=[Engineer.region_id, Engineer.name],
                    set_={key: getattr(statement.excluded, key) for key in values if key != "name"},
                ).returning(Engineer.id)
            )
        for request in parsed.requests:
            point = points[request.values["address"]]
            values = {
                **request.values,
                "region_id": region_id,
                "lat": point.lat,
                "lon": point.lon,
                "fact_engineer_id": engineer_ids.get(request.engineer_name),
            }
            statement = insert(Request).values(**values)
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=[Request.region_id, Request.external_id, Request.window_start],
                    set_={
                        key: getattr(statement.excluded, key)
                        for key in values
                        if key not in ("region_id", "external_id", "window_start")
                    },
                )
            )
    return region_id


async def import_csv(
    content: bytes,
    options: ImportOptions,
    session: AsyncSession,
    resolver: CoordinateResolver | None = None,
) -> dict:
    parsed = parse_csv(content, options)
    engineers = prepare_engineers(parsed, options)
    points = await resolve_coordinates(parsed, options, resolver)
    region_id = None
    if not options.dry_run:
        region_id = await write_import(session, parsed, options, engineers, points)
    return {
        "dry_run": options.dry_run,
        "region_id": region_id,
        "region": options.region_title,
        "requests_parsed": len(parsed.requests),
        "requests_written": 0 if options.dry_run else len(parsed.requests),
        "engineers_prepared": len(engineers),
        "engineers_written": 0 if options.dry_run else len(engineers),
        "blank_rows_skipped": parsed.blank_rows,
        "work_dates": sorted(
            {r.values["window_start"].date().isoformat() for r in parsed.requests}
        ),
        "work_rules": {
            key: rule.model_dump(mode="json") for key, rule in options.work_rules.items()
        },
        "engineers": [e.model_dump(mode="json") for e in engineers],
    }
