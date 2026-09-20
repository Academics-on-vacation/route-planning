from ..models.engeneer import Engeneer
from ..models.routing import EngeneerRoute
from ..models.tickets import Ticket


class Solver:
    def __init__(self):
        pass

    def solve(self, tickets: list[Ticket], engeneers: list[Engeneer]) -> EngeneerRoute | None:
        pass
