"""Parse waylines.wpml and extract path + action groups."""

import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, List

WPML_NS = "http://www.dji.com/wpmz/1.0.6"
KML_NS = "http://www.opengis.net/kml/2.2"


def _tag(name):
    return "{{{}}}{}".format(WPML_NS, name)


def _find_text(el: Optional[ET.Element], child: str, default: str = "") -> str:
    if el is None:
        return default
    c = el.find(child, namespaces={"wpml": WPML_NS})
    return c.text.strip() if c is not None and c.text else default


def _find_text_ns(el: Optional[ET.Element], tag: str) -> str:
    if el is None:
        return ""
    c = el.find(tag)
    return c.text.strip() if c is not None and c.text else ""


class PathPoint:
    """Single point along the flight path."""

    def __init__(self, index, lon, lat, execute_height, waypoint_heading_angle,
                 waypoint_speed, gimbal_pitch, gimbal_yaw):
        self.index = index
        self.lon = lon
        self.lat = lat
        self.execute_height = execute_height
        self.waypoint_heading_angle = waypoint_heading_angle
        self.waypoint_speed = waypoint_speed
        self.gimbal_pitch = gimbal_pitch
        self.gimbal_yaw = gimbal_yaw


class ActionGroup:
    """Action group with trigger (e.g. multipleDistance)."""

    def __init__(self, group_id, start_index, end_index, mode, trigger_type,
                 trigger_param, has_take_photo, gimbal_pitch, gimbal_yaw,
                 payload_lens_index):
        self.group_id = group_id
        self.start_index = start_index
        self.end_index = end_index
        self.mode = mode
        self.trigger_type = trigger_type
        self.trigger_param = trigger_param
        self.has_take_photo = has_take_photo
        self.gimbal_pitch = gimbal_pitch
        self.gimbal_yaw = gimbal_yaw
        self.payload_lens_index = payload_lens_index


class ParsedWayline:
    """Single wayline (route) from area mission: ortho or oblique."""

    def __init__(self, wayline_id, template_id, points, action_groups, auto_flight_speed):
        self.wayline_id = wayline_id
        self.template_id = template_id
        self.points = points
        self.action_groups = action_groups
        self.auto_flight_speed = auto_flight_speed


class ParsedWaylines:
    """Parsed waylines.wpml content. Holds multiple waylines (ortho + oblique)."""

    def __init__(self):
        self.waylines = []  # List[ParsedWayline] - ortho first (waylineId 0), then oblique
        self.points = []  # First wayline's points (backward compat)
        self.action_groups = []  # First wayline's action groups (backward compat)
        self.mission_config = {}
        self.drone_info = {}
        self.payload_info = {}
        self.auto_flight_speed = 1.0
        self.execute_height_mode = "relativeToStartPoint"


def _parse_placemark(pm, ns) -> Optional[PathPoint]:
    coords_el = pm.find(".//{{{}}}coordinates".format(KML_NS))
    if coords_el is None or not coords_el.text:
        return None

    parts = coords_el.text.strip().split(",")
    if len(parts) < 2:
        return None
    lon = float(parts[0].strip())
    lat = float(parts[1].strip())

    idx_el = pm.find(_tag("index"))
    index = int(idx_el.text) if idx_el is not None and idx_el.text else -1

    exec_el = pm.find(_tag("executeHeight"))
    execute_height = float(exec_el.text) if exec_el is not None and exec_el.text else 0.0

    speed_el = pm.find(_tag("waypointSpeed"))
    waypoint_speed = float(speed_el.text) if speed_el is not None and speed_el.text else 1.0

    heading_el = pm.find(f".//{_tag('waypointHeadingParam')}/{_tag('waypointHeadingAngle')}")
    heading = float(heading_el.text) if heading_el is not None and heading_el.text else 0.0

    gimbal_el = pm.find(f".//{_tag('waypointGimbalHeadingParam')}")
    gimbal_pitch = 0.0
    gimbal_yaw = 0.0
    if gimbal_el is not None:
        p = gimbal_el.find(_tag("waypointGimbalPitchAngle"))
        y = gimbal_el.find(_tag("waypointGimbalYawAngle"))
        if p is not None and p.text:
            gimbal_pitch = float(p.text)
        if y is not None and y.text:
            gimbal_yaw = float(y.text)

    return PathPoint(
        index=index,
        lon=lon,
        lat=lat,
        execute_height=execute_height,
        waypoint_heading_angle=heading,
        waypoint_speed=waypoint_speed,
        gimbal_pitch=gimbal_pitch,
        gimbal_yaw=gimbal_yaw,
    )


def _parse_action_group(ag_el) -> Optional[ActionGroup]:
    gid = int(ag_el.find(_tag("actionGroupId")).text or "0")
    start = int(ag_el.find(_tag("actionGroupStartIndex")).text or "0")
    end = int(ag_el.find(_tag("actionGroupEndIndex")).text or "0")
    mode = _find_text_ns(ag_el, _tag("actionGroupMode")) or "sequence"

    trigger_el = ag_el.find(_tag("actionTrigger"))
    trigger_type = ""
    trigger_param: Optional[float] = None
    if trigger_el is not None:
        tt = trigger_el.find(_tag("actionTriggerType"))
        if tt is not None and tt.text:
            trigger_type = tt.text.strip()
        tp = trigger_el.find(_tag("actionTriggerParam"))
        if tp is not None and tp.text:
            try:
                trigger_param = float(tp.text.strip())
            except ValueError:
                pass

    has_take_photo = False
    gimbal_pitch = -90.0
    gimbal_yaw = 0.0
    payload_lens_index = "wide,ir"

    for action_el in ag_el.findall(_tag("action")):
        func = action_el.find(_tag("actionActuatorFunc"))
        if func is not None and func.text:
            func_name = func.text.strip()
            if func_name == "takePhoto":
                has_take_photo = True
                param = action_el.find(_tag("actionActuatorFuncParam"))
                if param is not None:
                    lens = param.find(_tag("payloadLensIndex"))
                    if lens is not None and lens.text:
                        payload_lens_index = lens.text.strip()
            elif func_name == "gimbalRotate":
                param = action_el.find(_tag("actionActuatorFuncParam"))
                if param is not None:
                    p = param.find(_tag("gimbalPitchRotateAngle"))
                    y = param.find(_tag("gimbalYawRotateAngle"))
                    if p is not None and p.text:
                        gimbal_pitch = float(p.text)
                    if y is not None and y.text:
                        gimbal_yaw = float(y.text)

    return ActionGroup(
        group_id=gid,
        start_index=start,
        end_index=end,
        mode=mode,
        trigger_type=trigger_type,
        trigger_param=trigger_param,
        has_take_photo=has_take_photo,
        gimbal_pitch=gimbal_pitch,
        gimbal_yaw=gimbal_yaw,
        payload_lens_index=payload_lens_index,
    )


def parse_waylines_wpml(input_path: Path) -> ParsedWaylines:
    """Parse waylines.wpml from an area mission KMZ."""

    result = ParsedWaylines()

    with zipfile.ZipFile(input_path, "r") as zf:
        try:
            data = zf.read("wpmz/waylines.wpml")
        except KeyError:
            raise FileNotFoundError(f"wpmz/waylines.wpml not found in {input_path}")

    root = ET.fromstring(data)

    # missionConfig
    mc = root.find(".//{}".format(_tag("missionConfig")))
    if mc is not None:
        for child in mc:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag in ("droneInfo", "payloadInfo"):
                continue
            if child.text:
                result.mission_config[tag] = child.text.strip()
        di = mc.find(_tag("droneInfo"))
        if di is not None:
            for c in di:
                t = c.tag.split("}")[-1] if "}" in c.tag else c.tag
                if c.text:
                    result.drone_info[t] = c.text.strip()
        pi = mc.find(_tag("payloadInfo"))
        if pi is not None:
            for c in pi:
                t = c.tag.split("}")[-1] if "}" in c.tag else c.tag
                if c.text:
                    result.payload_info[t] = c.text.strip()

    # Parse all Folders (ortho = waylineId 0, oblique = waylineId 1+)
    folders = root.findall(".//{{{}}}Folder".format(KML_NS))
    for folder in folders:
        mode_el = folder.find(_tag("executeHeightMode"))
        if mode_el is not None and mode_el.text:
            result.execute_height_mode = mode_el.text.strip()

        speed_el = folder.find(_tag("autoFlightSpeed"))
        speed = float(speed_el.text) if speed_el is not None and speed_el.text else 1.0

        tid_el = folder.find(_tag("templateId"))
        wid_el = folder.find(_tag("waylineId"))
        template_id = int(tid_el.text) if tid_el is not None and tid_el.text else 0
        wayline_id = int(wid_el.text) if wid_el is not None and wid_el.text else 0

        points = []
        action_groups = []
        for pm in folder.findall("{{{}}}Placemark".format(KML_NS)):
            pt = _parse_placemark(pm, {"wpml": WPML_NS})
            if pt is not None:
                points.append(pt)
            for ag_el in pm.findall(_tag("actionGroup")):
                ag = _parse_action_group(ag_el)
                if ag is not None:
                    action_groups.append(ag)

        points.sort(key=lambda p: p.index)
        wl = ParsedWayline(
            wayline_id=wayline_id,
            template_id=template_id,
            points=points,
            action_groups=action_groups,
            auto_flight_speed=speed,
        )
        result.waylines.append(wl)

        # First wayline for backward compat
        if not result.points:
            result.points = points
            result.action_groups = action_groups
            result.auto_flight_speed = speed

    return result
