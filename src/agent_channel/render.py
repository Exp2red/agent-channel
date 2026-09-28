from .claims import QUIET_AFTER, expires, is_live, live_claims
from .clock import parse_ts


def truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[: max(0, n - 1)] + "…"


def delta(td) -> str:
    mins = int(td.total_seconds() // 60)
    if mins < 0:
        return "expired"
    if mins < 60:
        return f"{mins}m"
    h, m = divmod(mins, 60)
    return f"{h}h{m:02d}"


def agent_state(agent, now, ttl) -> str:
    if agent.get("status") == "done":
        return "done"
    if not is_live(agent, now, ttl):
        return "expired"
    if now - parse_ts(agent["last_seen"]) > QUIET_AFTER:
        return "quiet"
    return agent.get("status", "active")


def agent_line(agent, now, ttl) -> str:
    n = len(agent.get("claims", []))
    line = f"{agent['name']}  {agent_state(agent, now, ttl)}  {agent.get('task', '?')}  {agent.get('branch', '?')}"
    if n:
        line += f"  {n} claim{'s' if n != 1 else ''}, expire in {delta(expires(agent, ttl) - now)}"
    return line


def claim_lines(agents, now, ttl) -> list:
    return [f"{a['name']}  {c['pattern']}  {delta(expires(a, ttl) - now)}" for a, c in live_claims(agents, now, ttl)]


def header(msg) -> str:
    return f"{msg['ts'][:16].replace('T', ' ')} {msg.get('from', '?')} → {msg.get('to', '?')} {msg.get('kind', '?')}"


def one_line(msg, width: int) -> str:
    return truncate(f"{header(msg)}  {' '.join(str(msg.get('body', '')).split())}", width)


def full(msg) -> str:
    text = f"{header(msg)}  [{msg.get('id', '')}]\n{msg.get('body', '')}"
    if msg.get("reply_to"):
        text += f"\n  (reply to {msg['reply_to']})"
    return text
