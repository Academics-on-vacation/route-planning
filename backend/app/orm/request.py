from datetime import time, datetime

from sqlalchemy import (
    CheckConstraint,
    Double,
    Enum,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.orm.base import Base
from app.orm.transport import Transport
from app.orm.required_transport import RequiredTransport
from app.orm.skill import Skill

class Request(Base):
    __tablename__ = "request"
    __table_args__ = (
        UniqueConstraint("region_id", "external_id", "window_start"),
        CheckConstraint("duration_min > 0", name="ck_request_duration"),
        CheckConstraint("window_end > window_start", name="ck_request_window"),
        Index("ix_request_planning", "region_id", "window_start"),
        Index("ix_request_skill", "skill"),
        Index("ix_request_fact", "fact_engineer_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("region.id", ondelete="CASCADE"))
    external_id: Mapped[str] = mapped_column(String(32))

    address: Mapped[str]
    district: Mapped[str | None] = mapped_column(String(128))
    lat: Mapped[float] = mapped_column(Double)
    lon: Mapped[float] = mapped_column(Double)

    work_type: Mapped[str] = mapped_column(String(48))
    hd_type: Mapped[str | None] = mapped_column(String(128))
    skill: Mapped[Skill] = mapped_column(
        Enum(Skill, name="skill", native_enum=False, length=16, create_constraint=False)
    )
    duration_min: Mapped[int] = mapped_column(SmallInteger)

    window_start: Mapped[datetime]
    window_end: Mapped[datetime]

    priority: Mapped[int] = mapped_column(SmallInteger, default=100, server_default=text("100"))

    required_transport: Mapped[RequiredTransport | None] = mapped_column(
        Enum(
            RequiredTransport,
            name="required_transport",
            native_enum=False,
            length=16,
            create_constraint=False,
        )
    )
    equipment: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))

    status: Mapped[str | None] = mapped_column(String(32))
    fact_engineer_id: Mapped[int | None] = mapped_column(
        ForeignKey("engineer.id", ondelete="SET NULL")
    )

    region: Mapped["Region"] = relationship(back_populates="requests")
    fact_engineer: Mapped["Engineer | None"] = relationship(back_populates="fact_requests")

    is_active: Mapped[bool] = mapped_column(default=True)
