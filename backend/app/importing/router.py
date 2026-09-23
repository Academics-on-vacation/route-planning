from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.geocoder import CoordinateResolver, yandex_resolver
from app.importing.csv_parser import MAX_FILE_BYTES
from app.importing.schemas import ImportError, ImportOptions
from app.importing.service import import_csv

router = APIRouter(prefix="/api/imports", tags=["imports"])


def get_coordinate_resolver() -> CoordinateResolver:
    return yandex_resolver(settings.yandex_geocoder_api_key)


@router.post("/csv")
async def upload_csv(
    file: Annotated[UploadFile, File(description="CSV с разделителем ;")],
    options: Annotated[str, Form(description="JSON настроек импорта; см. backend/IMPORT.md")],
    session: Annotated[AsyncSession, Depends(get_session)],
    resolver: Annotated[CoordinateResolver, Depends(get_coordinate_resolver)],
) -> dict:
    try:
        config = ImportOptions.model_validate_json(options)
    except ValidationError as exc:
        raise HTTPException(
            422, detail=exc.errors(include_input=False, include_context=False)
        ) from None
    try:
        content = await file.read(MAX_FILE_BYTES + 1)
    finally:
        await file.close()
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(413, "Размер CSV превышает 5 МиБ")
    try:
        return await import_csv(content, config, session, resolver)
    except ImportError as exc:
        raise HTTPException(422, str(exc)) from None
    except IntegrityError:
        raise HTTPException(409, "Импорт отменён: данные нарушают ограничения БД") from None
