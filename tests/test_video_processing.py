from dlc_gait_assembly.video_processing import (
    NormalizedRect,
    ProcessingOptions,
    build_filter_graph,
    normalized_to_pixel_rect,
)


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


def test_normalized_rect_is_clamped_and_even_sized():
    rect = normalized_to_pixel_rect(NormalizedRect(0.99, 0.99, 0.5, 0.5), 1921, 1081)

    assert rect.x % 2 == 0
    assert rect.y % 2 == 0
    assert rect.width % 2 == 0
    assert rect.height % 2 == 0
    assert rect.x + rect.width <= 1921
    assert rect.y + rect.height <= 1081
