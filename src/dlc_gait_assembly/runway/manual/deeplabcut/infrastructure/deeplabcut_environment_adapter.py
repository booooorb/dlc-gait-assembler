"""Build platform commands, resolve terminal directories, and manage manual DLC artifacts."""

import shlex
import sys
from pathlib import Path

from dlc_gait_assembly.runway.manual.deeplabcut.business.deeplabcut_environment_use_cases import (
    DEEPLABCUT_CHECK_COMMAND,
    DEEPLABCUT_INSTALL_COMMAND,
    DEEPLABCUT_LAUNCH_COMMAND,
)
from dlc_gait_assembly.runway.manual.deeplabcut.infrastructure.deeplabcut_conda_commands import (
    deeplabcut_environment_file,
    deeplabcut_install_command,
    deeplabcut_install_display_command,
    deeplabcut_launch_command,
    deeplabcut_launch_display_command,
    deeplabcut_probe_command,
)
from dlc_gait_assembly.runway.manual.deeplabcut.infrastructure.deeplabcut_output_organizer import (
    organize_manual_deeplabcut_outputs,
)
from dlc_gait_assembly.shared.business.external_command_contracts import ExternalCommand
from dlc_gait_assembly.shared.infrastructure.external_process_runner import ExternalProcessSession
from dlc_gait_assembly.shared.infrastructure.workspace_path_resolver import manual_pipeline_output_folders


class DeepLabCutEnvironmentAdapter:
    def __init__(self):
        self.folders = manual_pipeline_output_folders()
        self.recipe = deeplabcut_environment_file(None)
        self.installable = self.recipe.is_file()
        self.cwd = self.folders.root

    def prepare(self, command, cwd):
        if command == DEEPLABCUT_LAUNCH_COMMAND:
            display, shell = deeplabcut_launch_display_command(), deeplabcut_launch_command()
        elif command == DEEPLABCUT_INSTALL_COMMAND:
            if not self.installable:
                raise FileNotFoundError(f"DeepLabCut environment file was not found at {self.recipe}.")
            display, shell = deeplabcut_install_display_command(self.recipe), deeplabcut_install_command(self.recipe)
        elif command == DEEPLABCUT_CHECK_COMMAND:
            display, shell = (
                "conda run -n DEEPLABCUT --no-capture-output python -c 'import deeplabcut'",
                deeplabcut_probe_command(),
            )
        else:
            display, shell = command, command
        arguments = (
            ("cmd.exe", "/d", "/s", "/c", shell) if sys.platform.startswith("win") else ("/bin/zsh", "-lc", shell)
        )
        return display, ExternalCommand(arguments, cwd)

    def change_directory(self, command, cwd):
        parts = shlex.split(command)
        if len(parts) > 2:
            raise ValueError("cd: expected one directory")
        target = Path.home() if len(parts) == 1 else Path(parts[1]).expanduser()
        target = (cwd / target).resolve() if not target.is_absolute() else target.resolve()
        if not target.is_dir():
            raise FileNotFoundError(f"cd: no such directory: {target}")
        return target

    def organize_outputs(self):
        return organize_manual_deeplabcut_outputs(self.folders)

    def session(self):
        return ExternalProcessSession()
