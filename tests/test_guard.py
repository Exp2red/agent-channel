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


def test_install_respects_hooks_path(repo):
    run_git(repo, "config", "core.hooksPath", "githooks")
    path = guard.install(repo, ["/x/agent-channel"])
    assert path.resolve() == (repo / "githooks" / "pre-commit").resolve()
