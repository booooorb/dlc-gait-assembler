from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math
import shutil
import struct

import pytest

from dlc_gait_assembly.video_processing import (
    NormalizedRect,
    ProcessingOptions,
    TrimRange,
    normalized_to_pixel_rect,
    process_video,
)


FPS_TOLERANCE = 0.01
PSNR_MINIMUM_DB = 32.0
VIDEO_FIXTURE_NAME = "2019_09_19_RW_DRUGS_23.2099782.20190919151537.mp4"


@dataclass(frozen=True)
class VideoMetadata:
    width: int
    height: int
    frame_count: int
    fps: float
    duration_seconds: float
    stts_entries: tuple[tuple[int, int], ...]


def test_regional_inversion_preserves_timing_resolution_and_quality(tmp_path, video_fixtures_dir):
    fixture_video = _fixture_video(video_fixtures_dir)
    cv2, np = _require_video_stack(fixture_video)
    edit_rect = NormalizedRect(0.1, 0.1, 0.2, 0.2)
    source = _read_video_metadata(fixture_video, cv2)

    result = process_video(
        fixture_video,
        tmp_path,
        ProcessingOptions(invert_enabled=True, invert_rects=(edit_rect,)),
    )
    output = _read_video_metadata(result.output_path, cv2)

    assert output.width == source.width
    assert output.height == source.height
    assert output.frame_count == source.frame_count
    assert output.duration_seconds == pytest.approx(source.duration_seconds, abs=_frame_duration(source))
    assert output.fps == pytest.approx(source.fps, abs=FPS_TOLERANCE)
    assert len(output.stts_entries) == 1

    for frame_index in _sample_frame_indices(source.frame_count):
        original_frame = _read_frame(fixture_video, frame_index, cv2)
        output_frame = _read_frame(result.output_path, frame_index, cv2)
        psnr = _masked_psnr(original_frame, output_frame, edit_rect, np)
        assert psnr >= PSNR_MINIMUM_DB


def test_h264_mp4_transcode_preserves_timing_resolution_and_quality(tmp_path, video_fixtures_dir):
    fixture_video = _fixture_video(video_fixtures_dir)
    cv2, np = _require_video_stack(fixture_video)
    source = _read_video_metadata(fixture_video, cv2)

    result = process_video(fixture_video, tmp_path, ProcessingOptions())
    output = _read_video_metadata(result.output_path, cv2)

    assert result.output_path.suffix == ".mp4"
    assert output.width == source.width
    assert output.height == source.height
    assert output.frame_count == source.frame_count
    assert output.duration_seconds == pytest.approx(source.duration_seconds, abs=_frame_duration(source))
    assert output.fps == pytest.approx(source.fps, abs=FPS_TOLERANCE)
    assert len(output.stts_entries) == 1

    for frame_index in _sample_frame_indices(source.frame_count):
        original_frame = _read_frame(fixture_video, frame_index, cv2)
        output_frame = _read_frame(result.output_path, frame_index, cv2)
        assert _psnr(original_frame, output_frame, np) >= PSNR_MINIMUM_DB


def test_crop_preserves_timing_and_uses_expected_resolution(tmp_path, video_fixtures_dir):
    fixture_video = _fixture_video(video_fixtures_dir)
    cv2, _np = _require_video_stack(fixture_video)
    crop_rect = NormalizedRect(0.1, 0.1, 0.8, 0.8)
    source = _read_video_metadata(fixture_video, cv2)
    expected_crop = normalized_to_pixel_rect(crop_rect, source.width, source.height)

    result = process_video(
        fixture_video,
        tmp_path,
        ProcessingOptions(crop_enabled=True, crop_rect=crop_rect),
    )
    output = _read_video_metadata(result.output_path, cv2)

    assert output.width == expected_crop.width
    assert output.height == expected_crop.height
    assert output.frame_count == source.frame_count
    assert output.duration_seconds == pytest.approx(source.duration_seconds, abs=_frame_duration(source))
    assert output.fps == pytest.approx(source.fps, abs=FPS_TOLERANCE)
    assert len(output.stts_entries) == 1


def test_trim_preserves_resolution_and_fps_while_matching_requested_duration(tmp_path, video_fixtures_dir):
    fixture_video = _fixture_video(video_fixtures_dir)
    cv2, _np = _require_video_stack(fixture_video)
    source = _read_video_metadata(fixture_video, cv2)
    trim_ranges = (
        TrimRange(1000, 3000),
        TrimRange(4000, 5500),
    )
    expected_duration = sum(trim.end_seconds() - trim.start_seconds() for trim in trim_ranges)
    expected_frames = round(expected_duration * source.fps)

    result = process_video(
        fixture_video,
        tmp_path,
        ProcessingOptions(trim_ranges=trim_ranges),
    )
    output = _read_video_metadata(result.output_path, cv2)

    assert output.width == source.width
    assert output.height == source.height
    assert output.frame_count == pytest.approx(expected_frames, abs=1)
    assert output.duration_seconds == pytest.approx(expected_duration, abs=_frame_duration(source) * 2)
    assert output.fps == pytest.approx(source.fps, abs=FPS_TOLERANCE)
    assert len(output.stts_entries) == 1


def _fixture_video(video_fixtures_dir: Path) -> Path:
    return video_fixtures_dir / VIDEO_FIXTURE_NAME


def _require_video_stack(fixture_video: Path):
    if not fixture_video.exists():
        pytest.skip(f"Missing video fixture: {fixture_video}")
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is required for video processing integration tests.")

    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    return cv2, np


def _read_video_metadata(path: Path, cv2) -> VideoMetadata:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise AssertionError(f"Could not open video: {path}")

    try:
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = float(capture.get(cv2.CAP_PROP_FPS))
    finally:
        capture.release()

    timing = _read_mp4_timing(path)
    duration = timing.duration_seconds if timing is not None else frame_count / fps
    entries = timing.stts_entries if timing is not None else ()

    return VideoMetadata(
        width=width,
        height=height,
        frame_count=frame_count,
        fps=fps,
        duration_seconds=duration,
        stts_entries=entries,
    )


def _read_frame(path: Path, frame_index: int, cv2):
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise AssertionError(f"Could not open video: {path}")

    try:
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = capture.read()
    finally:
        capture.release()

    if not ok or frame is None:
        raise AssertionError(f"Could not read frame {frame_index} from {path}")
    return frame


def _sample_frame_indices(frame_count: int) -> tuple[int, ...]:
    if frame_count <= 1:
        return (0,)
    return (0, frame_count // 2, frame_count - 1)


def _masked_psnr(original, output, edited_rect: NormalizedRect, np) -> float:
    if original.shape != output.shape:
        raise AssertionError(f"Frame shape changed from {original.shape} to {output.shape}")

    height, width = original.shape[:2]
    mask = np.ones((height, width), dtype=bool)
    excluded = normalized_to_pixel_rect(edited_rect, width, height)
    margin = 16
    left = max(0, excluded.x - margin)
    top = max(0, excluded.y - margin)
    right = min(width, excluded.x + excluded.width + margin)
    bottom = min(height, excluded.y + excluded.height + margin)
    mask[top:bottom, left:right] = False

    diff = original[mask].astype("float32") - output[mask].astype("float32")
    mse = float(np.mean(diff * diff))
    if mse <= 0.0:
        return math.inf
    return 20.0 * math.log10(255.0 / math.sqrt(mse))


def _psnr(original, output, np) -> float:
    if original.shape != output.shape:
        raise AssertionError(f"Frame shape changed from {original.shape} to {output.shape}")

    diff = original.astype("float32") - output.astype("float32")
    mse = float(np.mean(diff * diff))
    if mse <= 0.0:
        return math.inf
    return 20.0 * math.log10(255.0 / math.sqrt(mse))


def _frame_duration(metadata: VideoMetadata) -> float:
    if metadata.fps <= 0:
        return 0.05
    return 1.0 / metadata.fps


@dataclass(frozen=True)
class Mp4Timing:
    duration_seconds: float
    stts_entries: tuple[tuple[int, int], ...]


def _read_mp4_timing(path: Path) -> Mp4Timing | None:
    if path.suffix.lower() not in {".mp4", ".m4v", ".mov"}:
        return None

    data = path.read_bytes()
    moov = _find_child(data, 0, len(data), "moov")
    if moov is None:
        return None

    _moov_pos, moov_end, moov_payload = moov
    for atom, _trak_pos, trak_end, trak_payload in _children(data, moov_payload, moov_end):
        if atom != "trak":
            continue
        mdia = _find_child(data, trak_payload, trak_end, "mdia")
        if mdia is None:
            continue

        _mdia_pos, mdia_end, mdia_payload = mdia
        hdlr = _find_child(data, mdia_payload, mdia_end, "hdlr")
        if hdlr is None or _handler_type(data, hdlr[2]) != "vide":
            continue

        mdhd = _find_child(data, mdia_payload, mdia_end, "mdhd")
        minf = _find_child(data, mdia_payload, mdia_end, "minf")
        stbl = _find_child(data, minf[2], minf[1], "stbl") if minf is not None else None
        stts = _find_child(data, stbl[2], stbl[1], "stts") if stbl is not None else None
        if mdhd is None or stts is None:
            return None

        timescale, _duration_ticks = _mdhd_timescale_and_duration(data, mdhd[2])
        entries = tuple(_stts_entries(data, stts[2]))
        ticks = sum(count * delta for count, delta in entries)
        duration = ticks / timescale if timescale else 0.0
        return Mp4Timing(duration_seconds=duration, stts_entries=entries)

    return None


def _children(data: bytes, start: int, end: int):
    position = start
    while position + 8 <= end:
        size = struct.unpack(">I", data[position : position + 4])[0]
        atom = data[position + 4 : position + 8].decode("latin1")
        header_size = 8

        if size == 1:
            if position + 16 > end:
                break
            size = struct.unpack(">Q", data[position + 8 : position + 16])[0]
            header_size = 16
        elif size == 0:
            size = end - position

        if size < header_size or position + size > end:
            break

        yield atom, position, position + size, position + header_size
        position += size


def _find_child(data: bytes, start: int, end: int, name: str):
    for atom, position, atom_end, payload in _children(data, start, end):
        if atom == name:
            return position, atom_end, payload
    return None


def _handler_type(data: bytes, payload: int) -> str:
    return data[payload + 8 : payload + 12].decode("latin1")


def _mdhd_timescale_and_duration(data: bytes, payload: int) -> tuple[int, int]:
    version = data[payload]
    if version == 1:
        offset = payload + 20
        timescale = struct.unpack(">I", data[offset : offset + 4])[0]
        duration = struct.unpack(">Q", data[offset + 4 : offset + 12])[0]
    else:
        offset = payload + 12
        timescale = struct.unpack(">I", data[offset : offset + 4])[0]
        duration = struct.unpack(">I", data[offset + 4 : offset + 8])[0]
    return timescale, duration


def _stts_entries(data: bytes, payload: int) -> list[tuple[int, int]]:
    entry_count = struct.unpack(">I", data[payload + 4 : payload + 8])[0]
    entries = []
    offset = payload + 8
    for _index in range(entry_count):
        if offset + 8 > len(data):
            break
        entries.append(struct.unpack(">II", data[offset : offset + 8]))
        offset += 8
    return entries
