"""Calculate limb joint, elevation, and segment-length measurements."""

from __future__ import annotations

import math

import numpy as np


def angle(vector1, vector2):
    length1 = math.sqrt(vector1[0] * vector1[0] + vector1[1] * vector1[1])
    length2 = math.sqrt(vector2[0] * vector2[0] + vector2[1] * vector2[1])
    return math.acos((vector1[0] * vector2[0] + vector1[1] * vector2[1]) / (length1 * length2))


def find_angles(x1, y1, x_center, y_center, x2, y2):
    x1 = x1 - x_center
    y1 = y1 - y_center
    x2 = x2 - x_center
    y2 = y2 - y_center
    return [np.rad2deg(angle([x1[i], y1[i]], [x2[i], y2[i]])) for i in range(len(x1))]


def find_limb_length(x1, y1, x2, y2):
    """
    calculate the Euclidean distance between two endpoints of a limb
    using 4 lists
    """
    return [math.sqrt((x1[i] - x2[i]) ** 2 + (y1[i] - y2[i]) ** 2) for i in range(len(x1))]


def compute_limb_joint_angles(
    smooth_toe_x,
    smooth_toe_y,
    smooth_mtp_x,
    smooth_mtp_y,
    smooth_ankle_x,
    smooth_ankle_y,
    smooth_knee_x,
    smooth_knee_y,
    smooth_hip_x,
    smooth_hip_y,
    smooth_crest_x,
    smooth_crest_y,
):
    angles_toe_mtp_ankle = find_angles(
        smooth_toe_x, smooth_toe_y, smooth_mtp_x, smooth_mtp_y, smooth_ankle_x, smooth_ankle_y
    )
    angles_mtp_ankle_knee = find_angles(
        smooth_mtp_x, smooth_mtp_y, smooth_ankle_x, smooth_ankle_y, smooth_knee_x, smooth_knee_y
    )
    angles_ankle_knee_hip = find_angles(
        smooth_ankle_x, smooth_ankle_y, smooth_knee_x, smooth_knee_y, smooth_hip_x, smooth_hip_y
    )
    angles_knee_hip_crest = find_angles(
        smooth_knee_x, smooth_knee_y, smooth_hip_x, smooth_hip_y, smooth_crest_x, smooth_crest_y
    )
    elevation_angles = find_angles(
        smooth_mtp_x, smooth_mtp_y, smooth_crest_x, smooth_crest_y, smooth_crest_x, np.zeros(len(smooth_crest_y))
    )
    elevation_angle_change = np.diff(elevation_angles)
    return (
        angles_toe_mtp_ankle,
        angles_mtp_ankle_knee,
        angles_ankle_knee_hip,
        angles_knee_hip_crest,
        elevation_angles,
        elevation_angle_change,
    )
