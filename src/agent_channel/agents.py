import json
import os
import re

from .clock import iso, parse_ts
from .errors import ChannelError, NameTaken, UnknownAgent, UsageError
from .store import locked

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{1,31}$")
STATUSES = ("active", "waiting", "done")


def check_name(name: str) -> None:
    if not NAME_RE.match(name or ""):
        raise UsageError(f"invalid agent name {name!r}: 2-32 letters, digits, '-' or '_', starting with a letter")


def path_for(ch, name):
    check_name(name)
    return ch / "agents" / f"{name}.json"


def _dump(agent) -> str:
    return json.dumps(agent, ensure_ascii=False, indent=2) + "\n"


def _write(path, agent) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(_dump(agent), encoding="utf-8")
    os.replace(tmp, path)  # readers see the old file or the new one, never half


def join(ch, name, task, goal, session, worktree, branch, now) -> dict:
    path = path_for(ch, name)
    agent = {"name": name, "task": task, "goal": goal, "session": session,
             "worktree": str(worktree), "branch": branch, "status": "active",
             "started": iso(now), "last_seen": iso(now), "claims": [], "touches": []}
    with locked(ch):
        if (ch / "agents" / "archive" / path.name).exists():
            raise NameTaken(f"the name {name!r} was used before in this channel; pick another")
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            raise NameTaken(f"the name {name!r} is taken; pick another") from None
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(_dump(agent))
    return agent


def load(ch, name) -> dict:
    path = path_for(ch, name)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise UnknownAgent(f"no agent {name!r} in this channel; start with: agent-channel join {name} --task <slug> --goal \"...\"") from None
    except ValueError:
        raise ChannelError(f"agent file {path} is not valid JSON") from None


def load_all(ch, include_done: bool = True) -> list:
    out = []
    for p in sorted((ch / "agents").glob("*.json")):
        try:
            a = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(a, dict) and a.get("name") and (include_done or a.get("status") != "done"):
            out.append(a)
    return out


def update_unlocked(ch, name, fn, now) -> dict:
    agent = load(ch, name)
    fn(agent)
    agent["last_seen"] = iso(now)
    _write(path_for(ch, name), agent)
    return agent


def update(ch, name, fn, now) -> dict:
    with locked(ch):
        return update_unlocked(ch, name, fn, now)


def seen(ch, name, now) -> dict:
    return update(ch, name, lambda a: None, now)


def set_status(ch, name, status, now) -> dict:
    if status not in STATUSES:
        raise UsageError(f"unknown status {status!r}; use one of: {' '.join(STATUSES)}")

    def fn(a):
        a["status"] = status
        if status == "done":
            a["claims"] = []

    return update(ch, name, fn, now)


def archive_done_unlocked(ch, cutoff) -> int:
    moved = 0
    for a in load_all(ch):
        if a.get("status") == "done" and parse_ts(a["last_seen"]) < cutoff:
            src = path_for(ch, a["name"])
            os.replace(src, ch / "agents" / "archive" / src.name)
            moved += 1
    return moved
