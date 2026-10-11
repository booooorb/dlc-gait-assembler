"""Apply confidence masks without inventing low-confidence joint coordinates."""

from __future__ import annotations

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import ALMA_BODYPARTS


def filter_low_confidence_coordinates(dataframe, threshold: float, pd):
    threshold = float(threshold or 0.0)
    if threshold <= 0:
        return (dataframe, None, ())
    bodypart_masks = {}
    for bodypart in ALMA_BODYPARTS:
        likelihood_column = f"{bodypart} likelihood"
        if likelihood_column not in dataframe.columns:
            continue
        likelihood = pd.to_numeric(dataframe[likelihood_column], errors="coerce")
        valid = likelihood.ge(threshold).fillna(False)
        if not bool(valid.any()):
            raise ValueError(
                f"Tracking confidence filter removed every {bodypart} point at likelihood cutoff {threshold:.2f}. Lower the cutoff, set it to 0, or check body-part mapping."
            )
        bodypart_masks[bodypart] = valid
    if not bodypart_masks:
        return (dataframe, None, ("Tracking confidence filter skipped: no ALMA likelihood columns were found.",))
    valid_mask = pd.DataFrame(bodypart_masks, index=dataframe.index)
    low_confidence_count = int((~valid_mask).sum().sum())
    total_count = int(valid_mask.shape[0] * valid_mask.shape[1])
    if low_confidence_count == 0:
        return (
            dataframe,
            valid_mask,
            (f"Tracking confidence filter: all frames met the {threshold:.2f} likelihood cutoff.",),
        )
    filtered = dataframe.copy()
    filtered_any_coordinates = False
    for bodypart, valid in bodypart_masks.items():
        coordinate_columns = [column for column in (f"{bodypart} x", f"{bodypart} y") if column in filtered.columns]
        if not coordinate_columns:
            continue
        filtered_any_coordinates = True
        filtered.loc[~valid, coordinate_columns] = float("nan")
        interpolated = (
            filtered.loc[:, coordinate_columns]
            .apply(pd.to_numeric, errors="coerce")
            .interpolate(method="linear", limit_direction="both")
        )
        if interpolated.isna().any().any():
            raise ValueError(f"Tracking confidence filter could not interpolate {bodypart} at cutoff {threshold:.2f}.")
        filtered.loc[:, coordinate_columns] = interpolated
    if not filtered_any_coordinates:
        return (
            dataframe,
            valid_mask,
            ("Tracking confidence filter skipped: no ALMA x/y coordinate columns were found.",),
        )
    message = f"Tracking confidence filter: interpolated {low_confidence_count}/{total_count} low-confidence marker sample(s) below {threshold:.2f} for parameter extraction and hid those marker positions from stickplots."
    return (filtered, valid_mask, (message,))


def hide_low_confidence_stickplot_frames(coords, valid_mask):
    if len(coords) != len(valid_mask):
        return coords
    masked = coords.copy()
    for bodypart in valid_mask.columns:
        coordinate_columns = [column for column in (f"{bodypart} x", f"{bodypart} y") if column in masked.columns]
        if coordinate_columns:
            masked.loc[~valid_mask[bodypart].to_numpy(), coordinate_columns] = float("nan")
    return masked
