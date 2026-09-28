from datetime import timedelta

from .agents import archive_done_unlocked
from .store import archive_messages_unlocked, locked

KEEP_DAYS = 14
DONE_DAYS = 7


def maybe_gc(ch, now, force: bool = False) -> bool:
    """Archive old messages and finished agents, at most once per calendar day."""
    marker = ch / ".last-gc"
    today = now.date().isoformat()

    def done_today():
        return marker.exists() and marker.read_text().strip() == today

    if not force and done_today():
        return False
    with locked(ch):
        if not force and done_today():  # another process won the race
            return False
        archive_messages_unlocked(ch, now - timedelta(days=KEEP_DAYS))
        archive_done_unlocked(ch, now - timedelta(days=DONE_DAYS))
        marker.write_text(today + "\n")
    return True
