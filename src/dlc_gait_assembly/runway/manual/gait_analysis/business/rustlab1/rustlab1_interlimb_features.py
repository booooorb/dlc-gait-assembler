"""Calculate coordination and support measurements between bottom-view paws."""

from __future__ import annotations

from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_cycle_statistics import slice as _slice


def rustlab1_stance_mask(series, marker, np, threshold: float = 7.0):
    x = _slice(series, marker, "x", slice(None))
    if x is None or len(x) == 0:
        return None
    speed = np.abs(np.diff(x, prepend=x[0]))
    stance = np.isfinite(speed) & (speed <= threshold)
    if len(stance) > 1:
        stance[0] = stance[1]
    return stance


def write_interlimb_coordination(output, row_index, stance_masks, cycle_slice, np) -> None:
    if not {"FLBR_RATIO", "FRBL_RATIO"}.intersection(output.columns):
        return
    markers = ("d-front-left", "d-front-right", "d-back-left", "d-back-right")
    if any(stance_masks.get(marker) is None for marker in markers):
        return
    (fl, fr, bl, br) = (np.asarray(stance_masks[marker][cycle_slice], dtype=bool) for marker in markers)
    length = min(map(len, (fl, fr, bl, br)))
    if length == 0:
        return
    (fl, fr, bl, br) = (values[:length] for values in (fl, fr, bl, br))
    included = ~(fl & fr & bl & br)
    if not np.any(included):
        return
    if "FLBR_RATIO" in output.columns:
        output.at[row_index, "FLBR_RATIO"] = float(np.mean(fl[included] != br[included]))
    if "FRBL_RATIO" in output.columns:
        output.at[row_index, "FRBL_RATIO"] = float(np.mean(fr[included] != bl[included]))
