from .agents import load_all
from .claims import ttl_for
from .clock import now as clock_now
from .render import agent_line, claim_lines, full, one_line, truncate
from .store import read

KEYS = " ↑↓ scroll  enter open  b decisions  / search  q quit"


def _section(title, width):
    return truncate(f"── {title} " + "─" * width, width)


def dashboard(agents, messages, now, ttl, width, height, offset=0, only_decisions=False, repo="") -> list:
    live = [a for a in agents if a.get("status") != "done"]
    stamp = now.strftime("%Y-%m-%d %H:%M")
    title = f" agent-channel · {repo} ({len(live)} agents)"
    lines = [truncate(title.ljust(max(0, width - len(stamp))) + stamp, width), _section("Agents", width)]
    lines += [truncate("  " + agent_line(a, now, ttl), width) for a in live] or ["  (none)"]
    lines.append(_section("Claims", width))
    lines += [truncate("  " + l, width) for l in claim_lines(live, now, ttl)] or ["  (none)"]
    lines.append(_section("Messages" + (" · decisions only" if only_decisions else ""), width))
    msgs = [m for m in messages if not only_decisions or m.get("kind") == "DECISION"]
    room = max(0, height - len(lines) - 1)
    end = max(0, len(msgs) - offset)
    for m in msgs[max(0, end - room):end]:
        mark = "! " if m.get("kind") == "GUARD" else "  "
        lines.append(mark + one_line(m, width - 2))
    lines = lines[: height - 1]
    lines += [""] * (height - 1 - len(lines))
    lines.append(truncate(KEYS, width))
    return lines


def _prompt(scr, label) -> str:
    import curses
    h, w = scr.getmaxyx()
    scr.move(h - 1, 0)
    scr.clrtoeol()
    scr.addnstr(h - 1, 0, label, w - 1)
    curses.echo()
    scr.timeout(-1)
    try:
        return scr.getstr(h - 1, len(label), w - len(label) - 1).decode("utf-8", "replace")
    finally:
        curses.noecho()
        scr.timeout(1000)


def _show(scr, msg):
    if msg is None:
        return
    h, w = scr.getmaxyx()
    scr.erase()
    for y, line in enumerate(full(msg).splitlines()[: h - 1]):
        scr.addnstr(y, 0, line, w - 1)
    scr.addnstr(h - 1, 0, " any key to go back", w - 1)
    scr.timeout(-1)
    scr.getch()
    scr.timeout(1000)


def run(ch, cwd) -> None:
    import curses

    repo = cwd.name

    def loop(scr):
        curses.curs_set(0)
        scr.timeout(1000)
        offset, only, term = 0, False, ""
        while True:
            now = clock_now()
            h, w = scr.getmaxyx()
            msgs = read(ch)
            if term:
                msgs = [m for m in msgs if term.lower() in str(m.get("body", "")).lower()]
            offset = min(offset, max(0, len(msgs) - 1))
            lines = dashboard(load_all(ch), msgs, now, ttl_for(cwd), w, h, offset, only, repo)
            scr.erase()
            for y, line in enumerate(lines):
                try:
                    scr.addnstr(y, 0, line, w - 1, curses.A_BOLD if line.startswith("! ") else 0)
                except curses.error:
                    pass
            scr.refresh()
            key = scr.getch()
            if key in (ord("q"), 27):
                return
            if key == curses.KEY_UP:
                offset += 1
            elif key == curses.KEY_DOWN:
                offset = max(0, offset - 1)
            elif key == ord("b"):
                only, offset = not only, 0
            elif key == ord("/"):
                term, offset = _prompt(scr, "search: "), 0
            elif key in (10, 13, curses.KEY_ENTER):
                visible = [m for m in msgs if not only or m.get("kind") == "DECISION"]
                _show(scr, visible[-1 - offset] if visible else None)

    curses.wrapper(loop)
