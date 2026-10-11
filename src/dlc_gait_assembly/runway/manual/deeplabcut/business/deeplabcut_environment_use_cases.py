"""Resolve supported environment actions and coordinate terminal sessions without Qt."""

DEEPLABCUT_LAUNCH_COMMAND = "activate-dlc"
DEEPLABCUT_INSTALL_COMMAND = "install-dlc"
DEEPLABCUT_CHECK_COMMAND = "check-dlc"


class DeepLabCutEnvironmentUseCases:
    def __init__(self, environment):
        self.environment = environment

    def prepare_command(self, command, cwd):
        return self.environment.prepare(command, cwd)

    def change_directory(self, command, cwd):
        return self.environment.change_directory(command, cwd)

    def organize_outputs(self):
        return self.environment.organize_outputs()

    def new_session(self):
        return self.environment.session()

    def command_completed(self, command, result):
        if result.returncode == 0 and command == DEEPLABCUT_LAUNCH_COMMAND:
            return self.organize_outputs()
        return None
