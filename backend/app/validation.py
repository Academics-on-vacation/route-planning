"""Проверка допустимости плана, независимая от алгоритма и инфраструктуры.

Окно ограничивает начало работы; окончание ограничивается сменой. Проверяется
согласованность заявленного времени дороги, а не точность дорожного прогноза.
Причина отказа должна присутствовать; её истинность не доказывается перебором.
"""

from collections import Counter
from dataclasses import dataclass
from math import isfinite

from app.models.domain import Engeneer, Plan, Stop, Ticket


@dataclass(frozen=True)
class PlanViolation:
    code: str
    message: str
    ticket_id: str | None = None
    engineer_id: int | None = None


@dataclass(frozen=True)
class PlanValidationResult:
    violations: tuple[PlanViolation, ...]

    @property
    def is_valid(self) -> bool:
        return not self.violations

    def raise_if_invalid(self) -> None:
        if not self.is_valid:
            raise InvalidPlanError(self)


class InvalidPlanError(ValueError):
    def __init__(self, result: PlanValidationResult):
        self.result = result
        super().__init__("Некорректный план: " + "; ".join(v.message for v in result.violations))


def _finite(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def _stop_signature(stop: Stop) -> tuple:
    return (
        stop.ticket.id,
        stop.depart,
        stop.arrive,
        stop.start,
        stop.end,
        stop.travel_minutes,
        stop.travel_km,
        stop.frozen,
    )


def validate_plan(
    plan: Plan,
    tickets: list[Ticket],
    engineers: list[Engeneer],
    *,
    frozen: dict[int, list[Stop]] | None = None,
    not_before: int | None = None,
) -> PlanValidationResult:
    """Возвращает все обнаруженные нарушения, не изменяя план и входные данные.

    Ограничения берутся из исходных tickets/engineers, а не из объектов внутри
    маршрутов. frozen задаётся вызывающим кодом: валидатор не выбирает политику
    фиксации визитов. not_before ограничивает новые выезды при перепланировании.
    Геометрия, метаданные, целевая функция и лимиты конкретного солвера не проверяются.
    """
    violations: list[PlanViolation] = []

    def add(code, message, ticket_id=None, engineer_id=None):
        violations.append(PlanViolation(code, message, ticket_id, engineer_id))

    by_ticket = {t.id: t for t in tickets}
    by_engineer = {e.id: e for e in engineers}
    for ticket_id, count in Counter(t.id for t in tickets).items():
        if count > 1:
            add("duplicate_input_ticket", "Повтор ID входной заявки", ticket_id)
    for engineer_id, count in Counter(e.id for e in engineers).items():
        if count > 1:
            add("duplicate_input_engineer", "Повтор ID входного инженера", engineer_id=engineer_id)

    occurrences: Counter[str] = Counter()
    route_ids: set[int] = set()
    for route in plan.routes:
        engineer_id = route.engeneer.id
        if engineer_id in route_ids:
            add("duplicate_route", "Несколько маршрутов одного инженера", engineer_id=engineer_id)
        route_ids.add(engineer_id)
        engineer = by_engineer.get(engineer_id)
        if engineer is None:
            add("unknown_engineer", "Неизвестный инженер", engineer_id=engineer_id)

        expected = (frozen or {}).get(engineer_id, [])
        actual = route.stops[: len(expected)]
        if [_stop_signature(s) for s in actual] != [_stop_signature(s) for s in expected]:
            add("frozen_changed", "Изменён зафиксированный префикс", engineer_id=engineer_id)

        previous_end = engineer.work_shift_start_minutes if engineer is not None else None
        for index, stop in enumerate(route.stops):
            ticket_id = stop.ticket.id
            occurrences[ticket_id] += 1
            ticket = by_ticket.get(ticket_id)
            if ticket is None:
                add("unknown_ticket", "Неизвестная заявка", ticket_id, engineer_id)
            if ticket is not None and engineer is not None:
                if ticket.skill not in engineer.skills.types:
                    add("skill", "У инженера нет требуемого навыка", ticket_id, engineer_id)
                if (
                    ticket.required_transport is not None
                    and ticket.required_transport != engineer.transport
                ):
                    add(
                        "transport",
                        "Транспорт инженера не соответствует заявке",
                        ticket_id,
                        engineer_id,
                    )

            values = (
                stop.depart,
                stop.arrive,
                stop.start,
                stop.end,
                stop.travel_minutes,
                stop.travel_km,
            )
            if not all(_finite(value) for value in values):
                add(
                    "invalid_number",
                    "Время и расстояние должны быть конечными числами",
                    ticket_id,
                    engineer_id,
                )
                previous_end = None
                continue
            if stop.travel_minutes < 0 or stop.travel_km < 0:
                add(
                    "negative_travel",
                    "Отрицательное время или расстояние переезда",
                    ticket_id,
                    engineer_id,
                )
            if stop.arrive != stop.depart + stop.travel_minutes:
                add(
                    "arrival",
                    "Приезд не соответствует выезду и времени дороги",
                    ticket_id,
                    engineer_id,
                )
            if previous_end is not None and stop.depart < previous_end:
                add(
                    "overlap",
                    "Выезд раньше начала смены или окончания предыдущей работы",
                    ticket_id,
                    engineer_id,
                )
            if stop.start < stop.arrive:
                add("start_before_arrival", "Работа начинается до приезда", ticket_id, engineer_id)
            if not_before is not None and index >= len(expected) and stop.depart < not_before:
                add(
                    "before_event",
                    "Новый выезд раньше события перепланирования",
                    ticket_id,
                    engineer_id,
                )
            if ticket is not None:
                if not ticket.work_start <= stop.start <= ticket.work_finish:
                    add("window", "Начало работы вне окна заявки", ticket_id, engineer_id)
                if (
                    not _finite(ticket.duration_minutes)
                    or ticket.duration_minutes <= 0
                    or stop.end != stop.start + ticket.duration_minutes
                ):
                    add(
                        "duration",
                        "Длительность работы не соответствует заявке",
                        ticket_id,
                        engineer_id,
                    )
                if stop.ticket.duration_minutes != ticket.duration_minutes:
                    add(
                        "ticket_data",
                        "Длительность заявки в плане отличается от входной",
                        ticket_id,
                        engineer_id,
                    )
            if engineer is not None and stop.end > engineer.work_shift_end_minutes:
                add("shift", "Работа заканчивается после смены", ticket_id, engineer_id)
            previous_end = stop.end

    for engineer_id, stops in (frozen or {}).items():
        if stops and engineer_id not in route_ids:
            add(
                "frozen_missing",
                "Потерян маршрут с зафиксированными визитами",
                engineer_id=engineer_id,
            )
    for item in plan.unassigned:
        ticket_id = item.ticket.id
        occurrences[ticket_id] += 1
        if ticket_id not in by_ticket:
            add("unknown_ticket", "Неизвестная неназначенная заявка", ticket_id)
        if (
            not isinstance(item.reason, str)
            or not item.reason.strip()
            or not isinstance(item.reason_text, str)
            or not item.reason_text.strip()
        ):
            add("missing_reason", "Отсутствует причина неназначения", ticket_id)
    for ticket_id in by_ticket:
        count = occurrences[ticket_id]
        if count == 0:
            add("missing_ticket", "Заявка отсутствует в результате", ticket_id)
        elif count > 1:
            add("duplicate_ticket", "Заявка учтена более одного раза", ticket_id)
    return PlanValidationResult(tuple(violations))
