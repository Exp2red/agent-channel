from datetime import timedelta

from agent_channel import render
from conftest import NOW

TTL = timedelta(hours=4)
AGENT = {"name": "Otter", "task": "2026-09-28-x", "branch": "main", "status": "active",
         "last_seen": "2026-09-28T10:00:00+02:00",
         "claims": [{"pattern": "src/a.py", "reason": "", "since": ""}]}
MSG = {"id": "i", "ts": "2026-09-28T10:13:12+02:00", "from": "Otter", "to": "all",
       "kind": "DECISION", "body": "line one\n  line   two", "reply_to": None}


def test_delta():
    assert render.delta(timedelta(minutes=47)) == "47m"
    assert render.delta(timedelta(hours=3, minutes=5)) == "3h05"
    assert render.delta(timedelta(minutes=-1)) == "expired"


def test_agent_state():
    assert render.agent_state(AGENT, NOW, TTL) == "active"
    assert render.agent_state(AGENT, NOW + timedelta(hours=3), TTL) == "quiet"
    assert render.agent_state(AGENT, NOW + timedelta(hours=5), TTL) == "expired"
    assert render.agent_state({**AGENT, "status": "done"}, NOW, TTL) == "done"


def test_agent_line_and_claims():
    line = render.agent_line(AGENT, NOW + timedelta(minutes=13), TTL)
    assert line.startswith("Otter") and "active" in line and "1 claim" in line and "3h47" in line
    assert render.claim_lines([AGENT], NOW, TTL) == ["Otter  src/a.py  4h00"]


def test_one_line_collapses_and_truncates():
    assert render.one_line(MSG, 200) == "2026-09-28 10:13 Otter → all DECISION  line one line two"
    assert len(render.one_line(MSG, 30)) == 30 and render.one_line(MSG, 30).endswith("…")


def test_full_keeps_newlines():
    assert render.full(MSG).splitlines()[1:] == ["line one", "  line   two"]
