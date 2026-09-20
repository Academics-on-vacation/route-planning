from enum import Enum

from point import Point


class WorkType(Enum):
    UNKNOWN = 0


class Priority(Enum):
    UNKNOWN = 0
    COMMON = 1  # обычная
    EMERGENCY = 2  # срочная


class Ticket:
    def __init__(
        self,
        id: int,
        point: Point,
        duration_minutes: int,
        work_start: int,
        work_finish: int,
        work_type: WorkType,
    ):
        self.id = id
        self.point = point
        self.duration_minutes = duration_minutes
        self.work_start = work_start
        self.work_finish = work_finish
        self.work_type = work_type

    def __str__(self):
        return f"{self.id} {self.point} {self.duration_minutes} {self.work_start} {self.work_finish} {self.work_type}"

    def __repr__(self):
        return self.__str__()
