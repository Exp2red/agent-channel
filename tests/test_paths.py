import os

import pytest

from agent_channel.errors import ChannelError, NotARepo
from agent_channel.paths import channel_dir, common_dir


def test_no_channel_until_created(repo):
    assert channel_dir(repo) is None
    ch = channel_dir(repo, create=True)
    assert ch == common_dir(repo) / "agent-channel"
    assert (ch / "agents").is_dir() and (ch / "archive").is_dir() and (ch / "agents" / "archive").is_dir()


def test_worktrees_share_one_channel(repo, worktree):
    assert channel_dir(repo, create=True) == channel_dir(worktree)


def test_subdirectory_finds_same_channel(repo):
    sub = repo / "a" / "b"
    sub.mkdir(parents=True)
    assert channel_dir(repo, create=True) == channel_dir(sub)


def test_other_repo_sees_nothing(repo, tmp_path):
    from conftest import run_git
    other = tmp_path / "other"
    other.mkdir()
    run_git(other, "init", "-q")
    channel_dir(repo, create=True)
    assert channel_dir(other) is None


def test_symlinked_channel_is_refused(repo, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside, common_dir(repo) / "agent-channel")
    with pytest.raises(ChannelError):
        channel_dir(repo)


def test_symlinked_subdir_is_refused(repo, tmp_path):
    ch = channel_dir(repo, create=True)
    (ch / "archive").rmdir()
    os.symlink(tmp_path, ch / "archive")
    with pytest.raises(ChannelError):
        channel_dir(repo)


def test_outside_git_raises(tmp_path):
    with pytest.raises(NotARepo):
        channel_dir(tmp_path)
