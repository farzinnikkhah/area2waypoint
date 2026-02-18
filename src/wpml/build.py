"""Generate waypoint KMZ with orientedShoot actions."""

import time
import uuid
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from .parse import ParsedWaylines
from .compute import ShotPoint

WPML_NS = "http://www.dji.com/wpmz/1.0.6"
KML_NS = "http://www.opengis.net/kml/2.2"

# Register namespaces so output matches DJI format: default ns for KML, wpml: for WPML
ET.register_namespace("", KML_NS)
ET.register_namespace("wpml", WPML_NS)


def _wpml(tag: str) -> str:
    return f"{{{WPML_NS}}}{tag}"


def _el(parent, tag, text=None, **attrib):
    if "}" in tag:
        child = ET.SubElement(parent, tag, attrib)
    else:
        child = ET.SubElement(parent, _wpml(tag), attrib)
    if text is not None:
        child.text = str(text)
    return child


def _mission_config_el(parsed):
    """Build missionConfig element with proper nested droneInfo and payloadInfo."""
    mc = ET.Element(_wpml("missionConfig"))
    for k, v in parsed.mission_config.items():
        if k in ("droneEnumValue", "droneSubEnumValue", "payloadEnumValue",
                 "payloadSubEnumValue", "payloadPositionIndex"):
            continue
        _el(mc, _wpml(k), v)
    if not parsed.mission_config or "flyToWaylineMode" not in parsed.mission_config:
        _el(mc, _wpml("flyToWaylineMode"), "safely")
        _el(mc, _wpml("finishAction"), "goHome")
        _el(mc, _wpml("exitOnRCLost"), "executeLostAction")
        _el(mc, _wpml("executeRCLostAction"), "goBack")
        _el(mc, _wpml("takeOffSecurityHeight"), "20")
        _el(mc, _wpml("globalTransitionalSpeed"), "15")
    di = ET.SubElement(mc, _wpml("droneInfo"))
    _el(di, "droneEnumValue", parsed.drone_info.get("droneEnumValue", "67"))
    _el(di, "droneSubEnumValue", parsed.drone_info.get("droneSubEnumValue", "0"))
    pi = ET.SubElement(mc, _wpml("payloadInfo"))
    _el(pi, "payloadEnumValue", parsed.payload_info.get("payloadEnumValue", "53"))
    _el(pi, "payloadSubEnumValue", parsed.payload_info.get("payloadSubEnumValue", "2"))
    _el(pi, "payloadPositionIndex", parsed.payload_info.get("payloadPositionIndex", "0"))
    return mc


def _build_folder_for_wayline(
    folder_el, wl, shots, parsed, lens, focal_length
):
    """Add Placemarks for one wayline to a template Folder."""
    for idx, shot in enumerate(shots):
        pm = ET.SubElement(folder_el, f"{{{KML_NS}}}Placemark")
        pt = ET.SubElement(pm, f"{{{KML_NS}}}Point")
        coord = ET.SubElement(pt, f"{{{KML_NS}}}coordinates")
        coord.text = "\n            {:},{:}\n          ".format(shot.lon, shot.lat)

        _el(pm, "index", idx)
        _el(pm, "ellipsoidHeight", "{:.10f}".format(shot.execute_height))
        _el(pm, "height", "{:.10f}".format(shot.execute_height))
        _el(pm, "useGlobalHeight", "1")
        _el(pm, "useGlobalSpeed", "1")
        _el(pm, "useGlobalHeadingParam", "1")
        _el(pm, "useGlobalTurnParam", "1")
        _el(pm, "gimbalPitchAngle", int(round(shot.gimbal_pitch)))
        _el(pm, "useStraightLine", "0")

        ag = ET.SubElement(pm, _wpml("actionGroup"))
        _el(ag, "actionGroupId", idx)
        _el(ag, "actionGroupStartIndex", idx)
        _el(ag, "actionGroupEndIndex", idx)
        _el(ag, "actionGroupMode", "sequence")
        trig = ET.SubElement(ag, _wpml("actionTrigger"))
        _el(trig, "actionTriggerType", "reachPoint")
        ag.append(_oriented_shoot_action(shot, lens, focal_length, for_template=True))

        _el(pm, "isRisky", "0")


def _build_template_kml(
    parsed: ParsedWaylines,
    wayline_shots,
    lens: str = "ir,wide,zoom",
    focal_length: float = 48.0,
) -> bytes:
    """Build template.kml. Uses single template (templateId 0) matching area mission structure
    so Pilot 2 displays all waylines. waylines.wpml has one Folder per route, all templateId 0."""
    root = ET.Element(f"{{{KML_NS}}}kml")
    doc = ET.SubElement(root, f"{{{KML_NS}}}Document")

    ts = int(time.time() * 1000)
    _el(doc, _wpml("createTime"), ts)
    _el(doc, _wpml("updateTime"), ts)
    doc.append(_mission_config_el(parsed))

    # Single template Folder (templateId 0) - first route as reference, like area mission
    wl, shots = wayline_shots[0]
    folder = ET.SubElement(doc, f"{{{KML_NS}}}Folder")
    _el(folder, "templateType", "waypoint")
    _el(folder, "templateId", "0")

    wcsp = ET.SubElement(folder, _wpml("waylineCoordinateSysParam"))
    _el(wcsp, "coordinateMode", "WGS84")
    _el(wcsp, "heightMode", parsed.execute_height_mode)
    _el(wcsp, "positioningType", "GPS")

    _el(folder, "autoFlightSpeed", wl.auto_flight_speed)
    global_height = shots[0].execute_height if shots else 20.0
    _el(folder, "globalHeight", "{:.10f}".format(global_height))
    _el(folder, "caliFlightEnable", "0")
    _el(folder, "gimbalPitchMode", "usePointSetting")
    gh = ET.SubElement(folder, _wpml("globalWaypointHeadingParam"))
    _el(gh, "waypointHeadingMode", "followWayline")
    _el(gh, "waypointHeadingAngle", "0")
    _el(gh, "waypointPoiPoint", "0.000000,0.000000,0.000000")
    _el(gh, "waypointHeadingPoiIndex", "0")
    _el(folder, "globalWaypointTurnMode", "toPointAndStopWithDiscontinuityCurvature")
    _el(folder, "globalUseStraightLine", "1")

    _build_folder_for_wayline(folder, wl, shots, parsed, lens, focal_length)

    payload = ET.SubElement(folder, _wpml("payloadParam"))
    _el(payload, "payloadPositionIndex", "0")
    _el(payload, "meteringMode", "average")
    _el(payload, "dewarpingEnable", "0")
    _el(payload, "returnMode", "singleReturnStrongest")
    _el(payload, "samplingRate", "240000")
    _el(payload, "scanningMode", "nonRepetitive")
    _el(payload, "modelColoringEnable", "0")
    _el(payload, "imageFormat", lens)

    xml_str = ET.tostring(root, encoding="unicode", method="xml")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str).encode("utf-8")


def _oriented_shoot_action(
    shot: ShotPoint, lens: str, focal_length: float, for_template: bool = False
) -> ET.Element:
    """Build orientedShoot action element.
    for_template=True omits payloadLensIndex (use payloadParam.imageFormat instead).
    """
    action = ET.Element(_wpml("action"))
    _el(action, "actionId", "0")
    _el(action, "actionActuatorFunc", "orientedShoot")
    param = ET.SubElement(action, _wpml("actionActuatorFuncParam"))
    _el(param, "gimbalPitchRotateAngle", int(round(shot.gimbal_pitch)))
    _el(param, "gimbalRollRotateAngle", "0")
    _el(param, "gimbalYawRotateAngle", int(round(shot.gimbal_yaw)))
    _el(param, "focusX", "0")
    _el(param, "focusY", "0")
    _el(param, "focusRegionWidth", "0")
    _el(param, "focusRegionHeight", "0")
    _el(param, "focalLength", int(round(focal_length)))
    _el(param, "aircraftHeading", int(round(shot.heading)))
    _el(param, "accurateFrameValid", "0")
    _el(param, "payloadPositionIndex", "0")
    _el(param, "useGlobalPayloadLensIndex", "1")
    if not for_template:
        _el(param, "payloadLensIndex", lens)
    _el(param, "targetAngle", "0")
    uid = str(uuid.uuid4()).replace("-", "")[:32]
    _el(param, "actionUUID", uid)
    _el(param, "imageWidth", "0")
    _el(param, "imageHeight", "0")
    _el(param, "AFPos", "0")
    _el(param, "gimbalPort", "0")
    _el(param, "orientedCameraType", "53")
    _el(param, "orientedFilePath", uid)
    _el(param, "orientedFileMD5", "")
    _el(param, "orientedFileSize", "0")
    _el(param, "orientedPhotoMode", "normalPhoto")
    return action


def _build_waylines_folder(wl, shots, parsed, lens, focal_length, template_id):
    """Build one Folder for waylines.wpml."""
    folder = ET.Element(f"{{{KML_NS}}}Folder")
    _el(folder, "templateId", str(template_id))
    _el(folder, "executeHeightMode", parsed.execute_height_mode)
    _el(folder, "waylineId", str(wl.wayline_id))

    total_dist = 0.0
    for i in range(len(shots) - 1):
        s0, s1 = shots[i], shots[i + 1]
        d = ((s1.lon - s0.lon) ** 2 + (s1.lat - s0.lat) ** 2) ** 0.5 * 111320
        total_dist += d
    _el(folder, "distance", f"{total_dist:.6f}")
    _el(folder, "duration", f"{total_dist / wl.auto_flight_speed:.6f}")
    _el(folder, "autoFlightSpeed", wl.auto_flight_speed)

    for idx, shot in enumerate(shots):
        pm = ET.SubElement(folder, f"{{{KML_NS}}}Placemark")
        pt = ET.SubElement(pm, f"{{{KML_NS}}}Point")
        coord = ET.SubElement(pt, f"{{{KML_NS}}}coordinates")
        coord.text = f"\n            {shot.lon},{shot.lat}\n          "

        _el(pm, "index", idx)
        _el(pm, "executeHeight", f"{shot.execute_height:.10f}")
        _el(pm, "waypointSpeed", wl.auto_flight_speed)
        hp = ET.SubElement(pm, _wpml("waypointHeadingParam"))
        _el(hp, "waypointHeadingMode", "followWayline")
        _el(hp, "waypointHeadingAngle", int(round(shot.heading)))
        _el(hp, "waypointPoiPoint", "0.000000,0.000000,0.000000")
        _el(hp, "waypointHeadingAngleEnable", "0")
        _el(hp, "waypointHeadingPoiIndex", "0")
        tp = ET.SubElement(pm, _wpml("waypointTurnParam"))
        _el(tp, "waypointTurnMode", "toPointAndStopWithDiscontinuityCurvature")
        _el(tp, "waypointTurnDampingDist", "0")
        _el(pm, "useStraightLine", "1")

        ag = ET.SubElement(pm, _wpml("actionGroup"))
        _el(ag, "actionGroupId", idx)
        _el(ag, "actionGroupStartIndex", idx)
        _el(ag, "actionGroupEndIndex", idx)
        _el(ag, "actionGroupMode", "sequence")
        trig = ET.SubElement(ag, _wpml("actionTrigger"))
        _el(trig, "actionTriggerType", "reachPoint")
        ag.append(_oriented_shoot_action(shot, lens, focal_length))

        gh = ET.SubElement(pm, _wpml("waypointGimbalHeadingParam"))
        _el(gh, "waypointGimbalPitchAngle", "0")
        _el(gh, "waypointGimbalYawAngle", "0")
        _el(pm, "isRisky", "0")
        _el(pm, "waypointWorkType", "0")

    return folder


def _build_waylines_wpml(
    parsed: ParsedWaylines,
    wayline_shots,
    lens: str = "ir,wide,zoom",
    focal_length: float = 48.0,
) -> bytes:
    """Build waylines.wpml with one Folder per wayline (ortho + oblique)."""
    root = ET.Element(f"{{{KML_NS}}}kml")
    doc = ET.SubElement(root, f"{{{KML_NS}}}Document")
    doc.append(_mission_config_el(parsed))

    for wl, shots in wayline_shots:
        folder = _build_waylines_folder(
            wl, shots, parsed, lens, focal_length, template_id=0
        )
        doc.append(folder)

    xml_str = ET.tostring(root, encoding="unicode", method="xml")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str).encode("utf-8")


def build_waypoint_kmz(
    parsed: ParsedWaylines,
    wayline_shots,
    output_path: Path,
    lens: str = "ir,wide,zoom",
    focal_length: float = 48.0,
) -> None:
    """Write waypoint KMZ with template.kml and waylines.wpml.
    wayline_shots: List[Tuple[ParsedWayline, List[ShotPoint]]]
    """
    template_xml = _build_template_kml(
        parsed, wayline_shots, lens=lens, focal_length=focal_length
    )
    waylines_xml = _build_waylines_wpml(
        parsed, wayline_shots, lens=lens, focal_length=focal_length
    )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("wpmz/template.kml", template_xml)
        zf.writestr("wpmz/waylines.wpml", waylines_xml)
