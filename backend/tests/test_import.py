import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import httpx
import pytest
import requests
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from yandex_geocoder import NothingFound

from app.geocoder import GeocodingError, yandex_resolver
from app.importing.csv_parser import parse_csv, parse_datetime
from app.importing.schemas import Coordinates, ImportError, ImportOptions
from app.importing.service import import_csv, prepare_engineers, resolve_coordinates, write_import
from app.orm.engineer import Engineer
from app.orm.region import Region
from app.orm.request import Request

HEADER = "Заявка;Тип заявки BK;Тип заявки HD;Начало;Окончание;Район;Адрес"
ROWS = (
    "001;Подключение;Заявка на подключение;17.08.2026 10:00;17.08.2026 12:00;Район;Адрес А",
    "002;Локальная заявка;Нет линка;17.08.2026 12:00;17.08.2026 14:00;Район;Адрес Б",
)
CSV = ("\n".join([HEADER, *ROWS, ";;;;;;", "Адрес Офиса;Офис;;;;;"])).encode()


def options(**overrides) -> ImportOptions:
    return ImportOptions.model_validate(
        {
            "region": "import-test",
            "dataset": "synthetic",
            "engineer_count": 2,
            "coordinates": {
                "Офис": {"lat": 55.75, "lon": 37.62},
                "Адрес А": {"lat": 55.751, "lon": 37.621},
                "Адрес Б": {"lat": 55.752, "lon": 37.622},
            },
            **overrides,
        }
    )


def test_csv_normalization():
    parsed = parse_csv(b"\xef\xbb\xbf" + CSV, options())
    assert parsed.office_address == "Офис"
    assert parsed.blank_rows == 1
    assert parsed.requests[0].values["external_id"] == "001"
    assert parsed.requests[0].values["duration_min"] == 70
    assert parsed.requests[1].values["skill"] == "local"
    assert parsed.requests[0].values["window_start"].isoformat() == "2026-08-17T10:00:00"
    cp1251 = CSV.decode().encode("cp1251")
    assert len(parse_csv(cp1251, options(encoding="cp1251")).requests) == 2


def test_quoted_csv_and_control():
    content = (
        HEADER
        + ";Бригада;Статус BK;Гигабитное подключение;Подключение\r\n"
        + ROWS[0].replace("Адрес А", '"Адрес; с разделителем"')
        + ";Бригада А;Отправлена;Да;FMC\r\n"
    ).encode()
    config = options(dataset="control", engineer_count=None, office_address="Офис")
    parsed = parse_csv(content, config)
    row = parsed.requests[0]
    assert row.values["address"] == "Адрес; с разделителем"
    assert row.values["equipment"] == {"gigabit": True, "connection": "FMC"}
    assert row.values["status"] == "Отправлена"
    assert prepare_engineers(parsed, config)[0].name == "Бригада А"


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("17.08.2026 10:00", "31.02.2026 10:00", "ожидается дата"),
        ("17.08.2026 12:00", "17.08.2026 09:00", "конец окна"),
        ("17.08.2026 14:00", "18.08.2026 14:00", "через полночь"),
        ("Подключение", "Новый тип", "work_rules"),
        ("Заявка;", "Номер;", "отсутствуют колонки"),
        ("Адрес А", "Адрес А;лишнее поле", "число полей"),
    ],
)
def test_bad_rows_rejected(old, new, message):
    with pytest.raises(ImportError, match=message):
        parse_csv(CSV.decode().replace(old, new, 1).encode(), options())


def test_duplicates_and_dataset_mismatch():
    with pytest.raises(ImportError, match="повтор заявки"):
        parse_csv(CSV + b"\n" + ROWS[0].encode(), options())
    with pytest.raises(ImportError, match="dataset"):
        parse_csv(CSV, options(dataset="control", engineer_count=None))
    with pytest.raises(ImportError, match="engineers или engineer_count"):
        prepare_engineers(parse_csv(CSV, options()), options(engineer_count=None))
    with pytest.raises(ImportError, match="кодировка"):
        parse_csv(CSV.decode().encode("cp1251"), options())


def test_datetime_and_coordinates_validation():
    assert parse_datetime(" 17.08.2026 09:05 ", 2, "Начало").tzinfo is None
    with pytest.raises(ValueError):
        Coordinates(lat=float("nan"), lon=37)
    with pytest.raises(ValueError):
        Coordinates(lat=55, lon=181)
    with pytest.raises(ValueError):
        options(engineer_count=None, engineers=[{"name": "А", "skills": []}])


def test_dry_run_deduplicates_geocoding_without_database():
    calls = []

    async def resolve(address):
        calls.append(address)
        return Coordinates(lat=55.75, lon=37.62)

    content = CSV.replace("Адрес Б".encode(), "Адрес А".encode())
    config = options(coordinates={}, geocode=True, dry_run=True)
    session = Mock(spec=AsyncSession)
    result = asyncio.run(import_csv(content, config, session, resolve))
    assert session.mock_calls == []
    assert calls == ["Офис", "Адрес А"]
    assert result["requests_parsed"] == 2
    assert result["requests_written"] == 0
    assert result["region_id"] is None
    with pytest.raises(ImportError, match="нет координат"):
        asyncio.run(import_csv(CSV, options(coordinates={}), session))
    assert session.mock_calls == []


def test_upload_validation(monkeypatch):
    monkeypatch.setenv("DB_PASSWORD", "test-only-password")
    from app.main import app

    with TestClient(app) as client:
        response = client.post(
            "/api/imports/csv",
            files={"file": ("test.csv", CSV)},
            data={"options": options(dry_run=True).model_dump_json()},
        )
        assert response.status_code == 200, response.text
        response = client.post(
            "/api/imports/csv", files={"file": ("test.csv", CSV)}, data={"options": "{"}
        )
        assert response.status_code == 422
        response = client.post(
            "/api/imports/csv",
            files={"file": ("test.csv", b"x" * (5 * 1024 * 1024 + 1))},
            data={"options": options().model_dump_json()},
        )
        assert response.status_code == 413


def test_geocoder_coordinates_and_errors(monkeypatch):
    async def resolve(key):
        return await yandex_resolver(key)("Тестовый адрес")

    coordinates = Mock(return_value=(37.62, 55.75))
    monkeypatch.setattr("app.geocoder.Client.coordinates", coordinates)
    point = asyncio.run(resolve("test-key"))
    assert point == Coordinates(lat=55.75, lon=37.62)
    coordinates.assert_called_once_with("Тестовый адрес")
    coordinates.side_effect = NothingFound("Тестовый адрес")
    with pytest.raises(GeocodingError, match="не нашёл"):
        asyncio.run(resolve("test-key"))
    coordinates.side_effect = requests.RequestException("https://provider/?apikey=test-key")
    with pytest.raises(GeocodingError) as error:
        asyncio.run(resolve("test-key"))
    assert "test-key" not in str(error.value)
    with pytest.raises(GeocodingError, match="YANDEX_GEOCODER_API_KEY"):
        asyncio.run(resolve(None))


def test_upload_uses_shared_geocoder(monkeypatch):
    monkeypatch.setenv("DB_PASSWORD", "test-only-password")
    from app.importing.router import settings
    from app.main import app

    monkeypatch.setattr(settings, "yandex_geocoder_api_key", "test-key")
    coordinates = Mock(return_value=(37.62, 55.75))
    monkeypatch.setattr("app.geocoder.Client.coordinates", coordinates)
    config = options(dry_run=True, geocode=True, coordinates={})
    with TestClient(app) as client:
        response = client.post(
            "/api/imports/csv",
            files={"file": ("test.csv", CSV)},
            data={"options": config.model_dump_json()},
        )
        assert response.status_code == 200, response.text
        assert coordinates.call_count == 3
        coordinates.side_effect = NothingFound("Тестовый адрес")
        response = client.post(
            "/api/imports/csv",
            files={"file": ("test.csv", CSV)},
            data={"options": config.model_dump_json()},
        )
        assert response.status_code == 422
        assert "офис" in response.json()["detail"]
        assert "не нашёл" in response.json()["detail"]


def test_batch_uses_shared_geocoder_and_continues_after_failure(monkeypatch):
    monkeypatch.setenv("DB_PASSWORD", "test-only-password")
    from app.config import settings
    from app.geocoder import geocode_all_requests

    monkeypatch.setattr(settings, "yandex_geocoder_api_key", "test-key")
    rows = [
        SimpleNamespace(id=1, address="А", lat=55.0, lon=37.0),
        SimpleNamespace(id=2, address="Б", lat=55.0, lon=37.0),
    ]
    session = AsyncMock()
    session.scalars.return_value = Mock()
    session.scalars.return_value.all.return_value = rows

    @asynccontextmanager
    async def session_factory():
        yield session

    monkeypatch.setattr("app.db.session_factory", session_factory)
    geocode = AsyncMock(
        side_effect=[GeocodingError("Адрес не найден"), Coordinates(lat=55.75, lon=37.62)]
    )
    monkeypatch.setattr("app.geocoder.geocode_address", geocode)
    asyncio.run(geocode_all_requests())
    assert geocode.await_args_list == [call("А", "test-key"), call("Б", "test-key")]
    assert (rows[0].lat, rows[0].lon) == (55.0, 37.0)
    assert (rows[1].lat, rows[1].lon) == (55.75, 37.62)
    session.commit.assert_awaited_once()


def test_documented_example():
    folder = Path(__file__).resolve().parents[1] / "examples"
    config = ImportOptions.model_validate_json((folder / "import-options.json").read_text())
    result = asyncio.run(
        import_csv((folder / "import.csv").read_bytes(), config, Mock(spec=AsyncSession))
    )
    assert result["requests_parsed"] == 2
    assert result["dry_run"] is True


def test_available_source_files():
    """Optional local check of all supplied files; fixture CSVs above always run in CI."""
    folder = Path(__file__).resolve().parents[2] / "notes" / "Обезличивание"
    files = list(folder.glob("*.csv"))
    if not files:
        pytest.skip("Local source files are not distributed with the repository")
    for file in files:
        control = "Контрольное" in file.name
        config = options(
            dataset="control" if control else "synthetic",
            engineer_count=None if control else 2,
            office_address="Офис" if control else None,
        )
        parsed = parse_csv(file.read_bytes(), config)
        assert parsed.requests, file.name


@pytest.mark.skipif(
    os.environ.get("RUN_IMPORT_TESTS") != "1",
    reason="requires disposable PostgreSQL with migrations applied",
)
def test_postgres_upload_repeat_plan_and_rollback(monkeypatch):
    monkeypatch.setenv("DB_PASSWORD", os.environ["DB_PASSWORD"])
    from app.db import get_session
    from app.main import app

    async def run():
        url = URL.create(
            "postgresql+asyncpg",
            username=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            host=os.environ["DB_HOST"],
            port=int(os.environ["DB_PORT"]),
            database=os.environ["DB_NAME"],
        )
        engine = create_async_engine(url)
        try:
            async with engine.connect() as connection:
                outer = await connection.begin()

                async def session_dependency():
                    async with AsyncSession(
                        bind=connection, join_transaction_mode="create_savepoint"
                    ) as session:
                        yield session

                app.dependency_overrides[get_session] = session_dependency
                try:
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app), base_url="http://test"
                    ) as client:
                        config = options()

                        async def upload(content=CSV, config=config):
                            return await client.post(
                                "/api/imports/csv",
                                files={"file": ("data.csv", content)},
                                data={"options": config.model_dump_json()},
                            )

                        first = await upload()
                        assert first.status_code == 200, first.text
                        region_id = first.json()["region_id"]
                        config.work_rules["Подключение"].duration_min = 65
                        second = await upload(config=config)
                        assert second.status_code == 200, second.text
                        assert second.json()["region_id"] == region_id
                        assert (
                            await connection.scalar(
                                select(func.count())
                                .select_from(Request)
                                .where(Request.region_id == region_id)
                            )
                            == 2
                        )
                        assert (
                            await connection.scalar(
                                select(func.count())
                                .select_from(Engineer)
                                .where(Engineer.region_id == region_id)
                            )
                            == 2
                        )
                        assert (
                            await connection.scalar(
                                select(Request.duration_min).where(
                                    Request.region_id == region_id, Request.external_id == "001"
                                )
                            )
                            == 65
                        )
                        plan = await client.post(
                            "/api/plan",
                            json={"region_id": region_id, "options": {"use_api": False}},
                        )
                        assert plan.status_code == 200, plan.text
                        assert plan.json()["metrics"]["assigned"] == 2

                        control = (
                            HEADER + ";Бригада;Статус BK\n" + ROWS[0] + ";Бригада А;Отправлена\n"
                        ).encode()
                        response = await upload(
                            control,
                            options(dataset="control", engineer_count=None, office_address="Офис"),
                        )
                        assert response.status_code == 200, response.text
                        assert response.json()["region_id"] != region_id
                        fact_id = await connection.scalar(
                            select(Request.fact_engineer_id).where(
                                Request.region_id == response.json()["region_id"]
                            )
                        )
                        assert fact_id is not None
                        assert (
                            await connection.scalar(
                                select(Engineer.name).where(Engineer.id == fact_id)
                            )
                            == "Бригада А"
                        )

                        bad = await upload(CSV.replace(b"17.08.2026", b"31.02.2026"))
                        assert bad.status_code == 422
                        dry = await upload(config=options(region="dry", dry_run=True))
                        assert dry.status_code == 200, dry.text
                        assert (
                            await connection.scalar(
                                select(Region.id).where(Region.title == "dry [synthetic]")
                            )
                            is None
                        )

                        # Exercise the real local CSV variants against PostgreSQL as well.
                        # Coordinates are explicit test doubles, never external API results.
                        folder = Path(__file__).resolve().parents[2] / "notes" / "Обезличивание"
                        for index, file in enumerate(sorted(folder.glob("*.csv"))):
                            control_source = "Контрольное" in file.name
                            source_options = options(
                                region=f"source-test-{index}",
                                dataset="control" if control_source else "synthetic",
                                engineer_count=None if control_source else 2,
                                office_address="Офис" if control_source else None,
                            )
                            source = parse_csv(file.read_bytes(), source_options)
                            source_options.coordinates = {
                                address: Coordinates(lat=55.75, lon=37.62)
                                for address in [
                                    source.office_address,
                                    *[r.values["address"] for r in source.requests],
                                ]
                            }
                            loaded = await upload(file.read_bytes(), source_options)
                            assert loaded.status_code == 200, loaded.text
                            loaded_id = loaded.json()["region_id"]
                            repeated = await upload(file.read_bytes(), source_options)
                            assert repeated.status_code == 200, repeated.text
                            assert await connection.scalar(
                                select(func.count())
                                .select_from(Request)
                                .where(Request.region_id == loaded_id)
                            ) == len(source.requests)

                    # Force a DB constraint error on the second request AFTER the first
                    # request and engineers were updated, and verify the whole rollback.
                    parsed = parse_csv(CSV, config)
                    parsed.requests[0].values["duration_min"] = 99
                    parsed.requests[1].values["duration_min"] = -1
                    points = await resolve_coordinates(parsed, config, None)
                    async with AsyncSession(
                        bind=connection, join_transaction_mode="create_savepoint"
                    ) as session:
                        with pytest.raises(IntegrityError):
                            await write_import(
                                session, parsed, config, prepare_engineers(parsed, config), points
                            )
                    assert (
                        await connection.scalar(
                            select(Request.duration_min).where(
                                Request.region_id == region_id, Request.external_id == "001"
                            )
                        )
                        == 65
                    )
                    assert await connection.scalar(text("SELECT 1")) == 1
                finally:
                    app.dependency_overrides.pop(get_session, None)
                    await outer.rollback()
        finally:
            await engine.dispose()

    asyncio.run(run())
