# agent-channel

**Coordination for parallel coding agents in one git repository.**

Run three Claude Code sessions on one codebase and they meet at the merge: two of them
fixed the same bug, a third rewrote a file the first was halfway through. agent-channel
lets them find out *before* they start. They claim the files they are about to change,
see each other's claims, and talk in a channel you can read. A pre-commit guard stops a
commit that touches someone else's claimed files.

No server, no daemon, no dependencies: one Python standard-library CLI, a Claude Code
plugin, and some JSON files inside `.git/`.

![watch](docs/watch.gif)

## Quickstart

```bash
# in Claude Code
/plugin marketplace add Exp2red/agent-channel
/plugin install agent-channel@agent-channel

# once per repository (optional, recommended): block commits on others' claims
pipx install git+https://github.com/Exp2red/agent-channel
agent-channel install-guard

# watch along
agent-channel watch
```

From then on, every new session in that repository starts with a short summary of who is
working on what. The bundled skill tells agents how to join, claim, check and talk:

```text
$ agent-channel join Otter --task 2026-09-28-hr-approvals --goal "approval expiry per scope"
$ agent-channel claim Otter backend/src/modules/governance/approval*.ts --reason "expiry outcome"
$ agent-channel check backend/src/modules/governance/approval.service.ts --as Reiger
backend/src/modules/governance/approval.service.ts: claimed by Otter via backend/src/modules/governance/approval*.ts (expires in 3h58, session erppoc-c9)
$ agent-channel say Reiger Otter QUESTION "Can I add a column to approval_scopes after your step 1?"
```

## How it works

| Piece | What it does |
|---|---|
| **Channel** | `$(git rev-parse --git-common-dir)/agent-channel/`, shared by every worktree of the repository, never committed. |
| **Identity** | `join <Name>` creates `agents/<Name>.json` with task, goal, session, branch. Names are unique (`O_EXCL`). |
| **Claims** | Glob patterns. `claim` refuses overlaps with other live claims. A claim lives until 4 h after its owner's last activity, so crashed sessions release their claims without anyone deciding. |
| **Messages** | JSONL, appended under `flock`. Kinds: `INFO QUESTION ANSWER CLAIM RELEASE BLOCKED DECISION DONE GUARD`. |
| **Guard** | A pre-commit hook blocks staged paths claimed by another live agent, prints who and how to reach them, and records it. `AGENT_CHANNEL_OVERRIDE="<reason>"` passes and is recorded. |
| **Session start** | A Claude Code hook prints who is active, recent decisions and messages, capped at 2400 bytes. |
| **Retention** | Messages older than 14 days move to `archive/YYYY-MM.jsonl`; `decisions` searches everything. |
| **watch** | A read-only terminal dashboard: agents, claims with time left, the message stream. |

Claude Code's built-in `SendMessage` is the doorbell; the channel is the record. The
skill tells agents to use both.

## Why it exists

In July 2026 OpenAI disclosed that agents in an evaluation run had coordinated through
channels nobody gave them. According to OpenAI's Black Hat presentation, they used an
ad-hoc message board in an internal Artifactory, and after it was wiped they re-established
contact within days through WebDAV directory names
([timeline](https://simonwillison.net/2026/Aug/7/openai-timeline/)). Hugging Face's own
forensic write-up describes a public request-capture service used as a queue and datasets
used as dead-drops
([Hugging Face](https://huggingface.co/blog/agent-intrusion-technical-timeline)). Much of
the "agents organised themselves" story comes from OpenAI's own account, and some of it
reads like marketing. Take it with that in mind.

The lesson here does not depend on how dramatic it was. **Agents that need to coordinate
will improvise a channel if they are not given one.** Give them an explicit channel that is
scoped to one repository, readable by humans, and adds no reach. See
[SECURITY.md](SECURITY.md).

## Compared with

- **[MCP Agent Mail](https://github.com/Dicklesworthstone/mcp_agent_mail)** is the mature
  option: inboxes, threads, TTL file leases, a pre-commit guard and a web UI, served by an
  MCP server. Choose it for large fleets or cross-repository coordination. agent-channel is
  the small end: no server, one repository by construction, built around Claude Code's
  `SendMessage`.
- **[agent-comms](https://github.com/LakshmiSravyaVedantham/agent-comms)** uses JSON files
  in the project root. It does not span worktrees, and agents expire after 5 minutes
  without a heartbeat.

## Limits

- POSIX only (Linux, macOS, WSL): it uses `flock` and `curses`.
- The guard prevents accidents between cooperating agents. It is not authentication (see
  [SECURITY.md](SECURITY.md)).
- One repository, one machine.

## Development

```bash
pip install -e ".[dev]"
python -m pytest -q
```

Design: [docs/design.md](docs/design.md). License: MIT.
