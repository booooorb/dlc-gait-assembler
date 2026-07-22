"""Qt-compatible SVG sanitization shared by preview widgets."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET


def qt_safe_svg_bytes(svg_data: bytes) -> bytes:
    """Remove malformed paths and references that Qt's SVG renderer rejects."""

    try:
        root = ET.fromstring(svg_data)
    except ET.ParseError:
        return svg_data

    parent_by_child = {child: parent for parent in root.iter() for child in parent}
    defined_ids = {
        element_id
        for element in root.iter()
        if (element_id := element.attrib.get("id"))
    }
    unusable_ids = {
        element.attrib["id"]
        for element in root.iter()
        if _local_name(element.tag) == "path"
        and element.attrib.get("id")
        and not element.attrib.get("d", "").strip()
    }
    removed = False
    for element in list(root.iter()):
        parent = parent_by_child.get(element)
        if parent is None:
            continue
        tag = _local_name(element.tag)
        if tag == "path":
            path_data = element.attrib.get("d", "")
            if not path_data.strip() or _has_nonfinite_path_values(path_data):
                parent.remove(element)
                removed = True
                continue
        if tag == "use":
            href = (
                element.attrib.get("{http://www.w3.org/1999/xlink}href")
                or element.attrib.get("href")
                or ""
            )
            if href.startswith("#") and (
                href[1:] not in defined_ids or href[1:] in unusable_ids
            ):
                parent.remove(element)
                removed = True
    if not removed:
        return svg_data
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _has_nonfinite_path_values(path_data: str) -> bool:
    return bool(
        re.search(
            r"(?i)(?:^|[^a-z])(?:nan|inf|-inf|infinity|-infinity)(?:$|[^a-z])",
            path_data,
        )
    )
