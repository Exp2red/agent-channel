import json
from datetime import timedelta

from agent_channel import agents
from agent_channel.hook import BUDGET, session_start
from agent_channel.paths import channel_dir
from agent_channel.store import append, make_message
from conftest import NOW


def _stdin(cwd):
    return json.dumps({"cwd": str(cwd), "hook_event_name": "SessionStart"})


def test_silent_without_channel(repo):
    assert session_start(_stdin(repo), ["/x/agent-channel"], NOW) == ""


def test_silent_outside_git(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # "not json" falls back to the cwd, which is not a repository
    assert session_start(_stdin(tmp_path), ["/x/agent-channel"], NOW) == ""
    assert session_start("not json", ["/x/agent-channel"], NOW) == ""


def test_budget_holds_with_many_agents_and_messages(repo):
    ch = channel_dir(repo, create=True)
    for i in range(30):
        agents.join(ch, f"Agent{i:02d}", "2026-09-28-" + "long-task-name-" * 3, "g", "s", "/wt", "main", NOW)
    for i in range(500):
        kind = "DECISION" if i % 50 == 0 else "INFO"
        append(ch, make_message("Agent00", "t", "all", kind, f"message {i} " + "x" * 300, NOW - timedelta(minutes=500 - i)))
    out = session_start(_stdin(repo), ["/x/agent-channel"], NOW)
    assert len(out.encode()) <= BUDGET
    assert "/x/agent-channel" in out and "+22 more" in out and "Decisions" in out
    assert out.rstrip().endswith("read -n 30, decisions")


def test_cli_hook_always_exits_zero(tmp_path, cli):
    r = cli(tmp_path, "hook", "session-start", input="{}")
    assert r.returncode == 0 and r.stdout == ""
