from types import SimpleNamespace

import pytest

from app.models.domain import (
    Engeneer,
    Plan,
    Point,
    Route,
    Skills,
    SkillType,
    Stop,
    Ticket,
    TransportType,
    Unassigned,
)


@pytest.fixture
def plan_case():
    """Два визита, одна неназначенная срочная заявка и 50 минут ожидания."""
    point = Point(55.75, 37.62)
    engineer = Engeneer(
        1, "Engineer", point, 540, 1080, Skills([SkillType.LOCAL]), TransportType.CAR
    )
    tickets = [
        Ticket(str(index), point, 30, 600, 900, priority=priority, request_id=index + 1)
        for index, priority in enumerate((0, 10, 100))
    ]
    stops = [
        Stop(tickets[0], 540, 550, 600, 630, 10, 1.25),
        Stop(tickets[2], 630, 640, 640, 670, 10, 2.5),
    ]
    plan = Plan([Route(engineer, stops)], [Unassigned(tickets[1], "capacity", "Нет времени")], {})
    return SimpleNamespace(plan=plan, tickets=tickets, engineers=[engineer])
