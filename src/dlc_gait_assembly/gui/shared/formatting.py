"""Small presentation-only formatting helpers."""


def format_milliseconds(milliseconds: int) -> str:
    total_seconds, remainder = divmod(max(0, int(milliseconds)), 1000)
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{remainder:03d}"
    return f"{minutes:02d}:{seconds:02d}.{remainder:03d}"
