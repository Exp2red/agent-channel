"""One-time import from the 'samenwerken' prototype (Dutch text format)."""
import json
import os
import re
from datetime import datetime
from pathlib import Path

from .agents import path_for
from .claims import normalize
from .clock import iso
from .errors import UsageError
from .store import append_unlocked, iter_file, locked, new_id

HEADER = re.compile(r"^── (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) · (\S+) \((.*?)\) → (\S+) · (\S+)\s*$")
KIND = {"INFO": "INFO", "VRAAG": "QUESTION", "ANTWOORD": "ANSWER", "CLAIM": "CLAIM", "VRIJ": "RELEASE",
        "BLOKKADE": "BLOCKED", "BESLUIT": "DECISION", "KLAAR": "DONE"}
TO = {"iedereen": "all", "gebruiker": "human"}
STATUS = {"actief": "active", "wacht": "waiting", "klaar": "done"}


def _messages(text):
    current, body = None, []

    def flush():
        if current:
            while body and not body[-1].strip():
                body.pop()
            yield current, "\n".join(body)

    for line in text.splitlines():
        m = HEADER.match(line)
        if m:
            yield from flush()
            current, body = m.groups(), []
        elif current is not None:
            body.append(line)
    yield from flush()


def _agent(text, now):
    fields = dict(re.findall(r"^([A-Za-z/]+):[ \t]*(.*)$", text.split("\n\n", 1)[0], re.M))

    def section(title):
        m = re.search(rf"^{title}.*?\n((?:- .*\n?)*)", text, re.M)
        items = []
        for line in (m.group(1) if m else "").splitlines():
            item = re.split(r"\s{2,}|\t", line[2:].strip())[0]
            if item:
                items.append(normalize(item))
        return items

    return {"name": fields["Naam"], "task": fields.get("Taak/spec", "-"), "goal": fields.get("Doel", ""),
            "session": fields.get("Sessie", ""), "worktree": fields.get("Worktree", ""),
            "branch": fields.get("Branch", ""), "status": STATUS.get(fields.get("Status", ""), "waiting"),
            "started": iso(now), "last_seen": iso(now),
            "claims": [{"pattern": p, "reason": "imported", "since": iso(now)} for p in section("Claims")],
            "touches": section("Raakt")}


def import_legacy(ch, src_dir: Path, now):
    src_dir = Path(src_dir)
    if not (src_dir / "kanaal.txt").exists():
        raise UsageError(f"{src_dir} does not look like a samenwerken folder (no kanaal.txt)")
    files = sorted((src_dir / "archief").glob("kanaal-*.txt")) + [src_dir / "kanaal.txt"]
    agent_files = sorted((src_dir / "agenten").glob("*.txt")) + sorted((src_dir / "agenten" / "archief").glob("*.txt"))
    n_msgs = n_agents = 0
    with locked(ch):
        existing = {(m["ts"], m["from"], m["body"]) for p in [ch / "channel.jsonl", *(ch / "archive").glob("*.jsonl")] for m in iter_file(p)}
        for f in files:
            for (stamp, frm, task, to, kind), body in _messages(f.read_text(encoding="utf-8")):
                ts = datetime.strptime(stamp, "%Y-%m-%d %H:%M").astimezone()
                msg = {"id": new_id(ts), "ts": iso(ts), "from": frm, "task": task, "to": TO.get(to, to),
                       "kind": KIND.get(kind, "INFO"), "body": body, "reply_to": None}
                if (msg["ts"], frm, body) in existing:
                    continue
                target = ch / "channel.jsonl" if f.name == "kanaal.txt" else ch / "archive" / f"{ts.strftime('%Y-%m')}.jsonl"
                append_unlocked(target, msg)
                existing.add((msg["ts"], frm, body))
                n_msgs += 1
        for f in agent_files:
            agent = _agent(f.read_text(encoding="utf-8"), now)
            dest = path_for(ch, agent["name"])
            if f.parent.name == "archief":
                agent["status"], agent["claims"] = "done", []
                dest = ch / "agents" / "archive" / dest.name
            if dest.exists() or (ch / "agents" / "archive" / dest.name).exists():
                continue
            fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                out.write(json.dumps(agent, ensure_ascii=False, indent=2) + "\n")
            n_agents += 1
    return n_msgs, n_agents
