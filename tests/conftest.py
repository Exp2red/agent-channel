import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
NOW = datetime(2026, 9, 28, 10, 0, tzinfo=timezone(timedelta(hours=2)))


def run_git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))  # no global git config, no global hooksPath
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for key in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(key, "test")
    for key in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(key, "test@example.com")
    monkeypatch.setenv("PYTHONPATH", str(SRC) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    for key in ("AGENT_CHANNEL_AS", "AGENT_CHANNEL_OVERRIDE", "AGENT_CHANNEL_FAKE_NOW", "AGENT_CHANNEL_SELF"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    run_git(r, "init", "-q", "-b", "main")
    (r / "README.md").write_text("x\n")
    run_git(r, "add", ".")
    run_git(r, "commit", "-qm", "init")
    return r


@pytest.fixture
def worktree(repo, tmp_path):
    wt = tmp_path / "wt"
    run_git(repo, "worktree", "add", "-q", "-b", "feature", str(wt))
    return wt


@pytest.fixture
def cli():
    def _run(cwd, *args, input=None, env=None):
        full_env = dict(os.environ)
        full_env.update(env or {})
        return subprocess.run(
            [sys.executable, "-m", "agent_channel", *args],
            cwd=cwd, input=input, capture_output=True, text=True, env=full_env,
        )
    return _run
