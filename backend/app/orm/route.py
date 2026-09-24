from typing import TYPE_CHECKING

from sqlalchemy import Double, ForeignKey, SmallInteger, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.orm.base import Base

if TYPE_CHECKING:
    from app.orm.engineer import Engineer
    from app.orm.plan import Plan
    from app.orm.stop import Stop


class Route(Base):
    """Маршрут одного инженера в рамках конкретного Plan."""

    __tablename__ = "route"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plan.id", ondelete="CASCADE"))
    engineer_id: Mapped[int] = mapped_column(ForeignKey("engineer.id"))

    distance_km: Mapped[float] = mapped_column(Double, default=0.0, server_default=text("0"))
    travel_min: Mapped[int] = mapped_column(SmallInteger, default=0, server_default=text("0"))
    service_min: Mapped[int] = mapped_column(SmallInteger, default=0, server_default=text("0"))
    wait_min: Mapped[int] = mapped_column(SmallInteger, default=0, server_default=text("0"))

    geometry: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))

    plan: Mapped["Plan"] = relationship(back_populates="routes")
    engineer: Mapped["Engineer"] = relationship()
    stops: Mapped[list["Stop"]] = relationship(
        back_populates="route", cascade="all, delete-orphan", order_by="Stop.seq"
    )
