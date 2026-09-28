import json
import os
import shlex
from datetime import timedelta

from .agents import load_all
from .claims import ttl_for
from .clock import parse_ts
from .errors import ChannelError
from .gc import maybe_gc
from .paths import channel_dir
from .render import agent_line, one_line
from .store import read

BUDGET = 2400
FOOTER = "Full picture: who, read -n 30, decisions"


class _Budget:
    def __init__(self, limit):
        self.limit, self.used, self.lines, self.full = limit, 0, [], False

    def add(self, line) -> bool:
        n = len((line + "\n").encode("utf-8"))
        if self.full or self.used + n > self.limit:
            self.full = True
            return False
        self.lines.append(line)
        self.used += n
        return True


def session_start(stdin_text: str, command, now) -> str:
    try:
        cwd = (json.loads(stdin_text or "{}") or {}).get("cwd") or os.getcwd()
    except (ValueError, AttributeError):
        cwd = os.getcwd()
    try:
        ch = channel_dir(cwd)
    except ChannelError:
        return ""
    if ch is None:
        return ""
    maybe_gc(ch, now)
    ttl = ttl_for(cwd)
    live = load_all(ch, include_done=False)
    msgs = read(ch)

    b = _Budget(BUDGET - len((FOOTER + "\n").encode()))
    b.add("AGENT CHANNEL: other agents may be working in this repository. Follow the agent-channel skill before changing files.")
    b.add(f"CLI: {shlex.join(command)}  (who | read | check <path> | join | claim | say)")
    b.add(f"Agents ({len(live)}):" if live else "Agents: none active")
    for a in live[:8]:
        b.add("  " + agent_line(a, now, ttl))
    if len(live) > 8:
        b.add(f"  +{len(live) - 8} more")
    week = now - timedelta(days=7)
    decisions = [m for m in msgs if m.get("kind") == "DECISION" and parse_ts(m["ts"]) >= week]
    if decisions and b.add("Decisions (last 7 days):"):
        for m in reversed(decisions[-5:]):
            if not b.add("  " + one_line(m, 160)):
                break
    decision_ids = {m["id"] for m in decisions}
    recent = [m for m in msgs if m.get("id") not in decision_ids][-5:]
    if recent and b.add("Latest:"):
        for m in reversed(recent):
            if not b.add("  " + one_line(m, 200)):
                break
    return "\n".join(b.lines + [FOOTER]) + "\n"
