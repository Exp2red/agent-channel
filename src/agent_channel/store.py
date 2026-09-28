import fcntl
import json
import os
import secrets
from contextlib import contextmanager
from datetime import timezone

from .clock import iso, parse_ts
from .errors import UsageError

KINDS = ("INFO", "QUESTION", "ANSWER", "CLAIM", "RELEASE", "BLOCKED", "DECISION", "DONE", "GUARD")
MAX_BODY = 4000


@contextmanager
def locked(ch):
    """Exclusive lock for every write in the channel. Not re-entrant: never nest."""
    fd = os.open(ch / ".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def new_id(now) -> str:
    return now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(2)


def make_message(frm, task, to, kind, body, now, reply_to=None) -> dict:
    kind = kind.upper()
    if kind not in KINDS:
        raise UsageError(f"unknown kind {kind!r}; use one of: {' '.join(KINDS)}")
    if not body.strip():
        raise UsageError("empty message")
    if len(body) > MAX_BODY:
        raise UsageError(f"message is {len(body)} characters; the limit is {MAX_BODY}")
    return {"id": new_id(now), "ts": iso(now), "from": frm, "task": task, "to": to,
            "kind": kind, "body": body, "reply_to": reply_to}


def append_unlocked(path, msg) -> None:
    line = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
    fd = os.open(path, os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        size = os.fstat(fd).st_size
        if size and os.pread(fd, 1, size - 1) != b"\n":
            line = b"\n" + line  # a torn last line (crash, hand edit) must not swallow this message
        os.write(fd, line)  # one write per message: readers never see half a line from us
    finally:
        os.close(fd)


def append(ch, msg) -> dict:
    with locked(ch):
        append_unlocked(ch / "channel.jsonl", msg)
    return msg


def iter_file(path):
    if not path.exists():
        return
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if not (isinstance(obj, dict) and isinstance(obj.get("id"), str) and isinstance(obj.get("body"), str)):
                continue
            try:
                parse_ts(obj["ts"])
            except (KeyError, TypeError, ValueError):
                continue
            yield obj


def read(ch, include_archive: bool = False) -> list:
    msgs = []
    if include_archive:
        for p in sorted((ch / "archive").glob("*.jsonl")):
            msgs.extend(iter_file(p))
    msgs.extend(iter_file(ch / "channel.jsonl"))
    return msgs


def archive_messages_unlocked(ch, cutoff) -> int:
    """Move messages older than cutoff to archive/YYYY-MM.jsonl. Caller holds the lock.

    Unreadable lines stay in channel.jsonl: nothing is ever dropped. A crash between
    the archive append and the rewrite can duplicate a message, never lose one.
    """
    src = ch / "channel.jsonl"
    if not src.exists():
        return 0
    with open(src, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    keep, moved = [], 0
    for raw in lines:
        try:
            msg = json.loads(raw)
            ts = parse_ts(msg["ts"])
        except (ValueError, KeyError, TypeError):
            keep.append(raw)
            continue
        if ts < cutoff:
            append_unlocked(ch / "archive" / f"{ts.strftime('%Y-%m')}.jsonl", msg)
            moved += 1
        else:
            keep.append(raw)
    tmp = src.with_name(".channel.jsonl.tmp")
    tmp.write_text("".join(keep), encoding="utf-8")
    os.replace(tmp, src)
    return moved
