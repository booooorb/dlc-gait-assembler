from dlc_gait_assembly.shared.infrastructure.svg_preview_sanitizer import qt_safe_svg_bytes


def test_svg_sanitizer_removes_nonfinite_paths_and_broken_uses():
    source = b'<svg xmlns="http://www.w3.org/2000/svg"><defs><path id="bad"/></defs>\n    <path d="M 0 0 L nan 2"/><use href="#bad"/><path d="M 0 0 L 2 2"/></svg>'
    cleaned = qt_safe_svg_bytes(source)
    assert b"nan" not in cleaned
    assert b"<use" not in cleaned
    assert b"M 0 0 L 2 2" in cleaned
