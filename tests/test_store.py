import json
import multiprocessing

import pytest

from agent_channel.errors import UsageError
from agent_channel.paths import channel_dir
from agent_channel.store import MAX_BODY, append, make_message, read
from conftest import NOW


def test_append_and_read_roundtrip(repo):
    ch = channel_dir(repo, create=True)
    body = "line one\nline two with ── and : and \"quotes\" and ünïcode"
    append(ch, make_message("Otter", "t", "all", "info", body, NOW))
    [msg] = read(ch)
    assert msg["body"] == body and msg["kind"] == "INFO" and msg["from"] == "Otter"
    assert msg["ts"] == "2026-09-28T10:00:00+02:00"


def test_rejects_unknown_kind_and_oversized_and_empty_body():
    with pytest.raises(UsageError):
        make_message("Otter", "t", "all", "GOSSIP", "x", NOW)
    with pytest.raises(UsageError):
        make_message("Otter", "t", "all", "INFO", "x" * (MAX_BODY + 1), NOW)
    with pytest.raises(UsageError):
        make_message("Otter", "t", "all", "INFO", "   ", NOW)


def test_corrupt_lines_are_skipped(repo):
    ch = channel_dir(repo, create=True)
    append(ch, make_message("A1", "t", "all", "INFO", "first", NOW))
    with open(ch / "channel.jsonl", "a") as f:
        f.write('{"half": \n')
        f.write("not json at all\n")
    append(ch, make_message("A1", "t", "all", "INFO", "second", NOW))
    assert [m["body"] for m in read(ch)] == ["first", "second"]


def _writer(args):
    path, i = args
    from pathlib import Path
    from agent_channel.store import append as ap, make_message as mk
    from conftest import NOW as N
    ap(Path(path), mk(f"W{i:02d}", "t", "all", "INFO", f"message {i} " + "x" * 3000, N))


def test_concurrent_appends_never_interleave(repo):
    ch = channel_dir(repo, create=True)
    with multiprocessing.Pool(20) as pool:
        pool.map(_writer, [(str(ch), i) for i in range(20)])
    lines = (ch / "channel.jsonl").read_text().splitlines()
    assert len(lines) == 20
    assert all(json.loads(line)["body"].startswith("message ") for line in lines)


def test_torn_last_line_does_not_swallow_the_next_message(repo):
    ch = channel_dir(repo, create=True)
    with open(ch / "channel.jsonl", "w") as f:
        f.write('{"id":"x","ts":"2026-09-28T1')
    append(ch, make_message("A1", "t", "all", "INFO", "after the torn line", NOW))
    assert [m["body"] for m in read(ch)] == ["after the torn line"]


def test_messages_with_bad_ts_or_id_are_skipped(repo):
    ch = channel_dir(repo, create=True)
    with open(ch / "channel.jsonl", "w") as f:
        f.write(json.dumps({"id": "a", "ts": "yesterday", "body": "bad ts", "kind": "DECISION"}) + "\n")
        f.write(json.dumps({"ts": "2026-09-28T10:00:00+02:00", "body": "no id"}) + "\n")
        f.write(json.dumps({"id": "z", "ts": "2026-09-28T08:00:00Z", "body": "zulu"}) + "\n")
    assert [m["body"] for m in read(ch)] == ["zulu"]
