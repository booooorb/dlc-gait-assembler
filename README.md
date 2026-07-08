# DLC Gait Assembler

## Setup

Create the environment, then install the application command once:

```bash
conda env create -f GAIT_ASSEMBLER.yaml
conda activate gait-assembler
python -m pip install -e .
```

After installation, the app can be launched from **any directory** as long as the
`gait-assembler` environment is active:

```bash
conda activate gait-assembler
dlc-gait-assembler
```

You do not need to navigate back to the repository before launching it. If performing
the one-time installation from another directory, provide the repository path directly:

```bash
python -m pip install -e /path/to/dlc-gait-assembler
```

## Imports

Imported runtime/configuration files live under `imports/`:

- `imports/alma/`: ALMA runtime files used by gait parameter analysis.
- `imports/DEEPLABCUT.yaml`: DeepLabCut conda environment used by the DeepLabCut install button.

## Gait-analysis outputs

After selecting coordinate CSVs, generate the required one-stride stick-plot preview in the right-hand canvas. Full gait analysis is enabled after the preview succeeds; its intermediate files are temporary.

Opening Gait Analysis now goes directly to **Runway analysis** for ALMA stride and hindlimb kinematics. Ladder-rung analysis remains in the codebase but is no longer exposed as a primary application menu.

Ladder detection writes `*_ladder_footfalls.csv`; reviewed exports use the original ALMA event columns (`time`, `depth`, `start`, `end`, `duration`, `bodypart`, and `slip or fall`).

For recordings where one camera cannot see all four paws, choose **Paired left + right cameras**. Supply one left-view CSV/video and one right-view CSV/video, select exactly the visible front and hind paw in each, and configure each camera's method, likelihood, recovery, pixel threshold, and frame rate independently. The app writes per-camera ALMA files under `left/` and `right/`, plus one `*_ladder_combined.csv` with `view` and `source file` columns.

When the input DLC CSV contains RustLab1-style left (`l-`), right (`r-`), and down-view (`d-`) markers, gait analysis also writes:

- `*_rustlab1_parameters.csv`: the 30 hindlimb parameters selected in `SOP.tex`, evaluated on ALMA's gait-cycle boundaries.
- `*_expanded_parameters.csv`: the original ALMA columns followed by those 30 RustLab1 columns.

The run log lists missing multi-view markers. The RustLab1 output can be disabled from the compact **Outputs** tab.
