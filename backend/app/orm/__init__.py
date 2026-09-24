"""Импортируем все ORM-модели здесь, чтобы они гарантированно
зарегистрировались в SQLAlchemy declarative registry до первого запроса.

Многие relationship() объявлены через строковые forward-reference
(например Mapped["Plan"]), а сам класс импортируется только под
TYPE_CHECKING — этого достаточно для тайпчекера, но не для рантайма.
Без реального импорта здесь SQLAlchemy не находит класс при ленивой
конфигурации мапперов и падает с InvalidRequestError.
"""

from app.orm.base import Base
from app.orm.engineer import Engineer
from app.orm.plan import Plan
from app.orm.region import Region
from app.orm.request import Request
from app.orm.required_transport import RequiredTransport
from app.orm.route import Route
from app.orm.route_cache import RouteCache
from app.orm.skill import Skill
from app.orm.stop import Stop
from app.orm.transport import Transport

__all__ = [
    "Base",
    "Engineer",
    "Plan",
    "Region",
    "Request",
    "RequiredTransport",
    "Route",
    "RouteCache",
    "Skill",
    "Stop",
    "Transport",
]
