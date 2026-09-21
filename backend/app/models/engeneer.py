from enum import Enum

from .point import Point


class SkillType(Enum):
    UNKNOWN = 0


class Skills:
    def __init__(self, types: list[SkillType]):
        self.types = types

    def __str__(self):
        return f"{self.types}"

    def __repr__(self):
        return self.__str__()


class TransportType(Enum):
    UNKNOWN = 0
    CAR = 1  # автомобилист
    WALKER = 2  # пешеход
    BYCICLE = 3  # велосипедист
    PUBLIC_TRANSPORT = 4  # общественный транспорт


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

    def __str__(self):
        return f"{self.id} {self.name} {self.start_point} {self.work_shift_start_minutes} {self.work_shift_end_minutes} {self.skills} {self.transport}"

    def __repr__(self):
        return self.__str__()
