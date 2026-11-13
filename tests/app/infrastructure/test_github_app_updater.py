"""Exercise update discovery and fast-forward safety with real isolated Git repositories."""

import subprocess
import sys
from urllib.error import HTTPError

import pytest

from dlc_gait_assembly.app.business.app_update_contracts import AppUpdateError, AppUpdateInfo, PROJECT_URL
from dlc_gait_assembly.app.infrastructure.github_app_updater import GitHubAppUpdater
import dlc_gait_assembly.app.infrastructure.github_app_updater as adapter


def git(folder, *arguments):
    return subprocess.run(
        ["git", "-c", "user.name=Update test", "-c", "user.email=updates@example.invalid", *arguments],
        cwd=folder, text=True, capture_output=True, check=True,
    ).stdout.strip()


def commit(folder, name, text):
    (folder / name).write_text(text)
    git(folder, "add", name)
    git(folder, "commit", "-m", f"Update {name}")
    return git(folder, "rev-parse", "HEAD")


@pytest.fixture
def repositories(tmp_path, monkeypatch):
    origin = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    checkout = tmp_path / "checkout"
    git(tmp_path, "init", "--bare", "--initial-branch=main", str(origin))
    git(tmp_path, "clone", str(origin), str(seed))
    original = commit(seed, "app.py", "original\n")
    commit(seed, ".gitignore", "workspace/\n")
    git(seed, "push", "origin", "main")
    git(tmp_path, "clone", str(origin), str(checkout))
    git(checkout, "remote", "set-url", "origin", PROJECT_URL + ".git")
    updater = GitHubAppUpdater(checkout=checkout)
    run = updater._run
    pip_calls = []

    def isolated_run(arguments, **options):
        if arguments[:4] == ["git", "fetch", "--no-tags", "origin"]:
            arguments = [*arguments[:3], str(origin), *arguments[4:]]
        if arguments[:3] == [sys.executable, "-m", "pip"]:
            pip_calls.append(arguments)
            return subprocess.CompletedProcess(arguments, 0, "installed", "")
        return run(arguments, **options)

    monkeypatch.setattr(updater, "_run", isolated_run)
    return updater, origin, seed, checkout, pip_calls


def publish(seed):
    revision = commit(seed, "app.py", "updated\n")
    git(seed, "push", "origin", "main")
    return revision


def test_fetches_new_commit_without_changing_running_code_then_installs(repositories):
    updater, _, seed, checkout, pip_calls = repositories
    before = git(checkout, "rev-parse", "HEAD")
    latest = publish(seed)
    update = updater.check()
    assert update.available and not update.blocked_reason
    assert update.latest_revision == latest
    assert git(checkout, "rev-parse", "HEAD") == before
    assert (checkout / "app.py").read_text() == "original\n"
    messages = []
    updater.install(update, messages.append)
    assert git(checkout, "rev-parse", "HEAD") == latest
    assert (checkout / "app.py").read_text() == "updated\n"
    assert pip_calls[0][:3] == [sys.executable, "-m", "pip"]
    assert pip_calls[0][-2:] == ["--editable", str(checkout)]
    assert len(messages) == 3


@pytest.mark.parametrize("name", ["app.py", "untracked.py"])
def test_refuses_tracked_and_untracked_edits_made_after_check(repositories, name):
    updater, _, seed, checkout, pip_calls = repositories
    publish(seed)
    update = updater.check()
    (checkout / name).write_text("my work\n")
    with pytest.raises(AppUpdateError, match="local code changes"):
        updater.install(update, lambda _: None)
    assert git(checkout, "rev-parse", "HEAD") == update.current_revision
    assert (checkout / name).read_text() == "my work\n"
    assert not pip_calls


def test_blocks_dirty_checkout_but_still_fetches_updates(repositories):
    updater, _, seed, checkout, _ = repositories
    latest = publish(seed)
    (checkout / "app.py").write_text("local\n")
    update = updater.check()
    assert update.latest_revision == latest
    assert update.available
    assert "local code changes" in update.blocked_reason
    with pytest.raises(AppUpdateError, match="local code changes"):
        updater.install(update, lambda _: None)


def test_workspace_outputs_survive_update(repositories):
    updater, _, seed, checkout, _ = repositories
    workspace = checkout / "workspace"
    workspace.mkdir()
    (workspace / "results.csv").write_text("research data\n")
    publish(seed)
    update = updater.check()
    assert not update.blocked_reason
    updater.install(update, lambda _: None)
    assert (workspace / "results.csv").read_text() == "research data\n"


def test_upstream_cannot_overwrite_ignored_workspace_data(repositories):
    updater, _, seed, checkout, pip_calls = repositories
    (seed / "workspace").mkdir()
    (seed / "workspace" / "results.csv").write_text("upstream data\n")
    git(seed, "add", "--force", "workspace/results.csv")
    git(seed, "commit", "-m", "Add workspace file")
    git(seed, "push", "origin", "main")
    workspace = checkout / "workspace"
    workspace.mkdir()
    (workspace / "results.csv").write_text("research data\n")
    update = updater.check()
    with pytest.raises(AppUpdateError):
        updater.install(update, lambda _: None)
    assert (workspace / "results.csv").read_text() == "research data\n"
    assert git(checkout, "rev-parse", "HEAD") == update.current_revision
    assert not pip_calls


def test_diverging_commits_are_never_merged(repositories):
    updater, _, seed, checkout, _ = repositories
    publish(seed)
    local = commit(checkout, "local.py", "local work\n")
    update = updater.check()
    assert update.available and "diverged" in update.blocked_reason
    with pytest.raises(AppUpdateError, match="diverged"):
        updater.install(update, lambda _: None)
    assert git(checkout, "rev-parse", "HEAD") == local


def test_local_ahead_is_not_reported_as_an_update(repositories):
    updater, _, _, checkout, _ = repositories
    commit(checkout, "local.py", "local work\n")
    update = updater.check()
    assert not update.available
    assert "ahead" in update.blocked_reason


def test_unchanged_checkout_is_up_to_date(repositories):
    updater, *_ = repositories
    update = updater.check()
    assert not update.available and not update.blocked_reason


@pytest.mark.parametrize("detached", [False, True])
def test_untracked_or_detached_branch_cannot_install(repositories, detached):
    updater, _, seed, checkout, _ = repositories
    publish(seed)
    git(checkout, "checkout", "--detach" if detached else "-b", *([] if detached else ["experiment"]))
    update = updater.check()
    assert update.available and update.blocked_reason


def test_branch_changed_after_check_requires_new_check(repositories):
    updater, _, seed, checkout, _ = repositories
    publish(seed)
    update = updater.check()
    git(checkout, "checkout", "-b", "other")
    git(checkout, "branch", "--set-upstream-to=origin/main")
    with pytest.raises(AppUpdateError, match="changed after"):
        updater.install(update, lambda _: None)


def test_foreign_origin_is_rejected_before_fetch(repositories):
    updater, _, _, checkout, _ = repositories
    git(checkout, "remote", "set-url", "origin", "https://github.com/someone/another-app.git")
    with pytest.raises(AppUpdateError, match="origin to point"):
        updater.check()


def test_install_failure_reports_applied_code_and_keeps_local_data(repositories, monkeypatch):
    updater, _, seed, checkout, _ = repositories
    latest = publish(seed)
    update = updater.check()
    run = updater._run

    def failing_pip(arguments, **options):
        if "pip" in arguments:
            return subprocess.CompletedProcess(arguments, 1, "", "dependency install failed")
        return run(arguments, **options)

    monkeypatch.setattr(updater, "_run", failing_pip)
    with pytest.raises(AppUpdateError, match="downloaded code was applied"):
        updater.install(update, lambda _: None)
    assert git(checkout, "rev-parse", "HEAD") == latest


@pytest.mark.parametrize("tag", ["v0.10.0", "2.0.0"])
def test_installed_distribution_checks_release_versions_and_resolves_exact_commit(monkeypatch, tag):
    updater = GitHubAppUpdater(installed=True)
    calls = []

    def api(path):
        calls.append(path)
        return {"tag_name": tag} if path == "releases/latest" else {"sha": "a" * 40}

    monkeypatch.setattr(updater, "_api", api)
    update = updater.check()
    assert update.available
    assert update.latest_revision == "a" * 40
    assert update.latest_version == tag.removeprefix("v")
    assert calls == ["releases/latest", f"commits/{tag}"]


@pytest.mark.parametrize("release", [None, {"tag_name": "v0.1.0"}, {"tag_name": "0.2.0rc1"},
                                      {"tag_name": "0.2.0", "draft": True}])
def test_absent_older_and_unstable_releases_do_not_update(monkeypatch, release):
    updater = GitHubAppUpdater(installed=True)
    monkeypatch.setattr(updater, "_api", lambda _: release)
    assert not updater.check().available


def test_release_install_uses_pinned_archive_and_running_interpreter(monkeypatch):
    updater = GitHubAppUpdater(installed=True)
    update = AppUpdateInfo("0.1.0", available=True, latest_revision="b" * 40, latest_version="0.2.0")
    calls = []

    def run(arguments, **options):
        calls.append(arguments)
        return subprocess.CompletedProcess(arguments, 0, "installed", "")

    monkeypatch.setattr(updater, "_run", run)
    monkeypatch.setattr(adapter, "version", lambda _: "0.2.0")
    updater.install(update, lambda _: None)
    assert calls[0][:3] == [sys.executable, "-m", "pip"]
    assert calls[0][-1] == f"dlc-gait-assembler @ {PROJECT_URL}/archive/{'b' * 40}.zip"


def test_wrong_release_package_version_is_reported(monkeypatch):
    updater = GitHubAppUpdater(installed=True)
    update = AppUpdateInfo("0.1.0", available=True, latest_revision="b" * 40, latest_version="0.2.0")
    monkeypatch.setattr(updater, "_run", lambda *a, **kw: subprocess.CompletedProcess([], 0, "", ""))
    monkeypatch.setattr(adapter, "version", lambda _: "0.1.0")
    with pytest.raises(AppUpdateError, match="does not match"):
        updater.install(update, lambda _: None)


@pytest.mark.parametrize("exception, message", [
    (FileNotFoundError(), "not available"),
    (subprocess.TimeoutExpired("git", 30), "timed out"),
])
def test_missing_git_and_timeout_are_actionable(monkeypatch, exception, message):
    def run(*args, **kwargs):
        assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"
        raise exception

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(AppUpdateError, match=message):
        GitHubAppUpdater._run(["git", "fetch"], cwd=None, timeout=30)


def test_github_rate_limit_and_no_release_responses(monkeypatch):
    def limited(*args, **kwargs):
        raise HTTPError("https://api.github.com", 403, "Forbidden", {}, None)

    monkeypatch.setattr(adapter, "urlopen", limited)
    with pytest.raises(AppUpdateError, match="limiting"):
        GitHubAppUpdater._api("releases/latest")

    def missing(*args, **kwargs):
        raise HTTPError("https://api.github.com", 404, "Not found", {}, None)

    monkeypatch.setattr(adapter, "urlopen", missing)
    assert GitHubAppUpdater._api("releases/latest") is None
    with pytest.raises(AppUpdateError, match="HTTP 404"):
        GitHubAppUpdater._api("commits/v0.2.0")
