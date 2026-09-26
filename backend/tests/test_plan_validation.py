from copy import deepcopy

import pytest

from app.models.domain import Skills, SkillType, TransportType, Unassigned
from app.validation import InvalidPlanError, validate_plan


def test_valid_plan_can_finish_after_window(plan_case):
    plan_case.tickets[0].work_finish = 600
    assert validate_plan(plan_case.plan, plan_case.tickets, plan_case.engineers).is_valid


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("depart", 539, "overlap"),
        ("arrive", 551, "arrival"),
        ("start", 901, "window"),
        ("end", 631, "duration"),
        ("end", 1081, "shift"),
        ("travel_km", -1, "negative_travel"),
        ("travel_minutes", float("nan"), "invalid_number"),
    ],
)
def test_invalid_schedule(plan_case, field, value, code):
    setattr(plan_case.plan.routes[0].stops[0], field, value)
    result = validate_plan(plan_case.plan, plan_case.tickets, plan_case.engineers)
    assert code in {violation.code for violation in result.violations}
    with pytest.raises(InvalidPlanError):
        result.raise_if_invalid()


def test_constraints_use_original_engineer(plan_case):
    engineer = deepcopy(plan_case.engineers[0])
    engineer.skills = Skills([SkillType.EMERGENCY])
    engineer.transport = TransportType.WALKER
    plan_case.tickets[0].required_transport = TransportType.CAR
    result = validate_plan(plan_case.plan, plan_case.tickets, [engineer])
    assert {"skill", "transport"} <= {violation.code for violation in result.violations}


@pytest.mark.parametrize(
    "case,code",
    [
        ("missing", "missing_ticket"),
        ("duplicate", "duplicate_ticket"),
        ("reason", "missing_reason"),
    ],
)
def test_every_request_accounted_for(plan_case, case, code):
    if case == "missing":
        plan_case.plan.unassigned.clear()
    elif case == "duplicate":
        plan_case.plan.unassigned.append(
            Unassigned(plan_case.tickets[0], "capacity", "Нет времени")
        )
    else:
        plan_case.plan.unassigned[0].reason = ""
    result = validate_plan(plan_case.plan, plan_case.tickets, plan_case.engineers)
    assert code in {violation.code for violation in result.violations}


def test_frozen_visits_cannot_change(plan_case):
    first = plan_case.plan.routes[0].stops[0]
    first.frozen = True
    frozen = {1: [deepcopy(first)]}
    assert validate_plan(
        plan_case.plan, plan_case.tickets, plan_case.engineers, frozen=frozen, not_before=610
    ).is_valid
    first.travel_km += 1
    result = validate_plan(plan_case.plan, plan_case.tickets, plan_case.engineers, frozen=frozen)
    assert "frozen_changed" in {violation.code for violation in result.violations}
