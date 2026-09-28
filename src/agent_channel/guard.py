import shlex
import subprocess
import sys
from pathlib import Path

from . import agents
from .claims import expires, holders, ttl_for
from .errors import NotARepo, UsageError
from .paths import channel_dir, common_dir, git, repo_root
from .render import delta
from .store import append, make_message

START = "# >>> agent-channel >>>"
END = "# <<< agent-channel <<<"
BLOCKED = 10  # the only exit code that blocks a commit; anything else (a missing tool, a crash) lets it through
SHELLS = ("sh", "bash", "dash", "zsh", "ksh")


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
    if not hits:
        _refresh(ch, me, everyone, now)
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
    return BLOCKED


def _refresh(ch, me, everyone, now) -> None:
    """A commit by a known agent counts as activity. Runs only after the decision, so a
    failure here (e.g. gc archived the agent meanwhile) can never let a conflict through."""
    if me and any(a["name"] == me for a in everyone):
        try:
            agents.seen(ch, me, now)
        except Exception:
            pass


def hooks_dir(cwd) -> Path:
    try:
        configured = git(cwd, "config", "--get", "core.hooksPath")
    except NotARepo:
        configured = ""
    if configured:
        p = Path(configured).expanduser()
        if not p.is_absolute() or any(p.resolve() == r or r in p.resolve().parents for r in _worktree_roots(cwd)):
            raise UsageError(
                f"core.hooksPath is {configured!r}, inside the work tree: every worktree has its own copy, "
                "usually tracked in git, so a guard written there would guard one worktree and leak a "
                "machine-local path into a commit. Add this line to that hook yourself (exit code "
                f"{BLOCKED} means block), or point core.hooksPath at an absolute directory outside the repository.")
        return p
    return common_dir(cwd) / "hooks"


def _worktree_roots(cwd) -> list:
    """Every checkout of this repository: a hooks dir inside any of them is tracked content."""
    roots = [repo_root(cwd).resolve()]
    for line in git(cwd, "worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            roots.append(Path(line[len("worktree "):]).resolve())
    return roots


def _block(command) -> str:
    return (f"{START}\n"
            f"# Blocks the commit only when the guard answers {BLOCKED}; a missing or broken tool never blocks.\n"
            f"if [ -x {shlex.quote(command[0])} ]; then\n"
            f"  _ac_rc=0; {shlex.join(command)} hook pre-commit || _ac_rc=$?\n"
            f"  [ \"$_ac_rc\" -ne {BLOCKED} ] || exit 1\n"
            f"fi\n"
            f"{END}\n")


def _interpreter(first_line: str) -> str:
    parts = first_line[2:].split()
    if not parts:
        return ""
    name = Path(parts[0]).name
    if name == "env":
        rest = [x for x in parts[1:] if not x.startswith("-")]
        name = Path(rest[0]).name if rest else ""
    return name


def install(cwd, command) -> Path:
    d = hooks_dir(cwd)
    d.mkdir(parents=True, exist_ok=True)
    hook = d / "pre-commit"
    block = _block(command)
    manual = f"{shlex.join(command)} hook pre-commit   # exit code {BLOCKED} means: block the commit"
    if hook.exists():
        text = hook.read_text()
        if text.startswith("#!") and _interpreter(text.partition("\n")[0]) not in SHELLS:
            raise UsageError(f"{hook} is not a shell script; add the guard to it yourself:\n  {manual}")
        if START in text and END not in text:
            raise UsageError(f"{hook} has an agent-channel start marker but no end marker; fix it by hand first")
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
