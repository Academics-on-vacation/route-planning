from enum import Enum


class Point:
    def __init__(self, latitude: float, longitude: float):
        self.latitude = latitude
        self.longitude = longitude

    @property
    def coords(self) -> tuple[float, float]:
        """Координаты в порядке (широта, долгота)."""
        return (self.latitude, self.longitude)

    def __repr__(self):
        return f"{self.latitude}, {self.longitude}"


class SkillType(str, Enum):
    """Значения совпадают с колонкой skill в базе."""

    LOCAL = "local"
    INSTALL = "install"
    EMERGENCY = "emergency"


class TransportType(str, Enum):
    UNKNOWN = "unknown"
    CAR = "car"
    WALKER = "foot"
    BYCICLE = "bike"
    TRANSIT = "transit"  # пешеход с общественным транспортом


class Skills:
    def __init__(self, types: list[SkillType]):
        self.types = types

    def has(self, skill: SkillType) -> bool:
        return skill in self.types

    def __repr__(self):
        return f"{self.types}"


class Region:
    def __init__(self, id: int, title: str, office: Point, office_address: str = ""):
        self.id = id
        self.title = title
        self.office = office
        self.office_address = office_address

    def __repr__(self):
        return f"{self.id} {self.title}"


class Ticket:
    def __init__(
        self,
        id: str,
        point: Point,
        duration_minutes: int,
        work_start: int,
        work_finish: int,
        skill: SkillType = SkillType.LOCAL,
        priority: int = 100,
        required_transport: TransportType | None = None,
        address: str = "",
        district: str | None = None,
        equipment: dict | list | None = None,
        request_id: int | None = None,
    ):
        self.id = id
        # id — публичный (external_id, при коллизии с суффиксом); request_id —
        # настоящий PK таблицы request, нужен для связи stop.request_id при
        # сохранении плана в БД.
        self.request_id = request_id
        self.point = point
        self.duration_minutes = duration_minutes
        self.work_start = work_start
        self.work_finish = work_finish
        self.skill = skill
        self.priority = priority
        self.required_transport = required_transport
        self.address = address
        self.district = district
        self.equipment = equipment or {}

    def __repr__(self):
        return f"{self.id} {self.skill.value} {self.work_start}-{self.work_finish}"


class Engeneer:
    def __init__(
        self,
        id: int,
        name: str,
        start_point: Point,
        work_shift_start_minutes: int,
        work_shift_end_minutes: int,
        skills: Skills,
        transport: TransportType,
    ):
        self.id = id
        self.name = name
        self.start_point = start_point
        self.work_shift_start_minutes = work_shift_start_minutes
        self.work_shift_end_minutes = work_shift_end_minutes
        self.skills = skills
        self.transport = transport
        self.deployed = False

    def __repr__(self):
        return f"{self.id} {self.name} {self.transport.value}"


class Stop:
    def __init__(
        self,
        ticket,
        depart,
        arrive,
        start,
        end,
        travel_minutes,
        travel_km,
        frozen=False,
        moved_from=None,
    ):
        self.ticket: Ticket = ticket
        self.depart = depart
        self.arrive = arrive
        self.start = start
        self.end = end
        self.travel_minutes = travel_minutes
        self.travel_km = travel_km
        self.frozen = frozen
        self.moved_from = moved_from

    @property
    def wait_minutes(self) -> int:
        return self.start - self.arrive

    @property
    def late_minutes(self) -> int:
        """На сколько работа вылезла за правый край окна."""
        return max(0, self.end - self.ticket.work_finish)

    def __repr__(self):
        return f"{self.ticket.id} {self.start}-{self.end}"


class Route:
    """Маршрут одного исполнителя за день."""

    def __init__(self, engeneer: Engeneer, stops: list[Stop] | None = None):
        self.engeneer = engeneer
        self.stops: list[Stop] = stops or []

    @property
    def distance_km(self) -> float:
        return sum(s.travel_km for s in self.stops)

    @property
    def travel_minutes(self) -> int:
        return sum(s.travel_minutes for s in self.stops)

    @property
    def service_minutes(self) -> int:
        return sum(s.ticket.duration_minutes for s in self.stops)

    @property
    def wait_minutes(self) -> int:
        return sum(s.wait_minutes for s in self.stops)

    @property
    def finish(self) -> int | None:
        return self.stops[-1].end if self.stops else None

    def __repr__(self):
        return f"{self.engeneer.name}: {len(self.stops)} визитов"


class Unassigned:
    """Заявка без исполнителя и причина."""

    def __init__(self, ticket: Ticket, reason: str, reason_text: str):
        self.ticket = ticket
        self.reason = reason
        self.reason_text = reason_text

    def __repr__(self):
        return f"{self.ticket.id}: {self.reason_text}"


class Plan:
    """Результат алгоритма: маршруты и неназначенные заявки."""

    def __init__(self, routes: list[Route], unassigned: list[Unassigned]):
        self.routes = routes
        self.unassigned = unassigned

    @property
    def used_routes(self) -> list[Route]:
        return [r for r in self.routes if r.stops]

    def __repr__(self):
        return f"план: {len(self.used_routes)} маршрутов, {len(self.unassigned)} без исполнителя"
