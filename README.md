# DLC Gait Assembler

A desktop app for preparing videos, working with DeepLabCut coordinates, and analyzing Runway and Ladder gait data.

## Install and launch

```bash
git clone https://github.com/booooorb/dlc-gait-assembler.git
cd dlc-gait-assembler
conda env create -f src/dlc_gait_assembly/resources/environments/GAIT_ASSEMBLER.yaml
conda activate gait-assembler
python -m pip install -e .
dlc-gait-assembler
```

Python 3.10 or newer is required. You can also launch with `python gait_assembler.py` or `python -m dlc_gait_assembly`.

The Conda recipe includes FFmpeg and FFprobe. DeepLabCut runs in its own environment; use the app's DeepLabCut screen to check or install it.

## Updates

The app checks GitHub about 2.5 seconds after opening and every six hours while running. When an update is available, choose **Install and restart**, **View changes**, or **Later**.

- Check manually with **Settings → Check for updates…**.
- Disable background checks with **Settings → Check for updates automatically**.
- Installation runs the app's normal close checks before applying changes.
- Local code edits and conflicting commits block installation and produce an explanation. Saved workspace data stays in place.
- Offline background checks stay quiet.

Source checkouts fetch updates from their tracked branch on `origin`. Installed packages check stable public GitHub releases. If an environment refresh fails after a source update, run `python -m pip install -e .` in the app environment, then reopen the app.

## Workflows

Runway tools follow this sequence:

| Tool | Purpose |
| --- | --- |
| Calibration | Measure scale from images or video. |
| Video processing | Crop, flip, trim, enhance, and export videos. |
| DeepLabCut | Run pose estimation and produce coordinate files or labeled videos. |
| Knee correction | Review and reconstruct knee coordinates. |
| Gait analysis | Match camera views, map markers, preview strides, and export measurements. |
| PCA / Random Forest | Compare recording summaries across animals and groups. |

Use automation profiles to reuse settings and run selected stages across videos. Review the results at each review gate. Ladder analysis provides a separate workflow for detecting and reviewing paw placements and footfall events.

Before analysis, check marker assignments, camera timing, frame rates, confidence thresholds, and calibration. Exported measurements depend on those settings. In-app reference guides describe the available measurements and methods.

## Saved data

A source checkout saves sessions under `workspace/`. Installed packages use `~/DLC-Gait-Assembler/workspace`. Set `DLC_GAIT_WORKSPACE` to choose another location. External output folders are also supported.

Workspace data, local references, and build output are ignored by Git. Updating the app does not migrate or relocate saved data. For older workspace layouts, run `dlc-gait-migrate --help`; inspect a dry-run plan before applying a migration.

## Development

```bash
python -m pip install -e ".[dev]"
QT_QPA_PLATFORM=offscreen MPLBACKEND=Agg pytest -q
ruff check src tests gait_assembler.py
python -m build --sdist --wheel --no-isolation
```

Code lives under `src/dlc_gait_assembly/`: `app` assembles the interface and dependencies, `runway` and `ladder` own their workflows, `shared` provides common controls and adapters, and `resources` contains packaged assets. Tests mirror that layout. Business code is independent of Qt and concrete I/O adapters.

To publish a package update, bump the version in both `pyproject.toml` and `src/dlc_gait_assembly/__init__.py`, then publish a matching stable GitHub release such as `v0.2.0`.

## Credits and licenses

ALMA derives from the work of Aljović, Zhao et al. ([paper](https://doi.org/10.1038/s42003-022-03077-6), [source](https://github.com/sollan/alma)) and includes its GPL-3.0 license and attribution. RustLab1 methods retain their connection to [Weber et al. (2022)](https://doi.org/10.1186/s12915-022-01434-9).

Software and font notices are packaged in `src/dlc_gait_assembly/resources/licenses/`. Additional citations and artwork credits are available in the app.
