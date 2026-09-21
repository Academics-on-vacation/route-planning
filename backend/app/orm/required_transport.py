import enum


class RequiredTransport(str, enum.Enum):
    foot = "foot"
    transit = "transit"
    bike = "bike"
    car = "car"
