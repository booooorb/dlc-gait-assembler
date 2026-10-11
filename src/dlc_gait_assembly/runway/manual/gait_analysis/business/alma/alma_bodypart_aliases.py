"""Resolve ALMA body-part labels and preserve established anatomical aliases."""

from __future__ import annotations


def normalize_bodypart_label(label):
    return " ".join(label.strip().lower().replace("_", " ").replace("-", " ").split())


def detect_bodypart_mapping(bodyparts_detected):
    """
    Auto-detect bodypart naming convention and create mapping to standard names.
    Handles: 'toe'/'toeR'/'toeL', 'iliac crest'/'crestR', etc.
    Returns: dict mapping detected names to standard names, and list of standard bodyparts
    """
    bodypart_aliases = {
        "toe": ["back_toe", "back toe tip", "toe", "toer", "toel", "toe_r", "toe_l"],
        "mtp": ["mtp", "mtpr", "mtpl", "mtp_r", "mtp_l"],
        "ankle": ["ankle", "ankler", "anklel", "ankle_r", "ankle_l"],
        "knee": ["knee", "kneer", "kneel", "knee_r", "knee_l"],
        "hip": ["hip", "hipr", "hipl", "hip_r", "hip_l"],
        "iliac crest": [
            "iliac crest",
            "crest",
            "crestr",
            "crestl",
            "crest_r",
            "crest_l",
            "iliac crestr",
            "iliac crestl",
            "iliacr",
            "iliacl",
            "l-iliac-crest",
            "r-iliac-crest",
            "iliac-crest",
            "iliac_crest",
        ],
    }
    mapping = {}
    found_bodyparts = []
    normalized_aliases = {
        standard: {normalize_bodypart_label(alias) for alias in aliases}
        for (standard, aliases) in bodypart_aliases.items()
    }
    for detected in bodyparts_detected:
        detected_normalized = normalize_bodypart_label(detected)
        for standard, aliases in normalized_aliases.items():
            if detected_normalized in aliases:
                mapping[detected] = standard
                if standard not in found_bodyparts:
                    found_bodyparts.append(standard)
                break
    if not mapping:
        return ({bp: bp for bp in bodyparts_detected}, bodyparts_detected)
    return (mapping, found_bodyparts)


def fix_column_names(pd_dataframe, custom_mapping=None):
    header_1 = pd_dataframe.columns.get_level_values(0)
    header_2 = pd_dataframe.columns.get_level_values(1)
    col_names = []
    bodyparts_raw = []
    for i in range(len(header_1)):
        col_names.append(" ".join([header_1[i], header_2[i]]))
    for column in col_names:
        if column.endswith(" y"):
            bodyparts_raw.append(column.strip(" y"))
    (auto_mapping, auto_bodyparts) = detect_bodypart_mapping(bodyparts_raw)
    if custom_mapping is not None:
        bodypart_mapping = {**auto_mapping, **custom_mapping}
        bodyparts_standard = []
        for bodypart in [*custom_mapping.values(), *auto_bodyparts]:
            if bodypart not in bodyparts_standard:
                bodyparts_standard.append(bodypart)
    else:
        bodypart_mapping = auto_mapping
        bodyparts_standard = auto_bodyparts
    col_names_standard = []
    for col in col_names:
        parts = col.rsplit(" ", 1)
        if len(parts) == 2:
            (bodypart_name, coord) = parts
            standard_name = bodypart_mapping.get(bodypart_name, bodypart_name)
            col_names_standard.append(f"{standard_name} {coord}")
        else:
            col_names_standard.append(col)
    pd_dataframe.columns = col_names_standard
    return (pd_dataframe, bodyparts_standard, bodyparts_raw)
