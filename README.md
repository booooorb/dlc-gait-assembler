# DLC Gait Assembler

A desktop app for preparing videos, working with DeepLabCut coordinates, and analyzing Runway and Ladder gait data.

## Install and launch

**Git is optional.** Start with the ZIP instructions below if you are new to this. You do not need to install Python separately: Conda will install the required Python version and tools for you. An internet connection is needed during installation.

### 1. Install Conda once

Download [Miniforge](https://github.com/conda-forge/miniforge#requirements-and-installers), a small installer that provides Conda. If you already use Conda, you can use your existing installation.

- **Windows:** choose the `.exe` installer for your computer, run it, and keep the default options, including Start menu shortcuts. After installation, open **Start → Miniforge Prompt**. Use this prompt for all commands below.
- **macOS:** choose the `.pkg` installer for **Apple Silicon** or **Intel**; **Apple menu → About This Mac** identifies your chip. Run the installer and enable its Conda initialization option. Then open **Terminal** using Spotlight: press **Command + Space**, type `Terminal`, and press Enter.
- **Linux:** download the matching `.sh` installer. In Terminal, type `bash ` with a space, drag the downloaded file into the window, and press Enter. Follow the prompts and choose `yes` when asked to initialize Conda. Close and reopen Terminal afterward.

In that prompt or terminal, run:

```bash
conda --version
```

You should see `conda` followed by a version number. If the command is not found, see [installation help](#installation-help) below.

### 2. Download the app without Git

1. [Download the app ZIP](https://github.com/booooorb/dlc-gait-assembler/archive/refs/heads/main.zip). You can also use the green **Code → Download ZIP** button on this repository.
2. Extract it: on Windows, right-click the ZIP and choose **Extract All**; on macOS, double-click it; on Linux, use your archive manager's **Extract** action.
3. Move the extracted `dlc-gait-assembler-main` folder into your **Documents** folder. Open it and check that it contains `pyproject.toml` and a `src` folder. Do not run commands inside the ZIP itself.
4. In the prompt from step 1, go into that folder using the command for your system.

**Windows (Miniforge Prompt):**

```bat
cd /d "%USERPROFILE%\Documents\dlc-gait-assembler-main"
```

**macOS or Linux (Terminal):**

```bash
cd "$HOME/Documents/dlc-gait-assembler-main"
```

If your Documents folder is elsewhere, such as OneDrive, use the extracted folder's actual path instead. On Windows, copy it from File Explorer's address bar and use `cd /d "your full folder path"`; on macOS/Linux, use `cd "your full folder path"`.

### 3. Install the app

Run these commands **one at a time**, waiting for each to finish. If asked `Proceed ([y]/n)?`, type `y` and press Enter. Downloads and the environment setup can take several minutes.

```bash
conda env create -f src/dlc_gait_assembly/resources/environments/GAIT_ASSEMBLER.yaml
conda activate gait-assembler
python -m pip install .
```

These commands install Python 3.11, FFmpeg, FFprobe, and the app's dependencies in a separate environment named `gait-assembler`.

### 4. Open the app now and next time

After installation, run:

```bash
dlc-gait-assembler
```

The application window should open. Keep the prompt open while you use the app.

**To open the app again later**, open Miniforge Prompt on Windows or Terminal on macOS/Linux, then run:

```bash
conda activate gait-assembler
dlc-gait-assembler
```

You do not need to download the ZIP or repeat the installation each time. DeepLabCut is a separate, optional installation: use the app's **DeepLabCut** screen to check or install it when you need pose estimation.

<details>
<summary>Optional: install with Git instead (for updates from main)</summary>

Choose this route if you want the app to fetch updates from the latest `main` branch, rather than waiting for a published release. Complete **step 1** above first. Conda can install Git for you; no separate Git installer or GitHub account is needed for this public repository.

Open the prompt from step 1 and run:

```bash
conda activate base
conda install -c conda-forge git
```

Go to your Documents folder, using the appropriate command:

**Windows:**

```bat
cd /d "%USERPROFILE%\Documents"
```

**macOS or Linux:**

```bash
cd "$HOME/Documents"
```

Then run the following commands one at a time. If you already completed the ZIP installation, **skip the `conda env create` line** and reuse your existing `gait-assembler` environment.

```bash
git clone https://github.com/booooorb/dlc-gait-assembler.git
cd dlc-gait-assembler
conda env create -f src/dlc_gait_assembly/resources/environments/GAIT_ASSEMBLER.yaml
conda activate gait-assembler
conda install -c conda-forge git
python -m pip install -e .
dlc-gait-assembler
```

Git is also installed inside the app environment so the in-app updater can use it. Keep the cloned folder in place. Reopen the app with the two commands in step 4.

</details>

### Installation help

- **`conda` is not found:** on Windows, open **Miniforge Prompt**, rather than an ordinary Command Prompt or PowerShell window. On macOS/Linux, reopen Terminal after enabling Conda initialization; see [Miniforge's installation instructions](https://github.com/conda-forge/miniforge#install) if needed.
- **The YAML file or `pyproject.toml` cannot be found:** your prompt is in the wrong folder. Repeat the `cd` command in step 2 and check that you extracted the ZIP completely. Some extractors create an extra outer folder; use the inner folder containing `pyproject.toml`.
- **The environment already exists:** skip `conda env create`, run `conda activate gait-assembler`, and continue with the relevant `python -m pip install` command.
- **`dlc-gait-assembler` is not found:** activate `gait-assembler` first. You can also launch with `python -m dlc_gait_assembly`. If that says the module is missing, repeat the app installation in step 3.

### Upgrade an existing Windows ZIP installation

Close the app and open **Miniforge Prompt**. Run these commands one at a time to install the complete current version directly from GitHub; Git is not required:

```bat
conda activate gait-assembler
python -m pip install --upgrade --no-cache-dir "dlc-gait-assembler @ https://github.com/booooorb/dlc-gait-assembler/archive/refs/heads/main.zip"
python -c "import dlc_gait_assembly as app; print(app.__version__); print(app.__file__)"
python -m dlc_gait_assembly
```

The version check should print **0.2.0** or newer. Launching with `python -m dlc_gait_assembly` uses the package installed in this environment. Saved workspace files stay in place.

## Updates

The app checks GitHub about 2.5 seconds after opening and every six hours while running. When an update is available, choose **Install and restart**, **View changes**, or **Later**.

- Check manually with **Settings → Check for updates…**.
- Disable background checks with **Settings → Check for updates automatically**.
- Installation runs the app's normal close checks before applying changes.
- Local code edits and conflicting commits block installation and produce an explanation. Saved workspace data stays in place.
- Offline background checks stay quiet.

**Git installs** fetch updates from their tracked branch on `origin`. If an environment refresh fails after a Git update, activate `gait-assembler`, go into the cloned folder, run `python -m pip install -e .`, and reopen the app.

**ZIP installs** check stable public GitHub releases. Changes pushed only to `main` are not release updates. To get those changes without Git, close the app, download a fresh ZIP, extract it, enter its folder, activate `gait-assembler`, and run `python -m pip install --upgrade .`. Then reopen the app. Your installed app's saved data stays in its separate workspace folder; do not delete that folder. Use a regular install (`pip install .`), rather than `-e`, for the ZIP route.

The Windows release workflow builds the complete package, opens the installed Paw Track interface, and checks application behavior before publishing a new version. The release must be published before an older ZIP installation can detect it. You can request a check immediately through **Settings → Check for updates…**; scheduled background checks run every six hours.

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
