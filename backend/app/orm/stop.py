from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Double, ForeignKey, Index, SmallInteger, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.orm.base import Base

if TYPE_CHECKING:
    from app.orm.request import Request
    from app.orm.route import Route


class Stop(Base):
    """Один визит в маршруте — ссылается на заявку по её настоящему PK."""

    __tablename__ = "stop"
    __table_args__ = (Index("ix_stop_route", "route_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("route.id", ondelete="CASCADE"))
    request_id: Mapped[int] = mapped_column(ForeignKey("request.id", ondelete="CASCADE"))

    seq: Mapped[int] = mapped_column(SmallInteger)

    depart_at: Mapped[datetime]
    arrive_at: Mapped[datetime]
    start_at: Mapped[datetime]
    end_at: Mapped[datetime]

    travel_min: Mapped[int] = mapped_column(SmallInteger)
    travel_km: Mapped[float] = mapped_column(Double)

    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))

    route: Mapped["Route"] = relationship(back_populates="stops")
    request: Mapped["Request"] = relationship()
