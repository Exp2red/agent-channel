import shlex
import subprocess
import sys
from pathlib import Path

from . import agents
from .claims import expires, holders, ttl_for
from .errors import NotARepo
from .paths import channel_dir, common_dir, git, repo_root
from .render import delta
from .store import append, make_message

START = "# >>> agent-channel >>>"
END = "# <<< agent-channel <<<"


def staged_paths(cwd) -> list:
    out = subprocess.run(["git", "diff", "--cached", "--name-status", "-M", "-z"],
                         cwd=str(cwd), capture_output=True, check=True).stdout
    fields = out.decode("utf-8", "surrogateescape").split("\0")
    paths, i = [], 0
    while i < len(fields):
        status = fields[i]
        if not status:
            i += 1
            continue
        if status[0] in "RC":
            paths += [fields[i + 1], fields[i + 2]]
            i += 3
        else:
            paths.append(fields[i + 1])
            i += 2
    return sorted(set(paths))


def pre_commit(cwd, env, now) -> int:
    try:
        return _pre_commit(cwd, env, now)
    except Exception as e:  # a bug here must never block every commit in the repository
        print(f"agent-channel guard: internal error, commit allowed: {e!r}", file=sys.stderr)
        return 0


def _pre_commit(cwd, env, now) -> int:
    try:
        ch = channel_dir(cwd)
    except NotARepo:
        return 0
    if ch is None:
        return 0
    me = env.get("AGENT_CHANNEL_AS") or None
    ttl = ttl_for(cwd)
    everyone = agents.load_all(ch)
    hits = [(path, a, c) for path in staged_paths(cwd) for a, c in holders(everyone, path, now, ttl, exclude=me)]
    if me and any(a["name"] == me for a in everyone):
        agents.seen(ch, me, now)
    if not hits:
        return 0

    committer = me or "unknown"
    summary = "; ".join(f"{p} (claimed by {a['name']} via {c['pattern']})" for p, a, c in hits)
    reason = env.get("AGENT_CHANNEL_OVERRIDE")
    if reason:
        append(ch, make_message("guard", "-", "all", "GUARD", f"OVERRIDE by {committer}: {summary}. Reason: {reason}", now))
        print(f"agent-channel guard: override recorded in the channel ({len(hits)} claimed path(s))", file=sys.stderr)
        return 0

    lines = ["agent-channel guard: commit blocked. These staged paths are claimed by another active agent:"]
    for p, a, c in hits:
        lines.append(f"  {p}")
        lines.append(f"    claimed by {a['name']} ({a.get('task', '?')}) via {c['pattern']}, "
                     f"expires in {delta(expires(a, ttl) - now)}")
        reach = f"agent-channel say <YourName> {a['name']} QUESTION \"...\""
        if a.get("session"):
            reach += f"  or SendMessage to session {a['session']}"
        lines.append(f"    reach them: {reach}")
    lines.append("If you own the claim, commit as yourself:  AGENT_CHANNEL_AS=<YourName> git commit ...")
    lines.append("To proceed anyway (recorded in the channel):  AGENT_CHANNEL_OVERRIDE=\"<reason>\" git commit ...")
    print("\n".join(lines), file=sys.stderr)
    append(ch, make_message("guard", "-", "all", "GUARD", f"BLOCKED commit by {committer}: {summary}", now))
    return 1


def hooks_dir(cwd) -> Path:
    try:
        configured = git(cwd, "config", "--get", "core.hooksPath")
    except NotARepo:
        configured = ""
    if configured:
        p = Path(configured).expanduser()
        return p if p.is_absolute() else repo_root(cwd) / p
    return common_dir(cwd) / "hooks"


def install(cwd, command) -> Path:
    d = hooks_dir(cwd)
    d.mkdir(parents=True, exist_ok=True)
    hook = d / "pre-commit"
    block = f"{START}\n{shlex.join(command)} hook pre-commit || exit $?\n{END}\n"
    if hook.exists():
        text = hook.read_text()
        if START in text:
            before, _, rest = text.partition(START)
            _, _, after = rest.partition(END)
            new = before + block + after.lstrip("\n")
        elif text.startswith("#!"):
            first, _, rest = text.partition("\n")
            new = first + "\n" + block + rest
        else:
            new = block + text
    else:
        new = "#!/bin/sh\n" + block
    hook.write_text(new)
    hook.chmod(hook.stat().st_mode | 0o111)
    return hook
