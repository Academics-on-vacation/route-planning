from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.orm.engineer import Engineer
from app.orm.request import Request
from app.orm.required_transport import RequiredTransport
from app.orm.skill import Skill


class RequestCreate(BaseModel):
    """Тело POST /api/regions/{region_id}/requests."""

    external_id: str = Field(min_length=1, max_length=32)
    address: str = Field(min_length=1)
    district: str | None = Field(default=None, max_length=128)
    lat: float | None = None
    lon: float | None = None
    work_type: str = Field(min_length=1, max_length=48)
    hd_type: str | None = Field(default=None, max_length=128)
    skill: Skill
    duration_min: int = Field(gt=0)
    window_start: datetime
    window_end: datetime
    priority: int = 100
    required_transport: RequiredTransport | None = None
    equipment: dict = Field(default_factory=dict)
    status: str | None = None

    @field_validator("window_start", "window_end", mode="after")
    @classmethod
    def _drop_timezone(cls, value: datetime) -> datetime:
        """В БД window_* — naive TIMESTAMP (локальное время, без зоны),
        как и везде в системе (см. minutes_of/at в app/models/domain.py).
        Если клиент прислал дату с зоной (например, "...Z" из Swagger) —
        просто отбрасываем tzinfo, а не конвертируем: число часов/минут,
        которое ввёл клиент, и есть локальное время."""
        return value.replace(tzinfo=None) if value.tzinfo is not None else value

    @model_validator(mode="after")
    def _check_window(self) -> "RequestCreate":
        if self.window_end <= self.window_start:
            raise ValueError("window_end должен быть позже window_start")
        return self

    @model_validator(mode="after")
    def _check_coords_pair(self) -> "RequestCreate":
        if (self.lat is None) != (self.lon is None):
            raise ValueError("lat и lon нужно передавать вместе, либо не передавать вовсе")
        return self


class EngineerStartPointUpdate(BaseModel):
    """Тело PATCH /api/engineers/{engineer_id}. Меняет только точку старта."""

    start_lat: float | None = None
    start_lon: float | None = None

    @model_validator(mode="after")
    def _check_coords_pair(self) -> "EngineerStartPointUpdate":
        if (self.start_lat is None) != (self.start_lon is None):
            raise ValueError("start_lat и start_lon нужно передавать вместе, либо оба null")
        return self


def engineer_to_json(row: Engineer) -> dict:
    """Полная сериализация инженера для ручек управления (без привязки к дню)."""
    return {
        "id": row.id,
        "region_id": row.region_id,
        "name": row.name,
        "transport": row.transport.value if hasattr(row.transport, "value") else row.transport,
        "skills": row.skills,
        "shift_start": row.shift_start.isoformat(),
        "shift_end": row.shift_end.isoformat(),
        "start_lat": row.start_lat,
        "start_lon": row.start_lon,
        "is_active": row.is_active,
    }


def request_to_json(row: Request) -> dict:
    """Полная сериализация заявки для ручек создания/управления."""
    return {
        "id": row.id,
        "region_id": row.region_id,
        "external_id": row.external_id,
        "address": row.address,
        "district": row.district,
        "lat": row.lat,
        "lon": row.lon,
        "work_type": row.work_type,
        "hd_type": row.hd_type,
        "skill": row.skill.value if hasattr(row.skill, "value") else row.skill,
        "duration_min": row.duration_min,
        "window_start": row.window_start.isoformat(),
        "window_end": row.window_end.isoformat(),
        "priority": row.priority,
        "required_transport": (row.required_transport.value if row.required_transport else None),
        "equipment": row.equipment,
        "status": row.status,
        "fact_engineer_id": row.fact_engineer_id,
        "is_active": row.is_active,
    }
