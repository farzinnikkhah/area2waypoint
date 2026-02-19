"""Tests for Area Mission To Waypoint Converter."""

import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from src.wpml import (
    parse_waylines_wpml,
    compute_shot_points,
    compute_shot_points_per_wayline,
    build_waypoint_kmz,
)

FIXTURES = Path(__file__).parent / "fixtures"
AREA_MINIMAL_KMZ = FIXTURES / "area_minimal.kmz"
REPO_ROOT = Path(__file__).parent.parent
AREA_ROUTE1_KMZ = REPO_ROOT / "route_samples" / "tmp_area"
# Use extracted wpmz if tmp_area is a folder; otherwise expect a kmz
AREA_ROUTE1_WPML = REPO_ROOT / "route_samples" / "tmp_area" / "wpmz" / "waylines.wpml"

WPML_NS = "http://www.dji.com/wpmz/1.0.6"


def _ensure_kmz(path: Path) -> Path:
    """If path is a directory, create a temp kmz and return it; else return path."""
    if path.is_dir():
        wpml = path / "wpmz" / "waylines.wpml"
        if not wpml.exists():
            return None
        import tempfile
        out = Path(tempfile.mkdtemp()) / "area.kmz"
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(wpml, "wpmz/waylines.wpml")
        return out
    return path if path.suffix == ".kmz" else None


class TestParse:
    """Parse WPML tests."""

    def test_parse_minimal_kmz(self):
        parsed = parse_waylines_wpml(AREA_MINIMAL_KMZ)
        assert len(parsed.points) == 4
        assert parsed.points[0].lon == pytest.approx(-78.51)
        assert parsed.points[0].lat == pytest.approx(38.03)
        assert parsed.points[0].execute_height == 20
        assert parsed.auto_flight_speed == 2

    def test_parse_extracts_action_groups(self):
        parsed = parse_waylines_wpml(AREA_MINIMAL_KMZ)
        md_groups = [ag for ag in parsed.action_groups if ag.trigger_type == "multipleDistance"]
        assert len(md_groups) >= 1
        ag = md_groups[0]
        assert ag.trigger_param == 10
        assert ag.start_index == 0
        assert ag.end_index == 3
        assert ag.has_take_photo
        assert ag.gimbal_pitch == -90

    def test_parse_missing_wpml_raises(self, tmp_path):
        bad_kmz = tmp_path / "bad.kmz"
        with zipfile.ZipFile(bad_kmz, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("other.txt", "x")
        with pytest.raises(FileNotFoundError, match="wpmz/waylines.wpml"):
            parse_waylines_wpml(bad_kmz)


class TestCompute:
    """Compute shot points tests."""

    def test_compute_from_multiple_distance(self):
        parsed = parse_waylines_wpml(AREA_MINIMAL_KMZ)
        shots = compute_shot_points(parsed)
        assert len(shots) >= 2
        assert shots[0].lon == pytest.approx(-78.51, rel=1e-4)
        assert shots[0].gimbal_pitch == -90

    def test_compute_fallback_to_waypoints(self, tmp_path):
        # KMZ with no multipleDistance - use path waypoints
        wpml = b"""<?xml version="1.0"?>
<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:wpml="http://www.dji.com/wpmz/1.0.6">
  <Document><Folder>
    <wpml:autoFlightSpeed>1</wpml:autoFlightSpeed>
    <Placemark>
      <Point><coordinates>-78.5,38.0</coordinates></Point>
      <wpml:index>0</wpml:index>
      <wpml:executeHeight>15</wpml:executeHeight>
      <wpml:waypointSpeed>1</wpml:waypointSpeed>
      <wpml:waypointHeadingParam><wpml:waypointHeadingAngle>0</wpml:waypointHeadingAngle></wpml:waypointHeadingParam>
    </Placemark>
    <Placemark>
      <Point><coordinates>-78.6,38.1</coordinates></Point>
      <wpml:index>1</wpml:index>
      <wpml:executeHeight>15</wpml:executeHeight>
      <wpml:waypointSpeed>1</wpml:waypointSpeed>
      <wpml:waypointHeadingParam><wpml:waypointHeadingAngle>90</wpml:waypointHeadingAngle></wpml:waypointHeadingParam>
    </Placemark>
  </Folder></Document>
</kml>"""
        kmz = tmp_path / "no_md.kmz"
        with zipfile.ZipFile(kmz, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("wpmz/waylines.wpml", wpml)
        parsed = parse_waylines_wpml(kmz)
        shots = compute_shot_points(parsed)
        assert len(shots) == 2
        assert shots[0].lon == pytest.approx(-78.5)

    def test_compute_from_metadata_csv(self, tmp_path):
        csv_path = tmp_path / "shots.csv"
        csv_path.write_text("lat,lon,rel_alt,gimbal_pitch,gimbal_yaw,flight_yaw\n38.0,-78.5,20,-40,0,90\n")
        parsed = parse_waylines_wpml(AREA_MINIMAL_KMZ)
        shots = compute_shot_points(parsed, metadata_csv_path=csv_path)
        assert len(shots) == 1
        assert shots[0].lat == 38.0
        assert shots[0].lon == -78.5
        assert shots[0].gimbal_pitch == -40
        assert shots[0].heading == 90


class TestBuild:
    """Build waypoint KMZ tests."""

    def test_build_produces_valid_kmz(self, tmp_path):
        parsed = parse_waylines_wpml(AREA_MINIMAL_KMZ)
        wayline_shots = compute_shot_points_per_wayline(parsed)
        out = tmp_path / "out.kmz"
        build_waypoint_kmz(parsed, wayline_shots, output_path=out)

        assert out.exists()
        with zipfile.ZipFile(out, "r") as z:
            names = z.namelist()
            assert "wpmz/template.kml" in names
            assert "wpmz/waylines.wpml" in names

    def test_build_template_has_waypoint_type(self, tmp_path):
        parsed = parse_waylines_wpml(AREA_MINIMAL_KMZ)
        wayline_shots = compute_shot_points_per_wayline(parsed)
        out = tmp_path / "out.kmz"
        build_waypoint_kmz(parsed, wayline_shots, output_path=out)

        with zipfile.ZipFile(out, "r") as z:
            data = z.read("wpmz/template.kml").decode("utf-8")
        assert "templateType" in data
        assert "waypoint" in data
        assert "imageFormat" in data
        assert "wide" in data or "ir" in data or "zoom" in data

    def test_build_waylines_have_oriented_shoot(self, tmp_path):
        parsed = parse_waylines_wpml(AREA_MINIMAL_KMZ)
        wayline_shots = compute_shot_points_per_wayline(parsed)
        out = tmp_path / "out.kmz"
        build_waypoint_kmz(parsed, wayline_shots, output_path=out)

        with zipfile.ZipFile(out, "r") as z:
            data = z.read("wpmz/waylines.wpml").decode("utf-8")
        assert "orientedShoot" in data
        assert "reachPoint" in data
        assert "payloadLensIndex" in data


class TestGolden:
    """Golden / structure validation tests."""

    def test_output_wpml_placemark_count_matches_shots(self, tmp_path):
        parsed = parse_waylines_wpml(AREA_MINIMAL_KMZ)
        wayline_shots = compute_shot_points_per_wayline(parsed)
        total_shots = sum(len(s) for _, s in wayline_shots)
        out = tmp_path / "out.kmz"
        build_waypoint_kmz(parsed, wayline_shots, output_path=out)

        with zipfile.ZipFile(out, "r") as z:
            wpml = z.read("wpmz/waylines.wpml").decode("utf-8")

        root = ET.fromstring(wpml)
        ns = {"kml": "http://www.opengis.net/kml/2.2", "wpml": WPML_NS}
        placemarks = root.findall(".//kml:Placemark", ns)
        if not placemarks:
            placemarks = root.findall(".//{http://www.opengis.net/kml/2.2}Placemark")
        assert len(placemarks) == total_shots

    def test_each_placemark_has_oriented_shoot_action(self, tmp_path):
        parsed = parse_waylines_wpml(AREA_MINIMAL_KMZ)
        wayline_shots = compute_shot_points_per_wayline(parsed)
        out = tmp_path / "out.kmz"
        build_waypoint_kmz(parsed, wayline_shots, output_path=out)

        with zipfile.ZipFile(out, "r") as z:
            wpml = z.read("wpmz/waylines.wpml").decode("utf-8")

        root = ET.fromstring(wpml)
        for pm in root.iter("{http://www.opengis.net/kml/2.2}Placemark"):
            if pm.tag == "{http://www.opengis.net/kml/2.2}Placemark":
                has_os = any(
                    "orientedShoot" in (c.text or "")
                    for c in pm.iter()
                    if c.text and "orientedShoot" in c.text
                )
                # Check for orientedShoot in descendants
                text = ET.tostring(pm, encoding="unicode", method="xml")
                assert "orientedShoot" in text, f"Placemark missing orientedShoot: {text[:200]}"


class TestCLI:
    """CLI smoke tests."""

    def test_cli_help(self):
        from src.cli import main
        import sys
        orig = sys.argv
        try:
            sys.argv = ["area2waypoint", "--help"]
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
        finally:
            sys.argv = orig

    def test_cli_conversion(self, tmp_path):
        out = tmp_path / "converted.kmz"
        from src.cli import main
        import sys
        orig = sys.argv
        try:
            sys.argv = ["area2waypoint", str(AREA_MINIMAL_KMZ), "-o", str(out)]
            rc = main()
            assert rc == 0
            assert out.exists()
        finally:
            sys.argv = orig
