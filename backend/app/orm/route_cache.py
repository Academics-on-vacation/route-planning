from datetime import datetime

from sqlalchemy import Double, Enum, Index, SmallInteger, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.orm.base import Base
from app.orm.transport import Transport


class RouteCache(Base):
    __tablename__ = "route_cache"
    __table_args__ = (
        UniqueConstraint(
            "transport",
            "from_lat",
            "from_lon",
            "to_lat",
            "to_lon",
            "departure_at",
            name="uq_route_cache_leg",
        ),
        Index("ix_route_cache_departure", "departure_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    transport: Mapped[Transport] = mapped_column(
        Enum(Transport, name="transport", native_enum=False, length=16, create_constraint=False)
    )
    from_lat: Mapped[float] = mapped_column(Double)
    from_lon: Mapped[float] = mapped_column(Double)
    to_lat: Mapped[float] = mapped_column(Double)
    to_lon: Mapped[float] = mapped_column(Double)

    departure_at: Mapped[datetime]

    minutes: Mapped[int] = mapped_column(SmallInteger)
    km: Mapped[float] = mapped_column(Double)

    payload: Mapped[dict] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
