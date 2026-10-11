"""Apply the established treadmill and spontaneous stride acceptance rules."""


def treadmill_cycle_accepted(length, height, minimum_length, maximum_length, maximum_height):
    return length >= minimum_length and length <= maximum_length and height >= 0 and height <= maximum_height


def spontaneous_cycle_accepted(
    length, height, minimum_length, maximum_length, minimum_height, maximum_height, disable_filter=False
):
    return disable_filter or (
        length >= minimum_length and length <= maximum_length and height >= minimum_height and height <= maximum_height
    )


def dragging_dominates_recording(angle_change, np):
    return len(np.where(np.abs(angle_change) < 1)[0]) / len(angle_change) > 0.95
