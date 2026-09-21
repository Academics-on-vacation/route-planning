import math


from ..models.domain import Point, TransportType

# ОЦЕНКА маршрута
def estimate(a: Point, b: Point, transport: TransportType, depart: int) -> tuple[int, float]:

    p1, p2 = math.radians(a.latitude), math.radians(b.latitude)
    h = (
        math.sin((p2 - p1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b.longitude - a.longitude) / 2) ** 2
    )
    straight = 2 * 6371.0088 * math.asin(math.sqrt(h)) # расстрояние по прямой (по длине дуги на сфере)

    if straight < 0.02:
        return 0, 0.0

    # по прямой никто не ездит, накидываем запас
    km = straight * DETOUR

    # учитываем скорость по типу и длине
    near, far, switch = SPEED.get(transport, SPEED[TransportType.TRANSIT])
    kmh = near if km <= switch else far

    # набрасываем пробки на глаз
    factor = 1.0
    for limit, car, transit in CONGESTION:
        if depart < limit:
            factor = car if transport == TransportType.CAR else transit
            break

    return int(km / kmh * 60 * factor) + OVERHEAD_MIN, round(km, 2)


DETOUR = 1.35  # приближение оценки
OVERHEAD_MIN = 6  # погрешность на перемещение по дввору

SPEED = {
    TransportType.CAR: (30.0, 70.0, 25.0),
    TransportType.TRANSIT: (4.5, 18.0, 1.5),
    TransportType.WALKER: (4.5, 4.5, 999.0),
    TransportType.BYCICLE: (13.0, 15.0, 999.0),
}

CONGESTION = [
    (7 * 60, 0.80, 0.95),
    (10 * 60, 1.45, 1.10),  # утренний пик
    (16 * 60, 1.00, 1.00),
    (20 * 60, 1.50, 1.15),  # вечерний пик
    (24 * 60, 0.85, 0.95),
]

REASONS = {
    "skill": "Нет свободного исполнителя с нужным навыком",
    "transport": "Нужен другой транспорт",
    "capacity": "Все подходящие исполнители заняты в это окно",
    "window": "По реальной дороге заявка не успевает в окно",
}