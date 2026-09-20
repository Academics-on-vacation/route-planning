from ..models.engeneer import Engeneer
from ..models.routing import EngeneerRoute
from ..models.tickets import Ticket
from .interface import Solver


class GreedySolver(Solver):
    def solve(self, tickets: list[Ticket], engeneers: list[Engeneer]) -> EngeneerRoute | None:
        pass
