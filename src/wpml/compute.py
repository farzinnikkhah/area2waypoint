"""Compute shot points along path from multipleDistance triggers."""

import csv
from pathlib import Path
from typing import Optional, Tuple, List

from .parse import ParsedWaylines, PathPoint, ActionGroup


class ShotPoint:
    """Single shot point for waypoint output."""

    def __init__(self, lon, lat, execute_height, heading, gimbal_pitch, gimbal_yaw):
        self.lon = lon
        self.lat = lat
        self.execute_height = execute_height
        self.heading = heading
        self.gimbal_pitch = gimbal_pitch
        self.gimbal_yaw = gimbal_yaw


def _haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Approximate distance in meters between two WGS84 points."""
    import math
    R = 6371000  # Earth radius in m
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def _interpolate(
    p0: PathPoint, p1: PathPoint, t: float
) -> Tuple[float, float, float, float, float, float]:
    """Interpolate between two path points. t in [0, 1]."""
    lon = p0.lon + t * (p1.lon - p0.lon)
    lat = p0.lat + t * (p1.lat - p0.lat)
    height = p0.execute_height + t * (p1.execute_height - p0.execute_height)
    heading = p0.waypoint_heading_angle + t * (
        p1.waypoint_heading_angle - p0.waypoint_heading_angle
    )
    gimbal_pitch = p0.gimbal_pitch + t * (p1.gimbal_pitch - p0.gimbal_pitch)
    gimbal_yaw = p0.gimbal_yaw + t * (p1.gimbal_yaw - p0.gimbal_yaw)
    return lon, lat, height, heading, gimbal_pitch, gimbal_yaw


def _compute_shots_from_multiple_distance(
    points,
    start_idx,
    end_idx,
    spacing_m,
    default_pitch=-90.0,
    default_yaw=0.0,
):
    """Generate shot points along path segment at spacing_m intervals."""
    segment = [p for p in points if start_idx <= p.index <= end_idx]
    if len(segment) < 2:
        return []

    shots = []
    accumulated = 0.0
    next_shot_at = 0.0

    for i in range(len(segment) - 1):
        p0, p1 = segment[i], segment[i + 1]
        seg_len = _haversine_m(p0.lon, p0.lat, p1.lon, p1.lat)

        while accumulated + seg_len >= next_shot_at:
            t = (next_shot_at - accumulated) / seg_len if seg_len > 0 else 1.0
            t = max(0, min(1, t))
            lon, lat, height, heading, gp, gy = _interpolate(p0, p1, t)

            pitch = gp if (p0.gimbal_pitch != 0 or p1.gimbal_pitch != 0) else default_pitch
            yaw = gy if (p0.gimbal_yaw != 0 or p1.gimbal_yaw != 0) else default_yaw

            shots.append(
                ShotPoint(
                    lon=lon,
                    lat=lat,
                    execute_height=height,
                    heading=heading,
                    gimbal_pitch=pitch,
                    gimbal_yaw=yaw,
                )
            )
            next_shot_at += spacing_m

        accumulated += seg_len

    return shots


def _select_best_multiple_distance_group(action_groups):
    """Select the multipleDistance group with the broadest range."""
    candidates = [
        ag
        for ag in action_groups
        if ag.trigger_type == "multipleDistance"
        and ag.trigger_param is not None
        and ag.trigger_param > 0
        and ag.has_take_photo
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda ag: ag.end_index - ag.start_index)


def compute_shot_points(parsed, metadata_csv_path=None):
    """
    Compute shot points from first wayline (backward compat).
    For multi-wayline, use compute_shot_points_per_wayline.
    """
    if metadata_csv_path is not None and metadata_csv_path.exists():
        return _load_shots_from_csv(metadata_csv_path)
    return _compute_shots_for_wayline(parsed.points, parsed.action_groups)


def compute_shot_points_per_wayline(parsed, metadata_csv_path=None):
    """
    Compute shot points for each wayline (ortho + oblique).
    Returns List[Tuple[ParsedWayline, List[ShotPoint]]].
    """
    if metadata_csv_path is not None and metadata_csv_path.exists():
        # CSV overrides: apply to first wayline only
        shots = _load_shots_from_csv(metadata_csv_path)
        if parsed.waylines:
            return [(parsed.waylines[0], shots)]
        return []

    result = []
    for wl in parsed.waylines:
        shots = _compute_shots_for_wayline(wl.points, wl.action_groups)
        if shots:
            result.append((wl, shots))
    return result


def _compute_shots_for_wayline(points, action_groups):
    """Compute shot points for a single wayline."""
    ag = _select_best_multiple_distance_group(action_groups)

    if ag is not None:
        default_pitch = ag.gimbal_pitch
        default_yaw = ag.gimbal_yaw
        spacing = ag.trigger_param
        return _compute_shots_from_multiple_distance(
            points,
            ag.start_index,
            ag.end_index,
            spacing,
            default_pitch=default_pitch,
            default_yaw=default_yaw,
        )

    return [
        ShotPoint(
            lon=p.lon,
            lat=p.lat,
            execute_height=p.execute_height,
            heading=p.waypoint_heading_angle,
            gimbal_pitch=p.gimbal_pitch if p.gimbal_pitch != 0 else -90.0,
            gimbal_yaw=p.gimbal_yaw,
        )
        for p in points
    ]


def _load_shots_from_csv(path: Path):
    """Load shot points from metadata CSV."""
    shots = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            lat = float(row.get("lat", 0))
            lon = float(row.get("lon", 0))
            alt = float(row.get("rel_alt", row.get("alt", row.get("height", 0))))
            gp = float(row.get("gimbal_pitch", -90))
            gy = float(row.get("gimbal_yaw", 0))
            fy = float(row.get("flight_yaw", row.get("heading", 0)))
            shots.append(
                ShotPoint(
                    lon=lon,
                    lat=lat,
                    execute_height=alt,
                    heading=fy,
                    gimbal_pitch=gp,
                    gimbal_yaw=gy,
                )
            )
    return shots
