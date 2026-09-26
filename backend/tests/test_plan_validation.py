import asyncio
from copy import deepcopy
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.helpers import service
from app.models.domain import (
    Engeneer,
    Plan,
    Point,
    Region,
    Route,
    Skills,
    SkillType,
    Stop,
    Ticket,
    TransportType,
    Unassigned,
)
from app.validation import InvalidPlanError, validate_plan


@pytest.fixture
def example():
    point = Point(55.75, 37.62)
    engineer = Engeneer(
        1, "Engineer", point, 540, 1080, Skills([SkillType.LOCAL]), TransportType.WALKER
    )
    ticket = Ticket("one", point, 30, 540, 600, request_id=1)
    stop = Stop(ticket, 540, 550, 550, 580, 10, 2)
    return Plan([Route(engineer, [stop])], [], {}), ticket, engineer


def codes(result):
    return {v.code for v in result.violations}


def test_valid_plan_and_validation_do_not_mutate_data(example):
    plan, ticket, engineer = example
    before = deepcopy(plan.to_json(1, date(2026, 8, 17)))
    result = validate_plan(plan, [ticket], [engineer])
    assert result.is_valid and result.violations == ()
    result.raise_if_invalid()
    after = plan.to_json(1, date(2026, 8, 17))
    before["meta"].pop("generated_at")
    after["meta"].pop("generated_at")
    assert before == after


def test_window_restricts_start_not_finish(example):
    plan, ticket, engineer = example
    ticket.work_finish = 550
    assert validate_plan(plan, [ticket], [engineer]).is_valid


def test_unassigned_with_reason_and_empty_plan_are_valid(example):
    _, ticket, engineer = example
    plan = Plan([], [Unassigned(ticket, "capacity", "Нет свободного исполнителя")], {})
    assert validate_plan(plan, [ticket], [engineer]).is_valid
    assert validate_plan(Plan([], [], {}), [], []).is_valid


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("depart", 539, "overlap"),
        ("arrive", 551, "arrival"),
        ("start", 549, "start_before_arrival"),
        ("start", 601, "window"),
        ("end", 581, "duration"),
        ("end", 1081, "shift"),
        ("travel_km", -1, "negative_travel"),
        ("travel_minutes", -1, "negative_travel"),
        ("travel_minutes", float("nan"), "invalid_number"),
        ("travel_km", float("inf"), "invalid_number"),
        ("start", None, "invalid_number"),
    ],
)
def test_schedule_violations_have_identifiers(example, field, value, code):
    plan, ticket, engineer = example
    setattr(plan.routes[0].stops[0], field, value)
    result = validate_plan(plan, [ticket], [engineer])
    issue = next(v for v in result.violations if v.code == code)
    assert issue.ticket_id == "one" and issue.engineer_id == 1
    with pytest.raises(InvalidPlanError) as exc:
        result.raise_if_invalid()
    assert exc.value.result is result


def test_overlap_between_distinct_tickets(example):
    plan, first, engineer = example
    second = deepcopy(first)
    second.id = "two"
    plan.routes[0].stops.append(Stop(second, 570, 580, 580, 610, 10, 1))
    assert "overlap" in codes(validate_plan(plan, [first, second], [engineer]))


@pytest.mark.parametrize(
    "required", [TransportType.CAR, TransportType.TRANSIT, TransportType.BYCICLE]
)
def test_all_transport_requirements_checked_against_input(example, required):
    plan, ticket, engineer = example
    original = deepcopy(ticket)
    original.required_transport = required
    assert "transport" in codes(validate_plan(plan, [original], [engineer]))


def test_skill_checked_against_input_not_route_copy(example):
    plan, ticket, engineer = example
    original = deepcopy(engineer)
    original.skills = Skills([SkillType.EMERGENCY])
    assert "skill" in codes(validate_plan(plan, [ticket], [original]))


def test_missing_and_duplicate_assignments(example):
    plan, ticket, engineer = example
    assert "missing_ticket" in codes(validate_plan(Plan([], [], {}), [ticket], [engineer]))
    plan.unassigned.append(Unassigned(ticket, "capacity", "Нет времени"))
    assert "duplicate_ticket" in codes(validate_plan(plan, [ticket], [engineer]))


def test_unknown_references_and_duplicate_inputs(example):
    plan, ticket, engineer = example
    assert {"unknown_engineer", "unknown_ticket"} <= codes(validate_plan(plan, [], []))
    result = validate_plan(plan, [ticket, ticket], [engineer, engineer])
    assert {"duplicate_input_ticket", "duplicate_input_engineer"} <= codes(result)
    plan.routes.append(deepcopy(plan.routes[0]))
    assert {"duplicate_route", "duplicate_ticket"} <= codes(
        validate_plan(plan, [ticket], [engineer])
    )


def test_reason_required_for_every_unassigned_ticket(example):
    _, ticket, engineer = example
    plan = Plan([], [Unassigned(ticket, "", "  ")], {})
    assert "missing_reason" in codes(validate_plan(plan, [ticket], [engineer]))


def test_frozen_prefix_preserved_without_choosing_freeze_policy(example):
    plan, ticket, engineer = example
    plan.routes[0].stops[0].frozen = True
    frozen = {engineer.id: deepcopy(plan.routes[0].stops)}
    assert validate_plan(plan, [ticket], [engineer], frozen=frozen, not_before=560).is_valid
    plan.routes[0].stops[0].travel_km = 3
    assert "frozen_changed" in codes(validate_plan(plan, [ticket], [engineer], frozen=frozen))
    assert "frozen_missing" in codes(
        validate_plan(Plan([], [], {}), [ticket], [engineer], frozen=frozen)
    )


def test_frozen_flag_cannot_bypass_event_boundary(example):
    plan, ticket, engineer = example
    plan.routes[0].stops[0].frozen = True
    assert "before_event" in codes(validate_plan(plan, [ticket], [engineer], not_before=560))


@pytest.fixture
def service_context(example, monkeypatch):
    plan, ticket, engineer = example
    monkeypatch.setattr(service, "load_tickets", AsyncMock(return_value=[ticket]))
    monkeypatch.setattr(service, "load_engineers", AsyncMock(return_value=[engineer]))
    monkeypatch.setattr(service.repository, "load_leg_cache", AsyncMock(return_value=[]))
    save_plan = AsyncMock(return_value=7)
    save_cache = AsyncMock(return_value=0)
    monkeypatch.setattr(service.repository, "save_plan", save_plan)
    monkeypatch.setattr(service.repository, "save_leg_cache", save_cache)
    monkeypatch.setattr(service.GreedySolver, "solve", lambda *args: plan)
    monkeypatch.setattr(service.GreedySolver, "_geometry", lambda *args: None)
    return SimpleNamespace(
        plan=plan,
        save_plan=save_plan,
        save_cache=save_cache,
        session=AsyncMock(),
        region=Region(1, "Region", Point(55.75, 37.62)),
        day=date(2026, 8, 17),
    )


def test_build_saves_valid_result(service_context):
    ctx = service_context
    result = asyncio.run(service.build_plan(ctx.session, ctx.region, ctx.day, use_api=False))
    assert result["meta"]["plan_id"] == 7
    ctx.save_plan.assert_awaited_once()


@pytest.mark.parametrize("persist", [True, False])
def test_build_rejects_invalid_result_before_saving(service_context, persist):
    ctx = service_context
    ctx.plan.routes.clear()
    with pytest.raises(InvalidPlanError):
        asyncio.run(
            service.build_plan(ctx.session, ctx.region, ctx.day, use_api=False, persist=persist)
        )
    ctx.save_plan.assert_not_awaited()
    ctx.save_cache.assert_not_awaited()


@pytest.mark.parametrize("with_route", [True, False])
def test_replan_validates_merged_frozen_prefix(service_context, monkeypatch, with_route):
    ctx = service_context
    row = SimpleNamespace(
        request_id=1,
        depart_at=datetime(2026, 8, 17, 9),
        arrive_at=datetime(2026, 8, 17, 9, 10),
        start_at=datetime(2026, 8, 17, 9, 10),
        end_at=datetime(2026, 8, 17, 9, 40),
        travel_min=10,
        travel_km=2,
    )
    snapshot = SimpleNamespace(id=3, routes=[SimpleNamespace(engineer_id=1, stops=[row])])
    monkeypatch.setattr(service.repository, "active_plan", AsyncMock(return_value=snapshot))
    # Все заявки уже зафиксированы: результат солвера для свободной части пуст.
    ctx.plan.routes[0].stops.clear()
    if not with_route:
        ctx.plan.routes.clear()
    call = service.replan(ctx.session, ctx.region, datetime(2026, 8, 17, 9, 20), use_api=False)
    if with_route:
        result = asyncio.run(call)
        assert result["routes"][0]["stops"][0]["frozen"]
        ctx.save_plan.assert_awaited_once()
    else:
        with pytest.raises(InvalidPlanError) as exc:
            asyncio.run(call)
        assert "frozen_missing" in codes(exc.value.result)
        ctx.save_plan.assert_not_awaited()
        ctx.save_cache.assert_not_awaited()
