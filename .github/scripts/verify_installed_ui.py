"""Verify that a built distribution contains and opens the current desktop interface."""

from __future__ import annotations

import argparse
import json
import os
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("MPLBACKEND", "Agg")

    with TemporaryDirectory(prefix="gait-installed-ui-") as temporary:
        os.environ["DLC_GAIT_WORKSPACE"] = str(Path(temporary) / "workspace")
        from PySide6.QtCore import QSettings
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication

        import dlc_gait_assembly
        from dlc_gait_assembly.app.app_bootstrap import apply_theme_mode, create_main_window
        from dlc_gait_assembly.app.infrastructure.app_preferences_store import AppPreferencesStore
        from dlc_gait_assembly.shared.infrastructure.packaged_resource_reader import resource_path
        from dlc_gait_assembly.shared.infrastructure.workspace_path_resolver import source_checkout_root

        installed_version = version("dlc-gait-assembler")
        assert installed_version == dlc_gait_assembly.__version__
        assert source_checkout_root() is None, "Verification must import the installed wheel, not a checkout."
        for parts in (
            ("branding", "paw-track-light.svg"),
            ("branding", "paw-track-dark.svg"),
            ("branding", "paw-track-app.svg"),
            ("icons", "paw-gait.svg"),
            ("icons", "stage-switch-on.svg"),
            ("analysis", "rustlab1", "Run_GMM_Adapted_RustLab1.R"),
            ("analysis", "rustlab1", "Run_ALMA_Side_Rust_Bottom.R"),
        ):
            assert resource_path(*parts).is_file(), parts

        app = QApplication.instance() or QApplication([])
        apply_theme_mode(app, None, "light")
        settings = QSettings(str(Path(temporary) / "preferences.ini"), QSettings.IniFormat)
        window = create_main_window(preferences=AppPreferencesStore(settings))
        window.resize(1440, 900)
        window.show()
        QTest.qWait(300)
        assert window._brand_logo_filename == "paw-track-light.svg"
        assert window.workflows.bar.isVisible()
        assert window.updates.version_action.text() == f"Version {installed_version}"
        assert window.grab().save(str(output / "windows-home.png"))

        window.workflows.new(name="Installed release verification")
        window.routes._open_tool("gait_parameter_analysis")
        QTest.qWait(400)
        page = window._active_tool.kinematics_widget
        assert page.settings_tabs.objectName() == "RunwaySettingsTabs"
        assert page.settings_tabs.tabBar().isHidden()
        assert page.settings_tabs.tabText(page.settings_tabs.indexOf(page.mapping_tab)) == "Labels"
        assert window.grab().save(str(output / "windows-gait-analysis.png"))
        assert window.workflows.save()
        assert window.close()
        app.processEvents()

        report = {"version": installed_version, "package": str(Path(dlc_gait_assembly.__file__).resolve())}
        (output / "installed-version.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report))


if __name__ == "__main__":
    main()
