"""Представление моделей и результатов в существующем формате API/снимков."""

from datetime import date, datetime, time, timedelta

from app.models.domain import Engeneer, Region, Route, Stop, Ticket, Unassigned
from app.results import PlanningResult


def at(day: date, minutes: int) -> str:
    return (datetime.combine(day, time.min) + timedelta(minutes=minutes)).isoformat()


def region_to_json(region: Region) -> dict:
    return {
        "id": region.id,
        "title": region.title,
        "office_address": region.office_address,
        "office_lat": region.office.latitude,
        "office_lon": region.office.longitude,
    }


def ticket_to_json(ticket: Ticket, day: date) -> dict:
    return {
        "id": ticket.id,
        "lat": ticket.point.latitude,
        "lon": ticket.point.longitude,
        "address": ticket.address,
        "district": ticket.district,
        "skill": ticket.skill.value,
        "duration_min": ticket.duration_minutes,
        "window_start": at(day, ticket.work_start),
        "window_end": at(day, ticket.work_finish),
        "priority": ticket.priority,
        "required_transport": ticket.required_transport.value
        if ticket.required_transport
        else None,
        "equipment": {"Роутер": 3, "Кабель LAN, м": 30},
    }


def engineer_to_json(engineer: Engeneer, day: date) -> dict:
    return {
        "id": engineer.id,
        "name": engineer.name,
        "skills": [s.value for s in engineer.skills.types],
        "transport": engineer.transport.value,
        "shift_start": at(day, engineer.work_shift_start_minutes),
        "shift_end": at(day, engineer.work_shift_end_minutes),
        "start_lat": engineer.start_point.latitude,
        "start_lon": engineer.start_point.longitude,
    }


def unassigned_to_json(item: Unassigned) -> dict:
    return {
        "request_id": str(item.ticket.id),
        "reason": item.reason,
        "reason_text": item.reason_text,
    }


def stop_to_json(stop: Stop, day: date, seq: int) -> dict:
    return {
        "seq": seq,
        "request_id": str(stop.ticket.id),
        "arrive_at": at(day, stop.arrive),
        "start_at": at(day, stop.start),
        "end_at": at(day, stop.end),
        "wait_min": stop.wait_minutes,
        "travel_min": stop.travel_minutes,
        "travel_km": stop.travel_km,
        "frozen": stop.frozen,
        "moved_from": stop.moved_from,
    }


def route_to_json(route: Route, day: date, geometry) -> dict:
    engineer = route.engeneer
    return {
        "engineer_id": engineer.id,
        "engineer_name": engineer.name,
        "start": {
            "lat": engineer.start_point.latitude,
            "lon": engineer.start_point.longitude,
            "at": at(day, engineer.work_shift_start_minutes),
        },
        "stops": [stop_to_json(stop, day, seq) for seq, stop in enumerate(route.stops, 1)],
        "distance_km": round(route.distance_km, 1),
        "travel_min": route.travel_minutes,
        "service_min": route.service_minutes,
        "wait_min": route.wait_minutes,
        "finish_at": at(day, route.finish) if route.finish is not None else None,
        "geometry": geometry,
    }


def metrics_to_json(result: PlanningResult) -> dict:
    metrics = result.metrics
    if metrics is None:
        return {}
    return {
        "requests_total": metrics.total_requests_count,
        "assigned": metrics.assigned_requests_count,
        "unassigned": metrics.unassigned_requests_count,
        "engineers_used": metrics.used_engineers_count,
        "total_distance_km": float(round(metrics.total_travel_distance_km, 1)),
        "total_travel_min": metrics.total_travel_minutes,
        "total_wait_min": metrics.total_waiting_minutes,
        "window_violations": 0,  # Метрики создаются только после валидации.
        "finish_after_window": sum(s.late_minutes > 0 for r in result.plan.routes for s in r.stops),
        "cost": str(metrics.cost),
    }


def planning_result_to_json(result: PlanningResult) -> dict:
    return {
        "region_id": result.region_id,
        "work_date": result.work_date.isoformat() if result.work_date else None,
        "routes": [
            route_to_json(r, result.work_date, result.geometries.get(r.engeneer.id))
            for r in result.plan.used_routes
        ]
        if result.work_date is not None
        else [],
        "unassigned": [unassigned_to_json(item) for item in result.plan.unassigned],
        "metrics": metrics_to_json(result),
        "meta": {
            **result.metadata,
            "generated_at": result.generated_at.isoformat(timespec="seconds"),
        },
    }


def stored_plan_to_json(snapshot, region_id: int, work_date: date, public: dict, engineers) -> dict:
    """Представление сохранённого снимка без повторного запуска алгоритма/оценки."""
    replan_meta = (snapshot.meta or {}).get("replan") or {}
    frozen_at = replan_meta.get("frozen_at")
    came_from = {m["request_id"]: m["from"] for m in replan_meta.get("moves", [])}
    by_id = {e.id: e for e in engineers}
    routes = []
    for row in sorted(snapshot.routes, key=lambda r: r.engineer_id):
        eng = by_id.get(row.engineer_id)
        if eng is None or not row.stops:
            continue
        stops = []
        for st in row.stops:
            request_id = public.get(st.request_id, str(st.request_id))
            stops.append(
                {
                    "seq": st.seq,
                    "request_id": request_id,
                    "arrive_at": st.arrive_at.isoformat(),
                    "start_at": st.start_at.isoformat(),
                    "end_at": st.end_at.isoformat(),
                    "wait_min": int((st.start_at - st.arrive_at).total_seconds() // 60),
                    "travel_min": st.travel_min,
                    "travel_km": st.travel_km,
                    "frozen": bool(frozen_at and st.start_at.isoformat() < frozen_at),
                    "moved_from": came_from.get(request_id),
                }
            )
        routes.append(
            {
                "engineer_id": row.engineer_id,
                "engineer_name": eng.name,
                "start": {
                    "lat": eng.start_point.latitude,
                    "lon": eng.start_point.longitude,
                    "at": at(work_date, eng.work_shift_start_minutes),
                },
                "stops": stops,
                "distance_km": round(row.distance_km, 1),
                "travel_min": row.travel_min,
                "service_min": row.service_min,
                "wait_min": row.wait_min,
                "finish_at": stops[-1]["end_at"],
                "geometry": row.geometry,
            }
        )
    return {
        "region_id": region_id,
        "work_date": work_date.isoformat(),
        "routes": routes,
        "unassigned": (snapshot.meta or {}).get("unassigned", []),
        "metrics": {"cost": None, **(snapshot.metrics or {})},
        "meta": {
            **(snapshot.meta or {}),
            "stored": True,
            "plan_id": snapshot.id,
            "created_at": snapshot.created_at.isoformat(timespec="seconds"),
        },
    }
