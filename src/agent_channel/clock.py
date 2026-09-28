import os
from datetime import datetime


def parse_ts(value: str) -> datetime:
    if value.endswith(("Z", "z")):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt


def now() -> datetime:
    # AGENT_CHANNEL_FAKE_NOW exists so tests can freeze time across subprocesses
    # (the git hook runs in its own process).
    fake = os.environ.get("AGENT_CHANNEL_FAKE_NOW")
    if fake:
        return parse_ts(fake)
    return datetime.now().astimezone()


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")
