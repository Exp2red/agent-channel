import os
import re
from datetime import timedelta

from . import agents as agents_mod
from .clock import iso, parse_ts
from .errors import ClaimConflict, NotARepo, UsageError
from .paths import git
from .store import locked

DEFAULT_TTL = timedelta(hours=4)
QUIET_AFTER = timedelta(hours=2)
WILDCARDS = "*?"


def normalize(pattern: str, root=None) -> str:
    """Repository-relative, forward slashes, no '..'. A trailing '/' means the whole directory."""
    p = (pattern or "").strip()
    if root is not None and os.path.isabs(p):
        try:
            p = os.path.relpath(os.path.realpath(p), os.path.realpath(root))
        except ValueError:
            raise UsageError(f"{pattern!r} is outside the repository") from None
    p = p.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    if not p or p.startswith("/") or ".." in p.split("/"):
        raise UsageError(f"invalid path or pattern {pattern!r}: use a path relative to the repository root")
    if p.endswith("/"):
        p += "**"
    return p


def _regex(pattern: str):
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def matches(pattern: str, path: str) -> bool:
    return bool(_regex(pattern).match(path))


def _literal_prefix(p: str) -> str:
    idx = min([p.find(c) for c in WILDCARDS if c in p], default=len(p))
    return p[:idx]


def overlap(a: str, b: str) -> bool:
    """Could one path fall under both patterns? Conservative when both contain wildcards."""
    la, lb = _literal_prefix(a), _literal_prefix(b)
    if la == a and lb == b:
        return a == b
    if la == a:
        return matches(b, a)
    if lb == b:
        return matches(a, b)
    return la.startswith(lb) or lb.startswith(la)


def parse_duration(s: str) -> timedelta:
    m = re.fullmatch(r"\s*(\d+)\s*([smhd])\s*", s or "")
    if not m:
        raise UsageError(f"invalid duration {s!r}: use e.g. 30m, 4h or 1d")
    unit = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}[m.group(2)]
    return timedelta(**{unit: int(m.group(1))})


def ttl_for(cwd) -> timedelta:
    try:
        value = git(cwd, "config", "--get", "agent-channel.ttl")
    except NotARepo:  # unset config also exits non-zero
        return DEFAULT_TTL
    return parse_duration(value) if value else DEFAULT_TTL


def expires(agent, ttl):
    return parse_ts(agent["last_seen"]) + ttl


def is_live(agent, now, ttl) -> bool:
    return agent.get("status") != "done" and now < expires(agent, ttl)


def live_claims(agents, now, ttl, exclude=None):
    for a in agents:
        if a.get("name") == exclude or not is_live(a, now, ttl):
            continue
        for c in a.get("claims", []):
            yield a, c


def holders(agents, path, now, ttl, exclude=None) -> list:
    return [(a, c) for a, c in live_claims(agents, now, ttl, exclude) if matches(c["pattern"], path)]


def conflicts(agents, patterns, now, ttl, exclude) -> list:
    return [(p, a, c) for p in patterns for a, c in live_claims(agents, now, ttl, exclude)
            if overlap(p, c["pattern"])]


def claim(ch, name, patterns, reason, now, ttl) -> dict:
    with locked(ch):
        agents_mod.load(ch, name)  # UnknownAgent before anything else
        found = conflicts(agents_mod.load_all(ch), patterns, now, ttl, exclude=name)
        if found:
            raise ClaimConflict(found)

        def fn(a):
            have = {c["pattern"] for c in a["claims"]}
            for p in patterns:
                if p not in have:
                    a["claims"].append({"pattern": p, "reason": reason, "since": iso(now)})
            if a.get("status") == "done":
                a["status"] = "active"

        return agents_mod.update_unlocked(ch, name, fn, now)


def release(ch, name, patterns, release_all, now) -> list:
    released = []

    def fn(a):
        keep = []
        for c in a["claims"]:
            if release_all or c["pattern"] in patterns:
                released.append(c["pattern"])
            else:
                keep.append(c)
        a["claims"] = keep

    agents_mod.update(ch, name, fn, now)
    return released


def touch(ch, name, patterns, now) -> dict:
    def fn(a):
        for p in patterns:
            if p not in a["touches"]:
                a["touches"].append(p)

    return agents_mod.update(ch, name, fn, now)
