"""Correct marker trajectories for treadmill movement and walking direction."""

from __future__ import annotations

import numpy as np


def treadmill_correction(pd_dataframe, bodyparts, px_speed=8.09, right_to_left=True):
    """
    Correct for treadmill movement in x coordinates

    Parameters:
    -----------
    pd_dataframe : DataFrame with bodypart coordinates
    bodyparts : list or str of bodypart names
    px_speed : treadmill speed in pixels/frame
    right_to_left : bool
        If True: mouse walks right-to-left, treadmill moves left-to-right
                 correction = -(x - treadmill_shift)
        If False: mouse walks left-to-right, treadmill moves right-to-left
                 correction = x + treadmill_shift

    Explanation:
    - Right-to-left (typical): Mouse at position 100px, after 10 frames treadmill moved 80px right
      Without correction: mouse appears at 180px (moved by treadmill)
      With correction: -(180 - 80) = -100px (removes treadmill effect)

    - Left-to-right: Opposite signs needed
    """
    correction = np.arange(0, len(pd_dataframe), 1)
    correction = correction * px_speed
    if type(bodyparts) is list and len(bodyparts) > 1:
        for bodypart in bodyparts:
            if right_to_left:
                pd_dataframe[f"{bodypart} x"] = -(pd_dataframe[f"{bodypart} x"] - correction)
            else:
                pd_dataframe[f"{bodypart} x"] = pd_dataframe[f"{bodypart} x"] + correction
    elif type(bodyparts) is list and len(bodyparts) == 1:
        if right_to_left:
            pd_dataframe[f"{bodyparts[0]} x"] = -(pd_dataframe[f"{bodyparts[0]} x"] - correction)
        else:
            pd_dataframe[f"{bodyparts[0]} x"] = pd_dataframe[f"{bodyparts[0]} x"] + correction
    elif type(bodyparts) is str:
        if right_to_left:
            pd_dataframe[f"{bodyparts} x"] = -(pd_dataframe[f"{bodyparts} x"] - correction)
        else:
            pd_dataframe[f"{bodyparts} x"] = pd_dataframe[f"{bodyparts} x"] + correction
    return pd_dataframe
