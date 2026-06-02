# Test Layout

- `unit/`: fast tests for pure domain logic and service helpers.
- `integration/`: tests that exercise external tools or media processing, such as ffmpeg/OpenCV video checks.
- `fixtures/alma/`: DLC coordinate CSVs and expected ALMA output CSVs.
- `fixtures/video/`: source media used by video-processing integration tests.

Shared fixture paths live in `conftest.py`.
