import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_manifests_are_valid_json_and_consistent():
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text())
    assert plugin["name"] == "agent-channel"
    assert market["plugins"][0]["name"] == "agent-channel"
    cmd = hooks["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert "${CLAUDE_PLUGIN_ROOT}/bin/agent-channel" in cmd and "session-start" in cmd


def test_bin_wrapper_runs_without_install(repo, tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    r = subprocess.run([str(ROOT / "bin" / "agent-channel"), "hook", "session-start"], cwd=repo,
                       input=json.dumps({"cwd": str(repo)}), capture_output=True, text=True, env=env)
    assert r.returncode == 0 and r.stdout == ""
    subprocess.run([str(ROOT / "bin" / "agent-channel"), "join", "Otter", "--task", "t", "--goal", "g"],
                   cwd=repo, check=True, env=env, capture_output=True)
    r = subprocess.run([str(ROOT / "bin" / "agent-channel"), "hook", "session-start"], cwd=repo,
                       input=json.dumps({"cwd": str(repo)}), capture_output=True, text=True, env=env)
    assert str(ROOT / "bin" / "agent-channel") in r.stdout


def test_skill_has_frontmatter():
    text = (ROOT / "skills" / "agent-channel" / "SKILL.md").read_text()
    assert text.startswith("---\nname: agent-channel\ndescription: ")
