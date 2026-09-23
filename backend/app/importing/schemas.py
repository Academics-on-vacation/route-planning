from datetime import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.geocoder import Coordinates
from app.orm.skill import Skill
from app.orm.transport import Transport


class ImportError(ValueError):
    """An actionable import error, safe to expose through the API."""


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class WorkRule(InputModel):
    skill: Skill
    duration_min: int = Field(gt=0, le=32767)
    priority: int = Field(default=100, ge=0, le=32767)


def default_work_rules() -> dict[str, WorkRule]:
    # Technical work + documents; travel is calculated separately by the solver.
    return {
        "Подключение": WorkRule(skill=Skill.install, duration_min=70),
        "Дозаказ": WorkRule(skill=Skill.install, duration_min=20),
        "Локальная заявка": WorkRule(skill=Skill.local, duration_min=30),
        "Глобальная проблема": WorkRule(skill=Skill.emergency, duration_min=80, priority=0),
    }


class EngineerInput(InputModel):
    name: str = Field(min_length=1, max_length=128)
    skills: list[Skill] = Field(default_factory=lambda: list(Skill), min_length=1)
    transport: Transport = Transport.transit
    shift_start: time = time(9)
    shift_end: time = time(22)

    @model_validator(mode="after")
    def validate_shift(self):
        if self.shift_start.tzinfo or self.shift_end.tzinfo:
            raise ValueError("Смена задаётся местным временем без часового пояса")
        if self.shift_end <= self.shift_start:
            raise ValueError("Конец смены должен быть позже начала")
        return self


class ImportOptions(InputModel):
    region: str = Field(min_length=1, max_length=100)
    dataset: Literal["synthetic", "control"]
    office_address: str | None = Field(default=None, min_length=1, max_length=2000)
    coordinates: dict[str, Coordinates] = Field(default_factory=dict)
    geocode: bool = False
    dry_run: bool = False
    encoding: Literal["utf-8-sig", "cp1251"] = "utf-8-sig"
    engineers: list[EngineerInput] = Field(default_factory=list, max_length=1000)
    engineer_count: int | None = Field(default=None, ge=1, le=1000)
    work_rules: dict[str, WorkRule] = Field(default_factory=default_work_rules)

    @model_validator(mode="after")
    def validate_engineers(self):
        names = [e.name for e in self.engineers]
        if len(names) != len(set(names)):
            raise ValueError("Имена инженеров должны быть уникальны")
        if self.engineer_count is not None and (self.engineers or self.dataset == "control"):
            raise ValueError("engineer_count применяется только к синтетике без списка engineers")
        return self

    @property
    def region_title(self) -> str:
        # Existing schema has no scenario column: isolate datasets as separate regions.
        return f"{self.region} [{self.dataset}]"
