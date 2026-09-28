from datetime import timedelta, timezone

import pytest

from agent_channel import agents, claims
from agent_channel.errors import ClaimConflict, UsageError
from agent_channel.paths import channel_dir
from conftest import NOW, run_git

TTL = timedelta(hours=4)


@pytest.mark.parametrize("pattern,path,expected", [
    ("src/a.py", "src/a.py", True),
    ("src/*.py", "src/a.py", True),
    ("src/*.py", "src/sub/a.py", False),
    ("src/**", "src/sub/deep/a.py", True),
    ("src/**/a.py", "src/a.py", True),
    ("src/**/a.py", "src/x/y/a.py", True),
    ("src/?.py", "src/ab.py", False),
    ("src/a.py", "src/a.pyc", False),
])
def test_matches(pattern, path, expected):
    assert claims.matches(pattern, path) is expected


def test_normalize(repo):
    assert claims.normalize("./src/x/") == "src/x/**"
    assert claims.normalize(str(repo / "src" / "a.py"), root=repo) == "src/a.py"
    for bad in ("../x", "/etc/passwd", "", "a/../../b"):
        with pytest.raises(UsageError):
            claims.normalize(bad, root=repo)


@pytest.mark.parametrize("a,b,expected", [
    ("src/a.py", "src/a.py", True),
    ("src/a.py", "src/b.py", False),
    ("src/**", "src/x/a.py", True),
    ("src/a.py", "src/b*.py", False),
    ("lib/**", "src/**", False),
])
def test_overlap(a, b, expected):
    assert claims.overlap(a, b) is expected and claims.overlap(b, a) is expected


def _setup(ch):
    agents.join(ch, "Otter", "t", "g", "s-otter", "/wt", "main", NOW)
    agents.join(ch, "Reiger", "t", "g", "s-reiger", "/wt", "main", NOW)


def test_claim_conflict_claims_nothing(repo):
    ch = channel_dir(repo, create=True)
    _setup(ch)
    claims.claim(ch, "Otter", ["src/**"], "refactor", NOW, TTL)
    with pytest.raises(ClaimConflict) as e:
        claims.claim(ch, "Reiger", ["docs/x.md", "src/a.py"], "fix", NOW, TTL)
    assert [(p, a["name"]) for p, a, _ in e.value.conflicts] == [("src/a.py", "Otter")]
    assert agents.load(ch, "Reiger")["claims"] == []


def test_claim_expires_after_ttl_and_refreshes_on_activity(repo):
    ch = channel_dir(repo, create=True)
    _setup(ch)
    claims.claim(ch, "Otter", ["src/a.py"], "", NOW, TTL)
    later = NOW + timedelta(hours=3)
    agents.seen(ch, "Otter", later)
    all_ = agents.load_all(ch)
    assert claims.holders(all_, "src/a.py", NOW + timedelta(hours=6), TTL)
    assert not claims.holders(all_, "src/a.py", NOW + timedelta(hours=7, minutes=1), TTL)


def test_mixed_utc_offsets_compare_correctly(repo):
    ch = channel_dir(repo, create=True)
    _setup(ch)
    claims.claim(ch, "Otter", ["src/a.py"], "", NOW, TTL)
    utc_now = (NOW + timedelta(hours=3, minutes=59)).astimezone(timezone.utc)
    assert claims.holders(agents.load_all(ch), "src/a.py", utc_now, TTL)


def test_release_and_done(repo):
    ch = channel_dir(repo, create=True)
    _setup(ch)
    claims.claim(ch, "Otter", ["src/a.py", "src/b.py"], "", NOW, TTL)
    assert claims.release(ch, "Otter", ["src/a.py"], False, NOW) == ["src/a.py"]
    assert claims.release(ch, "Otter", [], True, NOW) == ["src/b.py"]


def test_holders_excludes_self(repo):
    ch = channel_dir(repo, create=True)
    _setup(ch)
    claims.claim(ch, "Otter", ["src/a.py"], "", NOW, TTL)
    assert claims.holders(agents.load_all(ch), "src/a.py", NOW, TTL, exclude="Otter") == []


def test_ttl_from_git_config(repo):
    assert claims.ttl_for(repo) == TTL
    run_git(repo, "config", "agent-channel.ttl", "90m")
    assert claims.ttl_for(repo) == timedelta(minutes=90)
    with pytest.raises(UsageError):
        claims.parse_duration("soon")


def test_paths_from_a_subdirectory_resolve_against_cwd(repo):
    sub = repo / "src" / "sub"
    sub.mkdir(parents=True)
    assert claims.normalize("a.py", root=repo, cwd=sub) == "src/sub/a.py"
    assert claims.normalize("./", root=repo, cwd=sub) == "src/sub/**"
    assert claims.normalize("*.py", root=repo, cwd=sub) == "src/sub/*.py"
    with pytest.raises(UsageError):
        claims.normalize("../../../x", root=repo, cwd=sub)


def test_existing_directory_without_slash_means_the_directory(repo):
    (repo / "src").mkdir()
    assert claims.normalize("src", root=repo, cwd=repo) == "src/**"
