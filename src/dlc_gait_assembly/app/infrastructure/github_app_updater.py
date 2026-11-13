"""Fetch GitHub updates and safely update an inactive checkout or installed distribution."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import replace
from importlib.metadata import version
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from packaging.version import InvalidVersion, Version

import dlc_gait_assembly
from dlc_gait_assembly.app.business.app_update_contracts import (
    PROJECT_URL,
    REPOSITORY,
    AppUpdateError,
    AppUpdateInfo,
)
from dlc_gait_assembly.shared.infrastructure.workspace_path_resolver import source_checkout_root

GIT_TIMEOUT = 30
INSTALL_TIMEOUT = 900


class GitHubAppUpdater:
    def __init__(self, *, checkout: Path | None = None, installed: bool = False):
        self.checkout = None if installed else (checkout or source_checkout_root())

    def check(self) -> AppUpdateInfo:
        if self.checkout is not None:
            return self._check_checkout(fetch=True)
        return self._check_release()

    def _git(self, *arguments: str, allow_failure: bool = False) -> str:
        result = self._run(["git", *arguments], cwd=self.checkout, timeout=GIT_TIMEOUT)
        if result.returncode and not allow_failure:
            raise AppUpdateError(result.stderr.strip() or result.stdout.strip() or "Git update check failed.")
        return result.stdout.strip() if result.returncode == 0 else ""

    def _is_ancestor(self, older: str, newer: str) -> bool:
        result = self._run(
            ["git", "merge-base", "--is-ancestor", older, newer], cwd=self.checkout, timeout=GIT_TIMEOUT
        )
        if result.returncode not in (0, 1):
            raise AppUpdateError(result.stderr.strip() or "Could not compare the local and downloaded versions.")
        return result.returncode == 0

    def _check_checkout(self, *, fetch: bool) -> AppUpdateInfo:
        if not (self.checkout / ".git").exists():
            raise AppUpdateError("This source folder has no Git history. Install from a Git clone to enable updates.")
        remote = self._git("remote", "get-url", "origin")
        if remote.removesuffix(".git").rstrip("/").lower() not in {
            PROJECT_URL.lower(),
            f"git@github.com:{REPOSITORY}".lower(),
            f"ssh://git@github.com/{REPOSITORY}".lower(),
        }:
            raise AppUpdateError(f"Updates require origin to point to {PROJECT_URL}.")
        current = self._git("rev-parse", "HEAD")
        local_branch = self._git("branch", "--show-current")
        tracked_remote = self._git("config", "--get", f"branch.{local_branch}.remote", allow_failure=True)
        tracked_ref = self._git("config", "--get", f"branch.{local_branch}.merge", allow_failure=True)
        branch = tracked_ref.removeprefix("refs/heads/") if tracked_remote == "origin" else "main"
        if not branch or not tracked_ref.startswith("refs/heads/"):
            branch = "main"
        blocked = ""
        if not local_branch:
            blocked = "This checkout is detached. Switch to a branch tracking origin before installing updates."
        elif tracked_remote != "origin" or tracked_ref != f"refs/heads/{branch}":
            blocked = "This branch does not track origin. Configure its upstream before installing updates."
        if fetch:
            self._git("fetch", "--no-tags", "origin", f"refs/heads/{branch}:refs/remotes/origin/{branch}")
        latest = self._git("rev-parse", f"refs/remotes/origin/{branch}")
        available = current != latest
        if available and not self._is_ancestor(current, latest):
            if self._is_ancestor(latest, current):
                available = False
                blocked = blocked or "This checkout contains local commits ahead of GitHub. They will be preserved."
            else:
                blocked = blocked or "Local and GitHub commits have diverged. Resolve them with Git before updating."
        if self._git("status", "--porcelain", "--untracked-files=all"):
            blocked = "This checkout has local code changes. Commit or move them before installing updates."
        return AppUpdateInfo(
            dlc_gait_assembly.__version__, available, current, latest, branch=branch, checkout=self.checkout,
            blocked_reason=blocked, local_branch=local_branch,
        )

    @staticmethod
    def _api(path: str):
        request = Request(
            f"https://api.github.com/repos/{REPOSITORY}/{path}",
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"DLC-Gait-Assembler/{dlc_gait_assembly.__version__}",
            },
        )
        try:
            with urlopen(request, timeout=15) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code == 404 and path == "releases/latest":
                return None
            if error.code in (403, 429):
                raise AppUpdateError("GitHub is limiting update checks. Try again later.") from error
            raise AppUpdateError(f"GitHub could not provide an update (HTTP {error.code}).") from error
        except (OSError, URLError, ValueError) as error:
            raise AppUpdateError(f"Could not contact GitHub: {error}") from error

    def _check_release(self) -> AppUpdateInfo:
        result = AppUpdateInfo(dlc_gait_assembly.__version__)
        release = self._api("releases/latest")
        if release is None:
            return replace(result, blocked_reason="No public GitHub release is available yet.")
        try:
            tag = release["tag_name"]
            if not isinstance(tag, str):
                raise TypeError("Release tags must be strings.")
            latest = Version(tag)
        except (InvalidVersion, KeyError, TypeError) as error:
            raise AppUpdateError("The latest GitHub release has an invalid version tag.") from error
        if release.get("draft") or release.get("prerelease") or latest.is_prerelease or latest.is_devrelease:
            return result
        if latest <= Version(dlc_gait_assembly.__version__):
            return result
        commit = self._api(f"commits/{quote(tag, safe='')}")
        revision = commit.get("sha", "") if isinstance(commit, dict) else ""
        if not re.fullmatch(r"[0-9a-f]{40,64}", revision):
            raise AppUpdateError("GitHub did not return a valid release commit.")
        return replace(result, available=True, latest_version=str(latest), latest_revision=revision)

    def install(self, update: AppUpdateInfo, progress) -> None:
        if not update.available or update.blocked_reason:
            raise AppUpdateError(update.blocked_reason or "There is no update to install.")
        if update.checkout != self.checkout:
            raise AppUpdateError("The installation location has changed. Check for updates again.")
        if self.checkout is not None:
            progress("Verifying local files…")
            fresh = self._check_checkout(fetch=False)
            if fresh.blocked_reason:
                raise AppUpdateError(fresh.blocked_reason)
            if (fresh.current_revision, fresh.latest_revision, fresh.branch, fresh.local_branch) != (
                update.current_revision, update.latest_revision, update.branch, update.local_branch
            ):
                raise AppUpdateError("The checkout changed after the update check. Check for updates again.")
            progress("Installing downloaded code…")
            self._git("merge", "--ff-only", "--no-autostash", "--no-overwrite-ignore", update.latest_revision)
            target = ["--editable", str(self.checkout)]
        else:
            if not re.fullmatch(r"[0-9a-f]{40,64}", update.latest_revision):
                raise AppUpdateError("The release commit is invalid. Check for updates again.")
            target = [f"dlc-gait-assembler @ {PROJECT_URL}/archive/{update.latest_revision}.zip"]
        progress("Refreshing the application and its dependencies. This may take a few minutes…")
        result = self._run(
            [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "--upgrade", *target],
            cwd=self.checkout,
            timeout=INSTALL_TIMEOUT,
        )
        if result.returncode:
            context = "The downloaded code was applied, but " if self.checkout is not None else ""
            raise AppUpdateError(
                context + "the application environment could not be refreshed. Repair the installation "
                "with pip before retrying.\n\n" + (result.stderr or result.stdout)[-4000:]
            )
        if update.latest_version and Version(version("dlc-gait-assembler")) != Version(update.latest_version):
            raise AppUpdateError("The installed package version does not match the release. Check its packaging.")

    @staticmethod
    def restart() -> None:
        try:
            subprocess.Popen([sys.executable, "-m", "dlc_gait_assembly"], start_new_session=os.name != "nt")
        except OSError as error:
            raise AppUpdateError(f"The update is installed. Please reopen the app manually: {error}") from error

    @staticmethod
    def _run(arguments, *, cwd, timeout):
        environment = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
        environment.setdefault("GIT_SSH_COMMAND", "ssh -oBatchMode=yes -oConnectTimeout=10")
        try:
            return subprocess.run(
                arguments, cwd=cwd, env=environment, text=True, capture_output=True,
                stdin=subprocess.DEVNULL, timeout=timeout, check=False,
            )
        except FileNotFoundError as error:
            raise AppUpdateError(f"{arguments[0]} is not available. Install it before updating.") from error
        except subprocess.TimeoutExpired as error:
            raise AppUpdateError("The update operation timed out. Check your connection and try again.") from error
        except OSError as error:
            raise AppUpdateError(f"The update operation failed: {error}") from error
