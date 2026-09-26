"""Результат прикладного сценария. Солвер возвращает только вложенный Plan."""

from dataclasses import dataclass, field
from datetime import date, datetime

from app.models.domain import Plan
from app.solver.evaluation import PlanMetrics


@dataclass
class PlanningResult:
    region_id: int
    work_date: date | None
    plan: Plan
    metrics: PlanMetrics | None = None
    metadata: dict = field(default_factory=dict)
    geometries: dict[int, list[list[float]] | None] = field(default_factory=dict)
    generated_at: datetime = field(default_factory=datetime.now)
