import multiprocessing

import pytest

from agent_channel import agents
from agent_channel.errors import NameTaken, UnknownAgent, UsageError
from agent_channel.paths import channel_dir
from conftest import NOW


def _join(ch):
    return agents.join(ch, "Otter", "t", "g", "s", "/wt", "main", NOW)


def test_join_then_load(repo):
    ch = channel_dir(repo, create=True)
    _join(ch)
    a = agents.load(ch, "Otter")
    assert a["status"] == "active" and a["claims"] == [] and a["last_seen"] == "2026-09-28T10:00:00+02:00"


def test_name_rules(repo):
    ch = channel_dir(repo, create=True)
    for bad in ("x", "1abc", "a/b", "../etc", "a" * 33, "ab c"):
        with pytest.raises(UsageError):
            agents.join(ch, bad, "t", "g", "s", "/wt", "main", NOW)


def test_name_taken_including_archived(repo):
    ch = channel_dir(repo, create=True)
    _join(ch)
    with pytest.raises(NameTaken):
        _join(ch)
    (ch / "agents" / "Otter.json").rename(ch / "agents" / "archive" / "Otter.json")
    with pytest.raises(NameTaken):
        _join(ch)


def _race(path):
    from pathlib import Path
    from agent_channel import agents as ag
    from agent_channel.errors import NameTaken as NT
    from conftest import NOW as N
    try:
        ag.join(Path(path), "Otter", "t", "g", "s", "/wt", "main", N)
        return 1
    except NT:
        return 0


def test_concurrent_join_exactly_one_wins(repo):
    ch = channel_dir(repo, create=True)
    with multiprocessing.Pool(8) as pool:
        assert sum(pool.map(_race, [str(ch)] * 8)) == 1


def test_done_clears_claims(repo):
    ch = channel_dir(repo, create=True)
    _join(ch)
    agents.update(ch, "Otter", lambda a: a["claims"].append({"pattern": "x", "reason": "", "since": ""}), NOW)
    assert agents.set_status(ch, "Otter", "done", NOW)["claims"] == []


def test_unknown_agent(repo):
    ch = channel_dir(repo, create=True)
    with pytest.raises(UnknownAgent):
        agents.load(ch, "Nobody")


def test_load_all_skips_corrupt_files(repo):
    ch = channel_dir(repo, create=True)
    _join(ch)
    (ch / "agents" / "Broken.json").write_text("{nope")
    assert [a["name"] for a in agents.load_all(ch)] == ["Otter"]
