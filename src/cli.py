#!/usr/bin/env python3
"""CLI for Area Mission To Waypoint Converter."""

import argparse
import sys
from pathlib import Path

from .wpml import (
    parse_waylines_wpml,
    compute_shot_points_per_wayline,
    build_waypoint_kmz,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="area2waypoint",
        description="Convert area mission KMZ to waypoint KMZ readable by DJI Pilot 2.",
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Input area mission KMZ file",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Output waypoint KMZ file (default: input_waypoints.kmz)",
    )
    parser.add_argument(
        "--metadata-csv",
        type=Path,
        default=None,
        help="Optional metadata CSV to override shot points (columns: lat, lon, rel_alt, gimbal_yaw, gimbal_pitch, flight_yaw)",
    )
    parser.add_argument(
        "--lens",
        type=str,
        default="ir,wide,zoom",
        help="Payload lens list (default: ir,wide,zoom)",
    )
    parser.add_argument(
        "--focal-length",
        type=float,
        default=48.0,
        help="Focal length for orientedShoot (default: 48)",
    )
    parser.add_argument(
        "--split-routes",
        action="store_true",
        help="Write one KMZ per route (ortho, oblique1, oblique2, ...) for separate import in Pilot 2",
    )
    args = parser.parse_args()

    out_path = args.output
    if out_path is None:
        stem = args.input.stem
        if stem.endswith("_area") or stem.endswith("_mapping"):
            stem = stem.rsplit("_", 1)[0]
        out_path = args.input.parent / f"{stem}_waypoints.kmz"

    try:
        parsed = parse_waylines_wpml(args.input)
    except Exception as e:
        print(f"Error parsing input: {e}", file=sys.stderr)
        return 1

    try:
        wayline_shots = compute_shot_points_per_wayline(
            parsed,
            metadata_csv_path=args.metadata_csv,
        )
    except Exception as e:
        print(f"Error computing shot points: {e}", file=sys.stderr)
        return 1

    if not wayline_shots:
        print("No shot points computed.", file=sys.stderr)
        return 1

    try:
        if args.split_routes:
            base = out_path.parent / out_path.stem.replace("_waypoints", "")
            for i, (wl, shots) in enumerate(wayline_shots):
                label = "ortho" if wl.wayline_id == 0 else f"oblique{i}"
                path = base.parent / f"{base.name}_{label}.kmz"
                build_waypoint_kmz(
                    parsed,
                    [(wl, shots)],
                    output_path=path,
                    lens=args.lens,
                    focal_length=args.focal_length,
                )
                print(f"Wrote {path} ({len(shots)} waypoints, gimbal {shots[0].gimbal_pitch if shots else 0}°)")
        else:
            build_waypoint_kmz(
                parsed,
                wayline_shots,
                output_path=out_path,
                lens=args.lens,
                focal_length=args.focal_length,
            )
            print(f"Wrote {out_path} ({len(wayline_shots)} routes)")
    except Exception as e:
        print(f"Error building output: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
