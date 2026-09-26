"""Преобразование записей хранилища в модели алгоритма."""

from app.models.domain import Engeneer, Point, Region, Skills, SkillType, Ticket, TransportType


def _value(value):
    return value.value if hasattr(value, "value") else value


def _minutes(value) -> int:
    return value.hour * 60 + value.minute


def region_from_row(row) -> Region:
    return Region(row.id, row.title, Point(row.office_lat, row.office_lon), row.office_address)


def ticket_from_row(row, public_id: str, office: Point) -> Ticket:
    return Ticket(
        id=public_id,
        point=Point(row.lat, row.lon) if row.lat is not None and row.lon is not None else office,
        duration_minutes=row.duration_min,
        work_start=_minutes(row.window_start),
        work_finish=_minutes(row.window_end),
        skill=SkillType(_value(row.skill)),
        priority=row.priority,
        required_transport=TransportType(_value(row.required_transport))
        if row.required_transport
        else None,
        address=row.address,
        district=row.district,
        equipment=getattr(row, "equipment", None),
        request_id=row.id,
    )


def engineer_from_row(row, office: Point) -> Engeneer:
    return Engeneer(
        id=row.id,
        name=row.name,
        start_point=Point(row.start_lat, row.start_lon)
        if row.start_lat is not None and row.start_lon is not None
        else office,
        work_shift_start_minutes=_minutes(row.shift_start),
        work_shift_end_minutes=_minutes(row.shift_end),
        skills=Skills([SkillType(s) for s in (row.skills or [])]),
        transport=TransportType(_value(row.transport)),
    )
