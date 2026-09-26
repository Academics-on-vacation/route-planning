import asyncio
import logging
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.evaluation import CostWeights, PlanScore, compare_plans, evaluate_plan
from app.helpers import service
from app.models.domain import Region
from app.validation import InvalidPlanError


def test_metrics_and_cost_formula(plan_case):
    metrics = evaluate_plan(plan_case.plan, plan_case.tickets, plan_case.engineers)
    assert metrics.score == PlanScore(1, 1, 1, Decimal("3.75"))
    assert metrics.assigned_requests_count == 2
    assert metrics.total_urgent_requests_count == 2
    assert metrics.total_waiting_minutes == 50
    # 10000 × 1 заявка + 2000 × 1 инженер + 15 × 3.75 км + 3 × 50 мин.
    assert metrics.cost == Decimal("12206.25")
    assert metrics.weighted_cost(CostWeights(per_waiting_minute=0)).total == Decimal("12056.25")


@pytest.mark.parametrize(
    "better,worse",
    [
        ((0, 3, 2, 1000), (1, 1, 1, 1)),  # Срочные важнее общего числа назначений.
        ((0, 0, 2, 1000), (0, 1, 1, 1)),  # Назначения важнее числа инженеров.
        ((0, 0, 1, 1000), (0, 0, 2, 1)),  # Число инженеров важнее километров.
        ((0, 0, 1, 1.01), (0, 0, 1, 1.04)),
    ],
)
def test_score_priorities(better, worse):
    better_score = PlanScore(better[0], better[1], better[2], Decimal(str(better[3])))
    worse_score = PlanScore(worse[0], worse[1], worse[2], Decimal(str(worse[3])))
    assert better_score < worse_score


def test_compare_plans_and_reject_invalid_result(plan_case):
    candidate = deepcopy(plan_case.plan)
    candidate.routes[0].stops[0].travel_km -= 0.1
    result = compare_plans(candidate, plan_case.plan, plan_case.tickets, plan_case.engineers)
    assert result.winner == "left"
    assert result.deciding_criterion == "total_travel_distance_km"
    candidate.unassigned.clear()
    with pytest.raises(InvalidPlanError):
        evaluate_plan(candidate, plan_case.tickets, plan_case.engineers)


@pytest.mark.parametrize("weight", [-1, float("nan"), float("inf")])
def test_invalid_weights(weight):
    with pytest.raises(ValueError):
        CostWeights(per_waiting_minute=weight)


def test_cost_is_saved_and_logged_when_loading(plan_case, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=service.__name__)
    cost = evaluate_plan(plan_case.plan, plan_case.tickets, plan_case.engineers).cost
    session = AsyncMock()
    session.add = Mock(side_effect=lambda row: setattr(row, "id", 7))
    day = date(2026, 8, 17)
    asyncio.run(service.repository.save_plan(session, 1, day, plan_case.plan, cost=cost))
    snapshot = session.add.call_args.args[0]
    assert snapshot.metrics["cost"] == "12206.25"
    snapshot.created_at = datetime(2026, 8, 17)
    monkeypatch.setattr(service.repository, "active_plan", AsyncMock(return_value=snapshot))
    rows = [
        SimpleNamespace(id=ticket.request_id, external_id=ticket.id) for ticket in plan_case.tickets
    ]
    monkeypatch.setattr(service.repository, "list_requests", AsyncMock(return_value=rows))
    monkeypatch.setattr(service, "load_engineers", AsyncMock(return_value=plan_case.engineers))
    monkeypatch.setattr(
        service, "evaluate_plan", Mock(side_effect=AssertionError("GET must not recalculate"))
    )
    region = Region(1, "Region", plan_case.engineers[0].start_point)
    result = asyncio.run(service.stored_plan(session, region, day))
    assert result["metrics"]["cost"] == snapshot.metrics["cost"]
    assert [
        record.getMessage() for record in caplog.records if record.name == service.__name__
    ] == ["cost=12206.25"]
