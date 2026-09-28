import argparse
import json
import os
import sys
import time
from pathlib import Path

from . import __version__, agents, claims, guard
from . import hook as hook_mod
from .clock import now as clock_now
from .errors import ChannelError, ClaimConflict, NoChannel
from .gc import maybe_gc
from .paths import branch, channel_dir, repo_root
from .render import agent_line, delta, full
from .store import KINDS, append, make_message, read


def self_command() -> list:
    explicit = os.environ.get("AGENT_CHANNEL_SELF")
    if explicit:
        return [explicit]
    argv0 = sys.argv[0] if sys.argv else ""
    if os.path.basename(argv0) == "agent-channel" and os.path.isfile(argv0):
        return [os.path.abspath(argv0)]
    return [sys.executable, "-m", "agent_channel"]


def current_channel(create: bool = False):
    ch = channel_dir(Path.cwd(), create=create)
    if ch is None:
        raise NoChannel("no agent channel in this repository yet; start one with: "
                        "agent-channel join <Name> --task <slug> --goal \"...\"")
    return ch


def _post(ch, name, kind, body, now, to="all", reply_to=None):
    a = agents.load(ch, name)
    return append(ch, make_message(name, a.get("task", "-"), to, kind, body, now, reply_to))


def _print_conflicts(e: ClaimConflict, ttl, now):
    print("agent-channel: claim refused, overlapping live claims:", file=sys.stderr)
    for pattern, owner, c in e.conflicts:
        reach = f", session {owner['session']}" if owner.get("session") else ""
        print(f"  {pattern} overlaps {owner['name']}'s {c['pattern']} "
              f"(expires in {delta(claims.expires(owner, ttl) - now)}{reach})", file=sys.stderr)
    print("  ask them first: agent-channel say <YourName> <Owner> QUESTION \"...\"", file=sys.stderr)


def cmd_join(a, now):
    ch = current_channel(create=True)
    root = repo_root(Path.cwd())
    agents.join(ch, a.name, a.task, a.goal, a.session or "", root, branch(root), now)
    maybe_gc(ch, now)
    _post(ch, a.name, "INFO", f"joined: {a.goal}", now)
    print(f"joined as {a.name}")


def cmd_status(a, now):
    ch = current_channel()
    agents.set_status(ch, a.name, a.status, now)
    if a.status == "done":
        _post(ch, a.name, "DONE", a.note or "done; all claims released", now)
    print(f"{a.name}: {a.status}")


def cmd_claim(a, now):
    ch = current_channel()
    ttl = claims.ttl_for(Path.cwd())
    root = repo_root(Path.cwd())
    patterns = [claims.normalize(p, root) for p in a.patterns]
    try:
        claims.claim(ch, a.name, patterns, a.reason or "", now, ttl)
    except ClaimConflict as e:
        _print_conflicts(e, ttl, now)
        return 3
    _post(ch, a.name, "CLAIM", " ".join(patterns) + (f" ({a.reason})" if a.reason else ""), now)
    print(f"claimed: {' '.join(patterns)}")
    return 0


def cmd_release(a, now):
    ch = current_channel()
    root = repo_root(Path.cwd())
    patterns = [claims.normalize(p, root) for p in a.patterns]
    released = claims.release(ch, a.name, patterns, a.all or not patterns, now)
    if released:
        _post(ch, a.name, "RELEASE", " ".join(released), now)
    print(f"released: {' '.join(released) or '(nothing)'}")


def cmd_touch(a, now):
    ch = current_channel()
    root = repo_root(Path.cwd())
    claims.touch(ch, a.name, [claims.normalize(p, root) for p in a.patterns], now)


def cmd_check(a, now):
    ch = current_channel()
    ttl = claims.ttl_for(Path.cwd())
    root = repo_root(Path.cwd())
    all_ = agents.load_all(ch)
    if a.name:
        agents.seen(ch, a.name, now)
    code = 0
    for raw in a.paths:
        path = claims.normalize(raw, root)
        found = claims.holders(all_, path, now, ttl, exclude=a.name)
        if not found:
            print(f"{path}: free")
        for owner, c in found:
            code = 3
            print(f"{path}: claimed by {owner['name']} via {c['pattern']} "
                  f"(expires in {delta(claims.expires(owner, ttl) - now)}, session {owner.get('session') or '?'})")
    return code


def cmd_say(a, now):
    ch = current_channel()
    body = sys.stdin.read() if a.body == "-" else a.body
    msg = _post(ch, a.name, a.kind, body.rstrip("\n"), now, to=a.to, reply_to=a.reply_to)
    agents.seen(ch, a.name, now)
    maybe_gc(ch, now)
    print(f"posted {msg['id']}")


def _filtered(ch, a):
    msgs = read(ch, include_archive=getattr(a, "all", False))
    if getattr(a, "kind", None):
        msgs = [m for m in msgs if m.get("kind") == a.kind.upper()]
    if getattr(a, "grep", None):
        term = a.grep.lower()
        msgs = [m for m in msgs if term in json.dumps(m, ensure_ascii=False).lower()]
    return msgs


def cmd_read(a, now):
    ch = current_channel()
    msgs = _filtered(ch, a)[-a.n:]
    if a.json:
        print(json.dumps(msgs, ensure_ascii=False, indent=2))
    else:
        for m in msgs:
            print(full(m) + "\n")
    if a.follow:
        seen_ids = {m["id"] for m in read(ch)}
        try:
            while True:
                time.sleep(1)
                for m in _filtered(ch, a):
                    if m["id"] not in seen_ids:
                        seen_ids.add(m["id"])
                        print(full(m) + "\n", flush=True)
        except KeyboardInterrupt:
            pass


def cmd_who(a, now):
    ch = current_channel()
    ttl = claims.ttl_for(Path.cwd())
    live = agents.load_all(ch, include_done=False)
    if a.json:
        print(json.dumps(live, ensure_ascii=False, indent=2))
        return
    if not live:
        print("(no active agents)")
    for ag in live:
        print(agent_line(ag, now, ttl))
        print(f"    session {ag.get('session') or '?'} · {ag.get('worktree', '?')}")
        for c in ag.get("claims", []):
            print(f"    claims {c['pattern']}" + (f"  ({c['reason']})" if c.get("reason") else ""))


def cmd_decisions(a, now):
    ch = current_channel()
    a.kind, a.all, a.grep = "DECISION", True, a.term
    for m in _filtered(ch, a):
        print(full(m) + "\n")


def cmd_gc(a, now):
    ch = current_channel()
    maybe_gc(ch, now, force=True)
    print("archived messages older than 14 days and agents done for 7 days")


def cmd_install_guard(a, now):
    path = guard.install(Path.cwd(), self_command())
    print(f"guard installed in {path}")


def cmd_hook(a, now):
    if a.event == "pre-commit":
        return guard.pre_commit(Path.cwd(), os.environ, now)
    try:  # a SessionStart hook must never fail the session
        sys.stdout.write(hook_mod.session_start(sys.stdin.read(), self_command(), now))
    except Exception:
        pass
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agent-channel", description="Coordination for parallel coding agents in one git repository.")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("join", help="create your identity")
    s.add_argument("name")
    s.add_argument("--task", required=True)
    s.add_argument("--goal", required=True)
    s.add_argument("--session", help="your harness session name, so others can message you")
    s.set_defaults(fn=cmd_join)

    s = sub.add_parser("status", help="set active, waiting or done")
    s.add_argument("name")
    s.add_argument("status", choices=agents.STATUSES)
    s.add_argument("--note")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("claim", help="claim paths or globs you are about to change")
    s.add_argument("name")
    s.add_argument("patterns", nargs="+")
    s.add_argument("--reason")
    s.set_defaults(fn=cmd_claim)

    s = sub.add_parser("release", help="release claims (all when no pattern is given)")
    s.add_argument("name")
    s.add_argument("patterns", nargs="*")
    s.add_argument("--all", action="store_true")
    s.set_defaults(fn=cmd_release)

    s = sub.add_parser("touch", help="record paths you read but do not change")
    s.add_argument("name")
    s.add_argument("patterns", nargs="+")
    s.set_defaults(fn=cmd_touch)

    s = sub.add_parser("check", help="who claims these paths? exit 3 if someone else does")
    s.add_argument("paths", nargs="+")
    s.add_argument("--as", dest="name")
    s.set_defaults(fn=cmd_check)

    s = sub.add_parser("say", help="post a message ('-' reads the body from stdin)")
    s.add_argument("name")
    s.add_argument("to")
    s.add_argument("kind", type=str.upper, choices=[k for k in KINDS if k != "GUARD"])
    s.add_argument("body")
    s.add_argument("--reply-to")
    s.set_defaults(fn=cmd_say)

    s = sub.add_parser("read", help="read messages")
    s.add_argument("-n", type=int, default=30)
    s.add_argument("--follow", action="store_true")
    s.add_argument("--kind")
    s.add_argument("--grep")
    s.add_argument("--all", action="store_true")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_read)

    s = sub.add_parser("who", help="active agents and their claims")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_who)

    s = sub.add_parser("decisions", help="all DECISION messages, archive included")
    s.add_argument("term", nargs="?")
    s.set_defaults(fn=cmd_decisions)

    s = sub.add_parser("gc", help="archive now")
    s.set_defaults(fn=cmd_gc)

    s = sub.add_parser("install-guard", help="add the claim guard to this repository's pre-commit hook")
    s.set_defaults(fn=cmd_install_guard)

    s = sub.add_parser("hook", help="entry points for git and Claude Code hooks")
    s.add_argument("event", choices=["pre-commit", "session-start"])
    s.set_defaults(fn=cmd_hook)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args, clock_now()) or 0
    except ChannelError as e:
        print(f"agent-channel: {e}", file=sys.stderr)
        return e.exit_code
