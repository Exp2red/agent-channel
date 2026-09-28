import os

from agent_channel import guard
from conftest import NOW, run_git

FAKE = {"AGENT_CHANNEL_FAKE_NOW": NOW.isoformat()}


def _prepare(repo, cli):
    assert cli(repo, "install-guard").returncode == 0
    cli(repo, "join", "Otter", "--task", "t", "--goal", "g", "--session", "s-otter", env=FAKE)
    cli(repo, "claim", "Otter", "src/", env=FAKE)
    (repo / "src").mkdir(exist_ok=True)
    (repo / "src" / "a file ü.py").write_text("x\n")
    run_git(repo, "add", ".")


def _commit(repo, env):
    import subprocess
    e = dict(os.environ)
    e.update(env)
    return subprocess.run(["git", "commit", "-qm", "c"], cwd=repo, capture_output=True, text=True, env=e)


def test_blocks_other_agents_claim(repo, cli):
    _prepare(repo, cli)
    r = _commit(repo, {**FAKE, "AGENT_CHANNEL_AS": "Reiger"})
    assert r.returncode != 0
    assert "a file ü.py" in r.stderr and "Otter" in r.stderr and "s-otter" in r.stderr
    assert "BLOCKED" in cli(repo, "read", "--kind", "GUARD").stdout


def test_owner_passes(repo, cli):
    _prepare(repo, cli)
    assert _commit(repo, {**FAKE, "AGENT_CHANNEL_AS": "Otter"}).returncode == 0


def test_override_passes_and_is_recorded(repo, cli):
    _prepare(repo, cli)
    assert _commit(repo, {**FAKE, "AGENT_CHANNEL_OVERRIDE": "hotfix agreed with Otter"}).returncode == 0
    out = cli(repo, "read", "--kind", "GUARD").stdout
    assert "OVERRIDE by unknown" in out and "hotfix agreed with Otter" in out


def test_expired_claim_passes(repo, cli):
    _prepare(repo, cli)
    later = (NOW.replace(hour=15)).isoformat()
    assert _commit(repo, {"AGENT_CHANNEL_FAKE_NOW": later}).returncode == 0


def test_no_channel_passes(repo, cli):
    assert cli(repo, "install-guard").returncode == 0
    (repo / "b.txt").write_text("x")
    run_git(repo, "add", ".")
    assert _commit(repo, {}).returncode == 0


def test_rename_checks_both_sides(repo, cli):
    (repo / "src").mkdir()
    (repo / "src" / "old.py").write_text("x\n" * 20)
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-qm", "base")
    _prepare(repo, cli)
    run_git(repo, "mv", "src/old.py", "moved.py")
    assert "src/old.py" in guard.staged_paths(repo) and "moved.py" in guard.staged_paths(repo)


def test_newline_in_filename(repo):
    (repo / "we\nird.txt").write_text("x")
    run_git(repo, "add", ".")
    assert "we\nird.txt" in guard.staged_paths(repo)


def test_internal_error_fails_open(repo, cli, monkeypatch, capsys):
    _prepare(repo, cli)
    monkeypatch.setattr(guard, "_pre_commit", lambda *a: 1 / 0)
    assert guard.pre_commit(repo, {}, NOW) == 0
    assert "internal error" in capsys.readouterr().err


def test_install_is_idempotent_and_keeps_existing_hook(repo):
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\necho existing\n")
    guard.install(repo, ["/x/agent-channel"])
    guard.install(repo, ["/x/agent-channel"])
    text = hook.read_text()
    assert text.count(guard.START) == 1 and "echo existing" in text and text.startswith("#!/bin/sh\n" + guard.START)
    assert os.access(hook, os.X_OK)


def test_install_respects_absolute_hooks_path(repo, tmp_path):
    hooks = tmp_path / "shared-hooks"
    run_git(repo, "config", "core.hooksPath", str(hooks))
    path = guard.install(repo, ["/x/agent-channel"])
    assert path.resolve() == (hooks / "pre-commit").resolve()


# --- final review fixes ---

def test_missing_guard_command_fails_open(repo, tmp_path):
    guard.install(repo, [str(tmp_path / "gone" / "agent-channel")])
    (repo / "c.txt").write_text("x")
    run_git(repo, "add", ".")
    assert _commit(repo, {}).returncode == 0


def test_interpreter_without_package_fails_open(repo):
    import sys
    guard.install(repo, [sys.executable, "-m", "no_such_module_here"])
    (repo / "c.txt").write_text("x")
    run_git(repo, "add", ".")
    assert _commit(repo, {}).returncode == 0


def test_refuses_non_shell_hook(repo):
    import pytest
    from agent_channel.errors import UsageError
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/usr/bin/env python3\nprint('hi')\n")
    with pytest.raises(UsageError):
        guard.install(repo, ["/x/agent-channel"])
    assert hook.read_text() == "#!/usr/bin/env python3\nprint('hi')\n"


def test_refuses_relative_hooks_path(repo):
    import pytest
    from agent_channel.errors import UsageError
    run_git(repo, "config", "core.hooksPath", ".githooks")
    with pytest.raises(UsageError):
        guard.install(repo, ["/x/agent-channel"])


def test_start_marker_without_end_is_refused(repo):
    import pytest
    from agent_channel.errors import UsageError
    hook = repo / ".git" / "hooks" / "pre-commit"
    original = f"#!/bin/sh\n{guard.START}\nsomething\necho keep me\n"
    hook.write_text(original)
    with pytest.raises(UsageError):
        guard.install(repo, ["/x/agent-channel"])
    assert hook.read_text() == original


def test_refresh_failure_does_not_let_a_conflict_through(repo, cli, monkeypatch):
    _prepare(repo, cli)
    monkeypatch.setattr(guard.agents, "seen", lambda *a: 1 / 0)
    assert guard.pre_commit(repo, {"AGENT_CHANNEL_AS": "Reiger"}, NOW) == guard.BLOCKED


def test_double_star_matches_newline_names():
    from agent_channel.claims import matches
    assert matches("src/**", "src/new\nline.py")


def test_refuses_hooks_path_inside_another_worktree(repo, worktree):
    import pytest
    from agent_channel.errors import UsageError
    run_git(repo, "config", "core.hooksPath", str(repo / "scripts" / "git-hooks"))
    with pytest.raises(UsageError):
        guard.install(worktree, ["/x/agent-channel"])  # absolute, outside *this* worktree, inside the main one
    assert not (repo / "scripts" / "git-hooks" / "pre-commit").exists()
