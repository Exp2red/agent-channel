from datetime import timedelta

from agent_channel.watch import dashboard
from conftest import NOW

TTL = timedelta(hours=4)
AGENTS = [{"name": "Otter", "task": "t-otter", "branch": "main", "status": "active",
           "last_seen": NOW.isoformat(), "claims": [{"pattern": "src/**", "reason": "", "since": ""}]},
          {"name": "Das", "task": "t-das", "branch": "x", "status": "done", "last_seen": NOW.isoformat(), "claims": []}]
MSGS = [{"id": str(i), "ts": (NOW + timedelta(minutes=i)).isoformat(), "from": "Otter", "to": "all",
         "kind": "GUARD" if i == 9 else ("DECISION" if i == 3 else "INFO"), "body": f"body {i}", "reply_to": None}
        for i in range(10)]


def test_layout_fits_and_marks_guard():
    for width, height in ((80, 24), (120, 40)):
        lines = dashboard(AGENTS, MSGS, NOW, TTL, width, height, repo="erppoc")
        assert len(lines) == height and all(len(l) <= width for l in lines)
        text = "\n".join(lines)
        assert "Otter" in text and "Das" not in text and "src/**" in text
        assert any(l.startswith("! ") and "body 9" in l for l in lines)


def test_offset_and_decisions_filter():
    lines = dashboard(AGENTS, MSGS, NOW, TTL, 80, 14, offset=2)
    assert "body 9" not in "\n".join(lines) and "body 7" in "\n".join(lines)
    only = "\n".join(dashboard(AGENTS, MSGS, NOW, TTL, 80, 24, only_decisions=True))
    assert "body 3" in only and "body 4" not in only
