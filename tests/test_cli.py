import json


def test_full_flow(repo, worktree, cli):
    r = cli(repo, "join", "Otter", "--task", "2026-09-28-x", "--goal", "fix a", "--session", "s-otter")
    assert r.returncode == 0, r.stderr
    assert cli(worktree, "join", "Otter", "--task", "t", "--goal", "g").returncode == 2
    assert cli(worktree, "join", "Reiger", "--task", "t2", "--goal", "g").returncode == 0

    assert cli(repo, "claim", "Otter", "src/", "--reason", "refactor").returncode == 0
    r = cli(worktree, "claim", "Reiger", "src/a.py")
    assert r.returncode == 3 and "Otter" in r.stderr and "s-otter" in r.stderr

    r = cli(worktree, "check", "src/a.py", "--as", "Reiger")
    assert r.returncode == 3 and "Otter" in r.stdout
    assert cli(repo, "check", "src/a.py", "--as", "Otter").returncode == 0

    assert cli(worktree, "say", "Reiger", "Otter", "question", "-", input="may I?\nplease").returncode == 0
    r = cli(repo, "read", "--json")
    kinds = [m["kind"] for m in json.loads(r.stdout)]
    assert kinds == ["INFO", "INFO", "CLAIM", "QUESTION"]  # two joins, a claim, a question

    r = cli(repo, "who")
    assert "Otter" in r.stdout and "src/**" in r.stdout

    assert cli(repo, "status", "Otter", "done").returncode == 0
    assert cli(worktree, "claim", "Reiger", "src/a.py").returncode == 0


def test_no_channel_message(repo, cli):
    r = cli(repo, "who")
    assert r.returncode == 1 and "agent-channel join" in r.stderr


def test_decisions_include_archive(repo, cli):
    cli(repo, "join", "Otter", "--task", "t", "--goal", "g")
    cli(repo, "say", "Otter", "all", "DECISION", "use CAS in update()")
    cli(repo, "say", "Otter", "all", "INFO", "noise")
    r = cli(repo, "decisions", "cas")
    assert "use CAS in update()" in r.stdout and "noise" not in r.stdout


def test_read_filters(repo, cli):
    cli(repo, "join", "Otter", "--task", "t", "--goal", "g")
    for i in range(5):
        cli(repo, "say", "Otter", "all", "INFO", f"msg {i}")
    r = cli(repo, "read", "-n", "2")
    assert "msg 3" in r.stdout and "msg 4" in r.stdout and "msg 2" not in r.stdout
    assert "msg 1" in cli(repo, "read", "--grep", "MSG 1").stdout


def test_check_and_claim_from_subdirectory(repo, cli):
    sub = repo / "src" / "sub"
    sub.mkdir(parents=True)
    cli(repo, "join", "Otter", "--task", "t", "--goal", "g")
    cli(repo, "join", "Reiger", "--task", "t", "--goal", "g")
    assert cli(repo, "claim", "Otter", "src/sub/a.py").returncode == 0
    r = cli(sub, "check", "a.py", "--as", "Reiger")
    assert r.returncode == 3 and "src/sub/a.py" in r.stdout
    assert cli(sub, "claim", "Reiger", "b.py").returncode == 0
    assert "src/sub/b.py" in cli(repo, "who").stdout
