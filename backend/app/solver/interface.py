from abc import ABC, abstractmethod

from ..models.domain import Engeneer, Plan, Ticket


class Solver(ABC):
    @abstractmethod
    def solve(self, tickets: list[Ticket], engineers: list[Engeneer]) -> Plan:
        """Построить план для переданного набора заявок и инженеров."""
        raise NotImplementedError
