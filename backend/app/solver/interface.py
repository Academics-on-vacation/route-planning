from ..models.domain import Engeneer, Plan, Ticket


class Solver:
    def __init__(self):
        pass

    def solve(self, tickets: list[Ticket], engeneers: list[Engeneer]) -> Plan:
        raise NotImplementedError

    def get_name(self) -> str:
        return "Solver"
