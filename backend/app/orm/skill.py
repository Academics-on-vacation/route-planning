import enum


class Skill(str, enum.Enum):
    local = "local"
    install = "install"
    emergency = "emergency"