from pathlib import Path

from agent_channel import agents
from agent_channel.legacy import import_legacy
from agent_channel.paths import channel_dir
from agent_channel.store import read
from conftest import NOW

FIX = Path(__file__).parent / "fixtures" / "legacy"


def test_import_messages_and_agents(repo):
    ch = channel_dir(repo, create=True)
    assert import_legacy(ch, FIX, NOW) == (3, 1)
    msgs = read(ch)
    assert [m["kind"] for m in msgs] == ["INFO", "DECISION", "QUESTION"]
    assert msgs[1]["body"] == "Eerste regel van het besluit.\nTweede regel: met ── en een dubbele punt."
    assert msgs[0]["to"] == "all" and msgs[2]["to"] == "human"
    otter = agents.load(ch, "Otter")
    assert otter["status"] == "active" and otter["session"] == "erppoc-mainmerge-c9"
    assert [c["pattern"] for c in otter["claims"]] == [
        "backend/src/modules/governance/approval.service.ts", "backend/src/modules/document/**"]
    assert otter["touches"] == ["backend/src/modules/x.ts"]


def test_import_is_idempotent(repo):
    ch = channel_dir(repo, create=True)
    import_legacy(ch, FIX, NOW)
    assert import_legacy(ch, FIX, NOW) == (0, 0)
    assert len(read(ch)) == 3
