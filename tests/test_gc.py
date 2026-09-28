import json
from datetime import timedelta

from agent_channel import agents
from agent_channel.gc import maybe_gc
from agent_channel.paths import channel_dir
from agent_channel.store import append, make_message, read
from conftest import NOW


def test_rolls_old_messages_into_monthly_archive(repo):
    ch = channel_dir(repo, create=True)
    for days, body in ((50, "august"), (20, "september"), (1, "fresh")):
        append(ch, make_message("A1", "t", "all", "INFO", body, NOW - timedelta(days=days)))
    with open(ch / "channel.jsonl", "a") as f:
        f.write("garbage line\n")
    assert maybe_gc(ch, NOW)
    assert [m["body"] for m in read(ch)] == ["fresh"]
    assert "garbage line" in (ch / "channel.jsonl").read_text()
    assert [json.loads(l)["body"] for l in (ch / "archive" / "2026-08.jsonl").read_text().splitlines()] == ["august"]
    assert [json.loads(l)["body"] for l in (ch / "archive" / "2026-09.jsonl").read_text().splitlines()] == ["september"]
    assert [m["body"] for m in read(ch, include_archive=True)] == ["august", "september", "fresh"]


def test_runs_once_per_day_unless_forced(repo):
    ch = channel_dir(repo, create=True)
    assert maybe_gc(ch, NOW)
    assert not maybe_gc(ch, NOW + timedelta(hours=1))
    assert maybe_gc(ch, NOW + timedelta(hours=1), force=True)
    assert maybe_gc(ch, NOW + timedelta(days=1))


def test_archives_agents_done_for_a_week(repo):
    ch = channel_dir(repo, create=True)
    agents.join(ch, "Old", "t", "g", "s", "/wt", "main", NOW - timedelta(days=10))
    agents.set_status(ch, "Old", "done", NOW - timedelta(days=8))
    agents.join(ch, "Recent", "t", "g", "s", "/wt", "main", NOW)
    agents.set_status(ch, "Recent", "done", NOW - timedelta(days=2))
    maybe_gc(ch, NOW)
    assert [a["name"] for a in agents.load_all(ch)] == ["Recent"]
    assert (ch / "agents" / "archive" / "Old.json").exists()
