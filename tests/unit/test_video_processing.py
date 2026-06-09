from pathlib import Path

from dlc_gait_assembly.services import video_processing as video_processing_module
from dlc_gait_assembly.services.video_processing import (
    CropRegion,
    EnhancementSettings,
    NormalizedRect,
    ProcessingOptions,
    TrimRange,
    VideoInfo,
    build_filter_graph,
    normalized_to_pixel_rect,
    output_path_for_input,
    process_video_outputs,
)
from dlc_gait_assembly.services.video_processing import build_processing_command
from dlc_gait_assembly.services.output_documents import write_video_processing_session_documents


def test_build_filter_graph_with_crop_and_invert():
    options = ProcessingOptions(
        crop_enabled=True,
        crop_rect=NormalizedRect(0.1, 0.1, 0.8, 0.8),
        invert_enabled=True,
        invert_rect=NormalizedRect(0.25, 0.25, 0.5, 0.5),
    )

    assert build_filter_graph(1920, 1080, options) == (
        "[0:v]split=2[base_0][region_0];"
        "[region_0]crop=960:540:480:270,vflip[flipped_0];"
        "[base_0][flipped_0]overlay=480:270[v_inverted_0];"
        "[v_inverted_0]crop=1536:864:192:108,format=yuv420p[vout]"
    )


def test_build_filter_graph_uses_single_named_crop_region():
    options = ProcessingOptions(
        crop_enabled=True,
        crop_regions=(CropRegion("Front Paw", NormalizedRect(0.1, 0.1, 0.8, 0.8)),),
    )

    assert build_filter_graph(1920, 1080, options) == "[0:v]crop=1536:864:192:108,format=yuv420p[vout]"


def test_build_filter_graph_flips_cropped_region_output():
    options = ProcessingOptions(
        crop_enabled=True,
        crop_regions=(
            CropRegion(
                "Front Paw",
                NormalizedRect(0.1, 0.1, 0.8, 0.8),
                flip_horizontal=True,
                flip_vertical=True,
            ),
        ),
    )

    assert build_filter_graph(1920, 1080, options) == (
        "[0:v]crop=1536:864:192:108,hflip,vflip,format=yuv420p[vout]"
    )


def test_crop_region_horizontal_flip_resolves_per_input_path(tmp_path):
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"
    selected_region = CropRegion(
        "Front Paw",
        NormalizedRect(0.1, 0.1, 0.8, 0.8),
        flip_horizontal=True,
        flip_horizontal_video_paths=frozenset({str(first.resolve())}),
    )

    assert selected_region.resolved_for_input(first).flip_horizontal is True
    assert selected_region.resolved_for_input(second).flip_horizontal is False


def test_build_filter_graph_with_multiple_invert_regions():
    options = ProcessingOptions(
        invert_enabled=True,
        invert_rects=(
            NormalizedRect(0.1, 0.1, 0.2, 0.2),
            NormalizedRect(0.6, 0.5, 0.2, 0.3),
        ),
    )

    assert build_filter_graph(1000, 800, options) == (
        "[0:v]split=2[base_0][region_0];"
        "[region_0]crop=200:160:100:80,vflip[flipped_0];"
        "[base_0][flipped_0]overlay=100:80[v_inverted_0];"
        "[v_inverted_0]split=2[base_1][region_1];"
        "[region_1]crop=200:240:600:400,vflip[flipped_1];"
        "[base_1][flipped_1]overlay=600:400[v_inverted_1];"
        "[v_inverted_1]format=yuv420p[vout]"
    )


def test_build_filter_graph_with_enhancements_only():
    options = ProcessingOptions(
        enhancements=EnhancementSettings(
            sharpening=0.6,
            cas=0.35,
            brightness=0.1,
            contrast=1.2,
        ),
    )

    assert build_filter_graph(1000, 800, options) == (
        "[0:v]eq=brightness=0.1:contrast=1.2:gamma=1,"
        "unsharp=5:5:0.6:5:5:0,"
        "cas=strength=0.35[v_enhanced];"
        "[v_enhanced]format=yuv420p[vout]"
    )


def test_build_filter_graph_with_no_edits_transcodes_to_mp4_ready_video():
    assert build_filter_graph(1000, 800, ProcessingOptions()) == "[0:v]format=yuv420p[vout]"


def test_build_filter_graph_with_trim_ranges_only():
    options = ProcessingOptions(
        trim_ranges=(
            TrimRange(1000, 4000),
            TrimRange(7000, 9000),
        ),
    )

    assert build_filter_graph(1000, 800, options, source_fps=30.0) == (
        "[0:v]split=2[trim_src_0][trim_src_1];"
        "[trim_src_0]trim=start=1:end=4,setpts=PTS-STARTPTS[vtrim_0];"
        "[trim_src_1]trim=start=7:end=9,setpts=PTS-STARTPTS[vtrim_1];"
        "[vtrim_0][vtrim_1]concat=n=2:v=1:a=0,format=yuv420p[vout]"
    )


def test_build_filter_graph_with_trim_audio():
    options = ProcessingOptions(trim_ranges=(TrimRange(1000, 4000),))

    assert build_filter_graph(1000, 800, options, include_audio=True, source_fps=30.0) == (
        "[0:v]trim=start=1:end=4,setpts=PTS-STARTPTS,format=yuv420p[vout];"
        "[0:a]atrim=start=1:end=4,asetpts=PTS-STARTPTS[aout]"
    )


def test_build_filter_graph_sorts_trim_ranges_by_start_time():
    options = ProcessingOptions(
        trim_ranges=(
            TrimRange(7000, 9000),
            TrimRange(1000, 4000),
        ),
    )

    assert build_filter_graph(1000, 800, options, source_fps=30.0) == (
        "[0:v]split=2[trim_src_0][trim_src_1];"
        "[trim_src_0]trim=start=1:end=4,setpts=PTS-STARTPTS[vtrim_0];"
        "[trim_src_1]trim=start=7:end=9,setpts=PTS-STARTPTS[vtrim_1];"
        "[vtrim_0][vtrim_1]concat=n=2:v=1:a=0,format=yuv420p[vout]"
    )


def test_build_filter_graph_merges_overlapping_trim_ranges():
    options = ProcessingOptions(
        trim_ranges=(
            TrimRange(3000, 5000),
            TrimRange(1000, 4000),
            TrimRange(7000, 8000),
        ),
    )

    assert build_filter_graph(1000, 800, options, source_fps=30.0) == (
        "[0:v]split=2[trim_src_0][trim_src_1];"
        "[trim_src_0]trim=start=1:end=5,setpts=PTS-STARTPTS[vtrim_0];"
        "[trim_src_1]trim=start=7:end=8,setpts=PTS-STARTPTS[vtrim_1];"
        "[vtrim_0][vtrim_1]concat=n=2:v=1:a=0,format=yuv420p[vout]"
    )


def test_build_filter_graph_preserves_timing_for_non_trim_exports():
    options = ProcessingOptions(
        crop_enabled=True,
        crop_rect=NormalizedRect(0.1, 0.1, 0.8, 0.8),
    )

    assert build_filter_graph(1920, 1080, options, source_fps=29.97) == (
        "[0:v]crop=1536:864:192:108,format=yuv420p[vout]"
    )


def test_build_filter_graph_with_trim_ranges_falls_back_to_timestamps_without_fps():
    options = ProcessingOptions(trim_ranges=(TrimRange(1000, 4000),))

    assert build_filter_graph(1000, 800, options) == (
        "[0:v]trim=start=1:end=4,setpts=PTS-STARTPTS,format=yuv420p[vout]"
    )


def test_normalized_rect_is_clamped_and_even_sized():
    rect = normalized_to_pixel_rect(NormalizedRect(0.99, 0.99, 0.5, 0.5), 1921, 1081)

    assert rect.x % 2 == 0
    assert rect.y % 2 == 0
    assert rect.width % 2 == 0
    assert rect.height % 2 == 0
    assert rect.x + rect.width <= 1921
    assert rect.y + rect.height <= 1081


def test_output_path_never_overwrites_input(tmp_path):
    input_path = tmp_path / "clip.mp4"
    input_path.write_bytes(b"not a real video")

    output_path = output_path_for_input(input_path, tmp_path)

    assert output_path != input_path
    assert output_path.name == "clip_processed.mp4"


def test_output_path_uses_unique_name_when_processed_file_exists(tmp_path):
    input_path = tmp_path / "clip.mp4"
    existing_output = tmp_path / "clip_processed.mp4"
    input_path.write_bytes(b"not a real video")
    existing_output.write_bytes(b"existing output")

    output_path = output_path_for_input(input_path, tmp_path)

    assert output_path != input_path
    assert output_path.name == "clip_processed_02.mp4"


def test_output_path_converts_non_mp4_inputs_to_mp4(tmp_path):
    input_path = tmp_path / "clip.avi"
    input_path.write_bytes(b"not a real video")

    output_path = output_path_for_input(input_path, tmp_path)

    assert output_path.suffix == ".mp4"
    assert output_path.name == "clip_processed.mp4"


def test_output_path_appends_crop_region_name_only_when_requested(tmp_path):
    input_path = tmp_path / "clip.mp4"
    input_path.write_bytes(b"not a real video")

    single_region_output = output_path_for_input(input_path, tmp_path, "Front Paw", include_crop_region_name=False)
    multi_region_output = output_path_for_input(input_path, tmp_path, "Front Paw", include_crop_region_name=True)

    assert single_region_output.name == "clip_processed.mp4"
    assert multi_region_output.name == "clip_processed_Front_Paw.mp4"


def test_process_video_outputs_writes_multiple_crop_regions_to_region_folders(tmp_path, monkeypatch):
    input_path = tmp_path / "clip.mp4"
    input_path.write_bytes(b"not a real video")

    monkeypatch.setattr(video_processing_module.shutil, "which", lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else None)
    monkeypatch.setattr(
        video_processing_module,
        "probe_video",
        lambda path: VideoInfo(width=1000, height=800, fps=30.0, frame_count=300, duration_seconds=10.0),
    )

    def fake_run(command, capture_output=True, text=True, check=False):
        class Completed:
            returncode = 0
            stdout = ""
            stderr = ""

        return Completed()

    monkeypatch.setattr(video_processing_module.subprocess, "run", fake_run)

    results = process_video_outputs(
        input_path,
        tmp_path / "session",
        ProcessingOptions(
            crop_enabled=True,
            crop_regions=(
                CropRegion("Front Paw", NormalizedRect(0.0, 0.0, 0.4, 0.4)),
                CropRegion("Rear Paw", NormalizedRect(0.5, 0.0, 0.4, 0.4)),
            ),
        ),
    )

    assert [result.output_path.relative_to(tmp_path / "session") for result in results] == [
        Path("Front_Paw") / "clip_processed.mp4",
        Path("Rear_Paw") / "clip_processed.mp4",
    ]
    assert (tmp_path / "session" / "Front_Paw").is_dir()
    assert (tmp_path / "session" / "Rear_Paw").is_dir()


def test_processing_command_exports_h264_mp4(tmp_path):
    command = build_processing_command(
        ffmpeg_path="/usr/bin/ffmpeg",
        input_path=tmp_path / "clip.mov",
        output_path=tmp_path / "clip_processed.mp4",
        filter_graph="[0:v]format=yuv420p[vout]",
        options=ProcessingOptions(crf=18, preset="slow"),
        has_trim=False,
        include_trim_audio=False,
    )

    assert command[0] == "/usr/bin/ffmpeg"
    assert command[command.index("-c:v") + 1] == "libx264"
    assert command[command.index("-profile:v") + 1] == "high"
    assert command[command.index("-tag:v") + 1] == "avc1"
    assert command[command.index("-preset") + 1] == "slow"
    assert command[command.index("-crf") + 1] == "18"
    assert command[command.index("-pix_fmt") + 1] == "yuv420p"
    assert command[command.index("-c:a") + 1] == "aac"
    assert command[command.index("-f") + 1] == "mp4"
    assert command[-1].endswith(".mp4")


def test_video_processing_session_documents_describe_outputs_and_edits(tmp_path):
    input_path = tmp_path / "clip.avi"
    output_path = tmp_path / "session" / "clip_processed.mp4"
    input_path.write_bytes(b"not a real video")
    output_path.parent.mkdir()
    output_path.write_bytes(b"not a real output")

    options = ProcessingOptions(
        crop_enabled=True,
        crop_regions=(
            CropRegion("Front", NormalizedRect(0.1, 0.2, 0.3, 0.4)),
            CropRegion("Rear", NormalizedRect(0.5, 0.2, 0.3, 0.4)),
        ),
        invert_enabled=True,
        invert_rects=(NormalizedRect(0.5, 0.5, 0.2, 0.2),),
        trim_ranges=(TrimRange(1000, 3000),),
        crf=16,
        preset="slow",
    )

    paths = write_video_processing_session_documents(
        output_path.parent,
        [input_path],
        [(str(input_path), str(output_path))],
        [],
        options,
        {str(input_path.resolve()): (TrimRange(1000, 3000),)},
    )

    manifest = paths["manifest"].read_text(encoding="utf-8")
    summary = paths["summary"].read_text(encoding="utf-8")
    assert '"video_codec": "H.264"' in manifest
    assert '"container": "mp4"' in manifest
    assert '"completed": 1' in manifest
    assert '"outputs": 1' in manifest
    assert '"crop_regions"' in manifest
    assert "Region flips: vertical overlays: 1" in summary
    assert "Front" in summary
    assert "Rear" in summary
    assert "1000 ms to 3000 ms" in summary


def test_video_processing_session_documents_keep_multiple_outputs_per_input(tmp_path):
    input_path = tmp_path / "clip.avi"
    output_dir = tmp_path / "session"
    front_output = output_dir / "clip_processed_Front.mp4"
    rear_output = output_dir / "clip_processed_Rear.mp4"
    input_path.write_bytes(b"not a real video")
    output_dir.mkdir()
    front_output.write_bytes(b"not a real output")
    rear_output.write_bytes(b"not a real output")

    paths = write_video_processing_session_documents(
        output_dir,
        [input_path],
        [(str(input_path), str(front_output)), (str(input_path), str(rear_output))],
        [],
        ProcessingOptions(
            crop_enabled=True,
            crop_regions=(
                CropRegion("Front", NormalizedRect(0.1, 0.2, 0.3, 0.4)),
                CropRegion("Rear", NormalizedRect(0.5, 0.2, 0.3, 0.4)),
            ),
        ),
        {},
    )

    manifest = paths["manifest"].read_text(encoding="utf-8")
    summary = paths["summary"].read_text(encoding="utf-8")
    assert '"outputs": 2' in manifest
    assert str(front_output.resolve()) in manifest
    assert str(rear_output.resolve()) in manifest
    assert "- Outputs:" in summary
