from datetime import date, datetime, time, timedelta
from enum import Enum

def minutes_of(value: datetime | time) -> int:
    """Время суток -> минуты от полуночи."""
    return value.hour * 60 + value.minute


def at(day: date, minutes: int) -> str:
    """Минуты от полуночи -> ISO для фронта.

    timedelta, а не replace(hour=...): смена может кончиться после
    полуночи, и тогда дата уедет на следующий день сама."""
    return (datetime.combine(day, time.min) + timedelta(minutes=minutes)).isoformat()


def _value(x):
    """Enum базы -> строка. SQLAlchemy отдаёт то объект перечисления,
    то готовую строку — зависит от того, как строка попала в сессию."""
    return x.value if hasattr(x, "value") else x



class Point:
    def __init__(self, latitude: float, longitude: float):
        self.latitude = latitude
        self.longitude = longitude

    @property
    def coords(self) -> tuple[float, float]:
        """(широта, долгота) — в таком порядке их ждёт клиент 2ГИС."""
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

    @classmethod
    def from_row(cls, row) -> "Region":
        return cls(row.id, row.title, Point(row.office_lat, row.office_lon), row.office_address)

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "office_address": self.office_address,
            "office_lat": self.office.latitude,
            "office_lon": self.office.longitude,
        }

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
    ):
        self.id = id
        self.point = point
        self.duration_minutes = duration_minutes
        self.work_start = work_start
        self.work_finish = work_finish
        self.skill = skill
        self.priority = priority
        self.required_transport = required_transport
        self.address = address
        self.district = district

    @classmethod
    def from_row(cls, row, public_id: str) -> "Ticket":
        return cls(
            id=public_id,
            point=Point(row.lat, row.lon),
            duration_minutes=row.duration_min,
            work_start=minutes_of(row.window_start),
            work_finish=minutes_of(row.window_end),
            skill=SkillType(_value(row.skill)),
            priority=row.priority,
            required_transport=(
                TransportType(_value(row.required_transport)) if row.required_transport else None
            ),
            address=row.address,
            district=row.district,
        )

    def to_json(self, day: date) -> dict:
        return {
            "id": self.id,
            "lat": self.point.latitude,
            "lon": self.point.longitude,
            "address": self.address,
            "district": self.district,
            "skill": self.skill.value,
            "duration_min": self.duration_minutes,
            "window_start": at(day, self.work_start),
            "window_end": at(day, self.work_finish),
            "priority": self.priority,
            "required_transport": (
                self.required_transport.value if self.required_transport else None
            ),
        }

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

    @classmethod
    def from_row(cls, row, office: Point) -> "Engeneer":
        # Старт — офис
        return cls(
            id=row.id,
            name=row.name,
            start_point=office,
            work_shift_start_minutes=minutes_of(row.shift_start),
            work_shift_end_minutes=minutes_of(row.shift_end),
            skills=Skills([SkillType(s) for s in (row.skills or [])]),
            transport=TransportType(_value(row.transport)),
        )

    def to_json(self, day: date) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "skills": [s.value for s in self.skills.types],
            "transport": self.transport.value,
            "shift_start": at(day, self.work_shift_start_minutes),
            "shift_end": at(day, self.work_shift_end_minutes),
        }

    def __repr__(self):
        return f"{self.id} {self.name} {self.transport.value}"




class Stop:
    def __init__(self, ticket, depart, arrive, start, end, travel_minutes, travel_km):
        self.ticket: Ticket = ticket
        self.depart = depart
        self.arrive = arrive
        self.start = start
        self.end = end
        self.travel_minutes = travel_minutes
        self.travel_km = travel_km

    @property
    def wait_minutes(self) -> int:
        return self.start - self.arrive

    @property
    def late_minutes(self) -> int:
        """На сколько работа вылезла за правый край окна."""
        return max(0, self.end - self.ticket.work_finish)

    def to_json(self, day: date, seq: int) -> dict:
        return {
            "seq": seq,
            "request_id": str(self.ticket.id),
            "arrive_at": at(day, self.arrive),
            "start_at": at(day, self.start),
            "end_at": at(day, self.end),
            "wait_min": self.wait_minutes,
            "travel_min": self.travel_minutes,
            "travel_km": self.travel_km,
        }

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

    def to_json(self, day: date) -> dict:
        return {
            "engineer_id": self.engeneer.id,
            "engineer_name": self.engeneer.name,
            "start": {
                "lat": self.engeneer.start_point.latitude,
                "lon": self.engeneer.start_point.longitude,
                "at": at(day, self.engeneer.work_shift_start_minutes),
            },
            "stops": [s.to_json(day, i + 1) for i, s in enumerate(self.stops)],
            "distance_km": round(self.distance_km, 1),
            "travel_min": self.travel_minutes,
            "service_min": self.service_minutes,
            "wait_min": self.wait_minutes,
            "finish_at": at(day, self.finish) if self.finish else None,
            "geometry": None,
        }

    def __repr__(self):
        return f"{self.engeneer.name}: {len(self.stops)} визитов"


class Unassigned:
    """Заявка без исполнителя и причина. """

    def __init__(self, ticket: Ticket, reason: str, reason_text: str):
        self.ticket = ticket
        self.reason = reason
        self.reason_text = reason_text

    def to_json(self) -> dict:
        return {
            "request_id": str(self.ticket.id),
            "reason": self.reason,
            "reason_text": self.reason_text,
        }

    def __repr__(self):
        return f"{self.ticket.id}: {self.reason_text}"



class Plan:
    """Результат планирования: маршруты, остаток и цифры."""

    def __init__(self, routes: list[Route], unassigned: list[Unassigned], meta: dict):
        self.routes = routes
        self.unassigned = unassigned
        self.meta = meta

    @property
    def used_routes(self) -> list[Route]:
        return [r for r in self.routes if r.stops]

    def metrics(self) -> dict:
        used = self.used_routes
        stops = [s for r in used for s in r.stops]
        return {
            "requests_total": len(stops) + len(self.unassigned),
            "assigned": len(stops),
            "unassigned": len(self.unassigned),
            "engineers_used": len(used),
            "total_distance_km": round(sum(r.distance_km for r in used), 1),
            "total_travel_min": sum(r.travel_minutes for r in used),
            "total_wait_min": sum(r.wait_minutes for r in used),
            # Начали внутри окна — жёсткое условие солвера, тут всегда 0.
            "window_violations": sum(
                1 for s in stops if not (s.ticket.work_start <= s.start <= s.ticket.work_finish)
            ),
            # А это спорные визиты: начали в окне, закончили после него.
            "finish_after_window": sum(1 for s in stops if s.late_minutes > 0),
        }

    def to_json(self, region_id: int, day: date) -> dict:
        return {
            "region_id": region_id,
            "work_date": day.isoformat(),
            "routes": [r.to_json(day) for r in self.used_routes],
            "unassigned": [u.to_json() for u in self.unassigned],
            "metrics": self.metrics(),
            "meta": {
                **self.meta,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
            },
        }

    def __repr__(self):
        return f"план: {len(self.used_routes)} маршрутов, {len(self.unassigned)} без исполнителя"
