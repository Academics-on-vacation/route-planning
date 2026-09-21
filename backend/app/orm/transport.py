import enum


class Transport(str, enum.Enum):
    transit = "transit"
    bike = "bike"
    car = "car"
