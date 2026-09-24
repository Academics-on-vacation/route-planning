from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.orm.base import Base

if TYPE_CHECKING:
    from app.orm.region import Region
    from app.orm.route import Route


class Plan(Base):
    """Снимок посчитанного плана на день. Живёт для истории/перепланирования:
    is_active=false у старых версий, а не удаление."""

    __tablename__ = "plan"
    __table_args__ = (
        Index(
            "uq_plan_active_per_day",
            "region_id",
            "work_date",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("region.id", ondelete="CASCADE"))
    work_date: Mapped[date] = mapped_column(Date)

    solver: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(16))

    metrics: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    meta: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))

    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    region: Mapped["Region"] = relationship(back_populates="plans")
    routes: Mapped[list["Route"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )
