from datetime import time
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Double,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.orm.base import Base
from app.orm.transport import Transport

if TYPE_CHECKING:
    from app.orm.region import Region
    from app.orm.request import Request


class Engineer(Base):
    __tablename__ = "engineer"
    __table_args__ = (
        UniqueConstraint("region_id", "name"),
        CheckConstraint("shift_end > shift_start", name="ck_engineer_shift"),
        Index("ix_engineer_region", "region_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("region.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(128))

    transport: Mapped[Transport] = mapped_column(
        Enum(Transport, name="transport", native_enum=False, length=16, create_constraint=False),
        default=Transport.transit,
        server_default=Transport.transit.value,
    )

    skills: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))

    shift_start: Mapped[time] = mapped_column(default=time(9, 0), server_default=text("'09:00'"))
    shift_end: Mapped[time] = mapped_column(default=time(22, 0), server_default=text("'22:00'"))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))

    start_lat: Mapped[float | None] = mapped_column(Double, nullable=True)
    start_lon: Mapped[float | None] = mapped_column(Double, nullable=True)

    region: Mapped["Region"] = relationship(back_populates="engineers")
    fact_requests: Mapped[list["Request"]] = relationship(back_populates="fact_engineer")
