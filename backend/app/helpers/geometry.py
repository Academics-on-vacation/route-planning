from __future__ import annotations

MIN_STEP = 0.00002


def to_geometry_points(selection: str) -> list[list[float]]:
    if not selection or "(" not in selection:
        return []
    inside = selection[selection.index("(") + 1 : selection.rindex(")")]
    points = []
    for pair in inside.split(","):
        parts = pair.split()
        if len(parts) < 2:
            continue
        try:
            lon, lat = float(parts[0]), float(parts[1])
        except ValueError:
            continue
        points.append([lat, lon])
    return points


def _from_segments(segments) -> list[list[float]]:
    out: list[list[float]] = []
    for seg in segments or []:
        out += to_geometry_points(seg.get("selection", "") if isinstance(seg, dict) else "")
    return out


def leg_points(payload: dict | None) -> list[list[float]]:
    if not isinstance(payload, dict):
        return []

    points: list[list[float]] = []

    for maneuver in payload.get("maneuvers") or []:
        path = (maneuver or {}).get("outcoming_path") or {}
        points += _from_segments(path.get("geometry"))

    for movement in payload.get("movements") or []:
        alternatives = (movement or {}).get("alternatives") or []
        if alternatives:
            points += _from_segments(alternatives[0].get("geometry"))

    return thin(points)


def thin(points: list[list[float]]) -> list[list[float]]:
    out: list[list[float]] = []
    for p in points:
        if not out or abs(p[0] - out[-1][0]) + abs(p[1] - out[-1][1]) > MIN_STEP:
            out.append(p)
    return out
