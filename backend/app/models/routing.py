from .engeneer import Engeneer
from .tickets import Ticket


class Route:
    def __init__(self, tickets: list[Ticket]):
        self.tickets = tickets

    def __str__(self):
        return f"{self.tickets}"

    def __repr__(self):
        return self.__str__()


class EngeneerRoute:
    def __init__(self, engeneer: Engeneer, route: Route):
        self.engeneer = engeneer
        self.route = route

    def __str__(self):
        return f"{self.engeneer} {self.route}"

    def __repr__(self):
        return self.__str__()


class EngeneerRoutes:
    def __init__(self, routes: list[EngeneerRoute]):
        self.routes = routes

    def __str__(self):
        return f"{self.routes}"

    def __repr__(self):
        return self.__str__()


class Routing:
    def __init__(self, routes: EngeneerRoutes):
        self.routes = routes

    def __str__(self):
        return f"{self.routes}"

    def __repr__(self):
        return self.__str__()
