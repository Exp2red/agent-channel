import os
import subprocess
from pathlib import Path
from typing import Optional

from .errors import ChannelError, NotARepo

CHANNEL = "agent-channel"
SUBDIRS = ("agents", "agents/archive", "archive")


def git(cwd, *args) -> str:
    try:
        out = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True)
    except FileNotFoundError as e:
        raise NotARepo("git is not installed") from e
    except subprocess.CalledProcessError as e:
        raise NotARepo(e.stderr.strip() or "not a git repository") from e
    return out.stdout.rstrip("\n")


def repo_root(cwd) -> Path:
    return Path(git(cwd, "rev-parse", "--show-toplevel"))


def common_dir(cwd) -> Path:
    return Path(git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()


def branch(cwd) -> str:
    try:
        return git(cwd, "branch", "--show-current") or "(detached)"
    except NotARepo:
        return "(unknown)"


def channel_dir(cwd, create: bool = False) -> Optional[Path]:
    """The channel for the repository containing cwd, or None if it has none.

    Refuses anything that is not a real directory inside the git common dir,
    so a symlink can never point the channel somewhere else.
    """
    cd = common_dir(cwd)
    ch = cd / CHANNEL
    if not ch.exists() and not ch.is_symlink():
        if not create:
            return None
        ch.mkdir(mode=0o700)
    if ch.is_symlink() or not ch.is_dir() or ch.resolve() != ch:
        raise ChannelError(f"refusing {ch}: the channel must be a real directory inside {cd}")
    for sub in SUBDIRS:
        p = ch / sub
        if p.is_symlink():
            raise ChannelError(f"refusing {p}: symlinks are not allowed inside the channel")
        p.mkdir(mode=0o700, exist_ok=True)
    for d in (ch, *(ch / s for s in SUBDIRS)):
        for entry in os.scandir(d):
            if entry.is_symlink():
                raise ChannelError(f"refusing {entry.path}: symlinks are not allowed inside the channel")
    return ch
