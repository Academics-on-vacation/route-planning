from typing import TYPE_CHECKING

from sqlalchemy import (
    Double,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.orm.base import Base

if TYPE_CHECKING:
    from app.orm.engineer import Engineer
    from app.orm.request import Request


class Region(Base):
    __tablename__ = "region"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(128), unique=True)
    office_address: Mapped[str]
    office_lat: Mapped[float] = mapped_column(Double)
    office_lon: Mapped[float] = mapped_column(Double)

    engineers: Mapped[list["Engineer"]] = relationship(
        back_populates="region", cascade="all, delete-orphan"
    )
    requests: Mapped[list["Request"]] = relationship(
        back_populates="region", cascade="all, delete-orphan"
    )
