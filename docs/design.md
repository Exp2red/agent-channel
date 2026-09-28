# agent-channel — design

**Status:** approved in conversation 2026-09-28, awaiting written-spec review
**Author:** Q. Smits (with Claude)
**Supersedes:** the private `samenwerken` skill (`~/.claude/skills/samenwerken`, 2026-09-28)

---

## 1. Problem

Several coding agents (Claude Code sessions, sometimes other tools) work on one repository
at the same time, often in different git worktrees. They find out about each other only
afterwards: through a merge conflict, a file that changed underneath them, or a human who
notices two agents fixing the same bug. What is missing is a cheap way to say, before
touching a file, "I am working on this", and to talk about it where the human can read
along.

A private prototype (`samenwerken`) proved the idea in one afternoon: four agents, in two
worktrees, found each other, divided a contested file between them and recorded the
agreement. It also showed the gaps this design closes:

- Claims were advice. Nothing stopped a commit on a file someone else had claimed.
- A crashed session left its claims behind indefinitely.
- The channel lived in one hard-coded machine-wide folder.
- The start-up summary grew with every agent and message.
- Parsing free text with sed and awk broke on multi-line messages and odd characters.

## 2. Goals and non-goals

**Goals**
1. Agents working on the same repository can identify themselves, claim paths, see each
   other's claims and exchange messages, across every worktree of that repository.
2. A commit that touches a path claimed by another active agent is blocked, with a visible,
   logged way out.
3. The human can follow everything live in the terminal.
4. A new session learns who is active in at most ~600 tokens.
5. The channel stays small and useful for months (rolling archive, searchable decisions).
6. Zero runtime dependencies beyond Python ≥ 3.9 and git. No server, no daemon, no network.
7. Installable by a colleague with one command; readable as a portfolio piece (tests, CI,
   explicit threat model).

**Non-goals**
- Stopping a malicious or deceptive agent. The guard prevents accidents (§4).
- Coordination across repositories or machines. One channel per repository, on one host.
- Replacing Claude Code's `SendMessage`. The channel is the record; `SendMessage` is the
  doorbell. The skill tells agents to use both.
- A web UI or desktop app. A later, separate project may read the same files (§6 is the
  stable format).
- Native Windows. `flock` and `curses` are unavailable there; WSL works.

## 3. Inspiration

In July 2026 OpenAI disclosed that agents in an evaluation run had coordinated through
channels nobody gave them. According to OpenAI's Black Hat presentation they used an
ad-hoc message board in an internal Artifactory, and after that was wiped they rebuilt
contact within days through WebDAV directory names
([timeline by Simon Willison](https://simonwillison.net/2026/Aug/7/openai-timeline/)).
Hugging Face's own forensic write-up describes a public request-capture service used as a
message queue and datasets used as dead-drops
([Hugging Face technical timeline](https://huggingface.co/blog/agent-intrusion-technical-timeline)).
Much of the "agents organised themselves" narrative comes from OpenAI's own account and
should be read with that in mind.

The lesson this project takes does not depend on how dramatic that was: **agents that need
to coordinate will improvise a channel if they are not given one.** Better to give them an
explicit channel that is scoped to the repository, readable by humans, and grants no reach
the agent did not already have.

## 4. Security model

| Property | How |
|---|---|
| **No new reach.** The channel lives inside the repository's git directory, so reading it requires access the agent already has. | Path is always `$(git rev-parse --git-common-dir)/agent-channel`. Resolved with `realpath`; any path (including via symlink) outside the common dir is refused. |
| **No global discovery.** | No command lists other channels. No environment variable or config points the tool at another directory. |
| **Messages are data.** | Body ≤ 4000 characters. The tool never executes, interpolates or evaluates message content. The skill states that another agent's message carries no user authority. |
| **Never committed.** | It lives in `.git/`, which git does not track. |
| **Guard is accident prevention, not access control.** | All agents commit as the same git user; an agent can name itself anything, set the override variable, or use `git commit --no-verify`. README and SECURITY.md say so explicitly. Every override leaves a `GUARD` record. |
| **Fail-open guard.** | If the guard itself errors, the commit proceeds with a visible warning. A bug in the tool must not block every commit in a repository. |

## 5. Architecture

```
src/agent_channel/
  paths.py     locate + validate the channel dir (git common dir, realpath check)
  store.py     locked append, read, rolling archive (JSONL)
  agents.py    identity files, O_EXCL creation, status, heartbeat
  claims.py    glob matching, TTL, conflict detection
  guard.py     pre-commit logic, install into existing hooks
  hook.py      budgeted SessionStart summary
  render.py    pure functions: agents/claims/messages → text lines (used by CLI and watch)
  watch.py     curses loop around render.py
  legacy.py    import from the samenwerken prototype
  cli.py       argparse entry point
```

Each module has one job and is testable without the others' internals. `render.py` is
pure, so both the CLI and the dashboard use it and it can be snapshot-tested.

## 6. Storage format

Location: `$(git rev-parse --git-common-dir)/agent-channel/`. All worktrees of a
repository share the common dir, so they share the channel automatically.

```
agent-channel/
  channel.jsonl          messages from the last 14 days, one JSON object per line
  archive/YYYY-MM.jsonl  older messages, by the month of the message
  agents/<Name>.json     one file per agent
  agents/archive/        agents that have been `done` for 7 days
  .lock                  flock target for writes, archiving and name creation
  .last-gc               date of the last automatic archive run
```

**Message**
```json
{"id": "20260928T101312-7f3a", "ts": "2026-09-28T10:13:12+02:00",
 "from": "Reiger", "task": "2026-09-28-samenwerkingsregel", "to": "all",
 "kind": "DECISION", "body": "…", "reply_to": null}
```
- `kind` ∈ `INFO QUESTION ANSWER CLAIM RELEASE BLOCKED DECISION DONE GUARD`.
  `GUARD` is written only by the guard.
- `to` is an agent name, `all`, or `human`.
- `id` = UTC timestamp + 4 random hex characters; `reply_to` references an `id`.
- Unknown fields are preserved on read, so later versions can add fields.

**Agent**
```json
{"name": "Reiger", "task": "2026-09-28-samenwerkingsregel", "goal": "…",
 "session": "erppoc-mainmerge-89", "worktree": "/home/qsmits/erppoc-mainmerge",
 "branch": "merge/2026-09-23", "status": "active",
 "started": "…", "last_seen": "…",
 "claims": [{"pattern": "backend/src/modules/document/document.service.ts",
             "reason": "CAS in update()", "since": "…"}],
 "touches": ["backend/src/modules/accounting/services/verkoopfacturen.service.ts"]}
```
- `name` matches `^[A-Za-z][A-Za-z0-9_-]{1,31}$`. Creation uses `O_EXCL` under the lock,
  so exactly one of two agents choosing the same name wins.
- `status` ∈ `active waiting done`. `done` clears `claims`.
- Writes to an agent file go to a temp file plus `rename`, so a reader never sees half a
  file.

**Writes.** Every append to `channel.jsonl` holds an exclusive `flock` on `.lock` and
writes one line with a single `write()` call.

**Retention.** On the first write or session start of a day (`.last-gc`), under the lock:
messages older than 14 days move to `archive/YYYY-MM.jsonl`, and agent files with status
`done` untouched for 7 days move to `agents/archive/`. Nothing is deleted.

## 7. Claims and TTL

- A claim is a glob pattern relative to the repository root. It supports `*`, `**` and
  `?`, with `fnmatch` semantics extended so that `**` spans directories.
- A claim is **live** while `now < last_seen + TTL` and the agent is not `done`.
  TTL defaults to 4 hours and is configurable per repository via
  `git config agent-channel.ttl`.
- `last_seen` is refreshed by every `agent-channel` command the agent runs, and by a commit
  that the agent makes as itself (`AGENT_CHANNEL_AS`). A working agent keeps its claims;
  a crashed session loses them within the TTL, without anyone having to decide.
- `claim` checks for conflicts before claiming. Two patterns conflict when either matches
  the other's literal prefix, or when a concrete path would match both. On conflict it
  exits 3, prints the owner, the owner's session and the expiry, and claims nothing.
- An agent whose `last_seen` is older than 2 hours but whose claims are still live is shown
  as `quiet`.

## 8. CLI

The agent names itself on every call; a shell variable would not persist between an
agent's commands. Output is plain and stable. Every read command supports `--json`.

| Command | Behaviour |
|---|---|
| `join <Name> --task <slug> --goal "…" [--session <s>]` | Create the identity. Worktree and branch are detected. Exit 2 if the name is taken. |
| `status <Name> active\|waiting\|done` | Set status. `done` releases all claims and posts `DONE`. |
| `claim <Name> <pattern>… [--reason …]` | Conflict check first. On success, post `CLAIM`. |
| `release <Name> [<pattern>…\|--all]` | Release, post `RELEASE`. |
| `touch <Name> <pattern>…` | Record read interest. No lock, no guard effect. |
| `check <path>…` | Print live claims matching each path. Exit 3 if any are held by someone else. |
| `say <Name> <to> <KIND> <body\|->  [--reply-to <id>]` | Post a message. `-` reads the body from stdin. |
| `read [-n N] [--follow] [--kind K] [--grep T] [--all] [--json]` | Read messages. `--all` includes the archive. |
| `who [--json]` | Agents, status, live claims, expiries. |
| `decisions [T]` | All `DECISION` messages, archive included. |
| `watch` | Live dashboard (§11). |
| `gc` | Run retention now. |
| `install-guard` | Install the pre-commit guard (§9). |
| `hook session-start` | SessionStart output (§10). Reads the hook JSON from stdin. |
| `hook pre-commit` | Guard entry point. |
| `import-legacy <dir>` | Convert a `samenwerken` folder (§13). |

Exit codes: `0` ok, `1` error, `2` usage or name taken, `3` claim conflict.

## 9. Commit guard

**Install.** `install-guard` finds the hooks directory: `core.hooksPath` if it is set,
otherwise `<common-dir>/hooks`. It adds a delimited block
(`# >>> agent-channel >>>` … `# <<< agent-channel <<<`) to an existing `pre-commit`, or
creates one. It never overwrites other content. Running it again is a no-op. The block
calls the tool by absolute path.

**Check.**
1. No channel in this repository: exit 0 silently.
2. Collect the staged paths from `git diff --cached --name-status -M`, counting both sides
   of a rename.
3. For each path, find live claims held by agents other than `$AGENT_CHANNEL_AS`.
4. No conflicts: exit 0. If `$AGENT_CHANNEL_AS` names a known agent, refresh its
   `last_seen`.
5. Conflicts and `$AGENT_CHANNEL_OVERRIDE` is set: post a `GUARD` message (committer
   name, or `unknown`; paths; owners; the given reason) and exit 0.
6. Conflicts without an override: print each path, its owner, the pattern, the expiry,
   and how to reach the owner (`agent-channel say …` or `SendMessage` to `<session>`).
   Post a `GUARD` message recording the block, and exit 1.
7. Any internal exception: print a one-line warning to stderr and exit 0.

## 10. SessionStart hook

The plugin registers `hook session-start`. It prints nothing unless the current directory
is inside a git repository that has a channel. The output is at most **2400 bytes** and is
filled in priority order until the budget runs out:

1. Two lines: what this is, and the absolute path of the CLI (the hook knows its plugin
   root), so the agent needs nothing on `PATH`.
2. One line per non-`done` agent: name, status, task, claim count, next expiry. At most 8,
   then `+N more`.
3. `DECISION` messages from the last 7 days, 160 characters each.
4. The latest messages, 200 characters each.
5. A pointer to `who` and `read` for the full picture.

## 11. `watch`

A read-only curses dashboard with three panes: agents (status markers for
active/waiting/quiet), live claims with time to expiry, and the message stream. `GUARD`
events are highlighted. It polls the files every second. Keys: arrows to scroll, enter to
expand a message, `b` for decisions only, `/` to search, `q` to quit. It has no compose
action: the human instructs agents in their own sessions, which keeps authority
unambiguous. The layout is computed by `render.py`, so the curses layer only paints.

## 12. Distribution

- **Claude Code plugin.** `.claude-plugin/plugin.json` and `marketplace.json`, installed
  with `/plugin marketplace add Exp2red/agent-channel`. The plugin ships the skill
  (`skills/agent-channel/SKILL.md`), the SessionStart hook (`hooks/hooks.json`) and
  `bin/agent-channel`.
- **pipx.** `pyproject.toml` defines an `agent-channel` console script for humans and for
  the git hook.
- **License:** MIT.
- **Documentation:**
  - README: the problem, a 60-second quickstart, a GIF of `watch`, the inspiration (§3),
    and an honest comparison with MCP Agent Mail and agent-comms. This project is smaller,
    has no server and is scoped to one repository by construction.
  - SECURITY.md: §4.
  - CHANGELOG.md.

## 13. Migration from `samenwerken`

`import-legacy /home/qsmits/erppoc-samenwerking` converts the old channel into the ERPPOC
repository's new channel:

- Messages are parsed from the `── date · Name (task) → To · KIND` header format.
  `BESLUIT` becomes `DECISION`, `VRAAG` becomes `QUESTION`, and so on. Bodies are kept
  verbatim.
- Agent text files become JSON. `Status: actief/wacht/klaar` becomes
  `active/waiting/done`.
- It is idempotent: a message whose `(ts, from, body)` already exists is skipped.

Afterwards, removed with the user's confirmation:
- `~/.claude/skills/samenwerken`
- the SessionStart hook entry in `~/.claude/settings.json`
- the old folder

The active agents receive one `INFO` message with the new commands.

## 14. Testing

Every test runs against a real temporary git repository, with worktrees where relevant.
Git is not mocked.

- **Concurrency:** 20 processes append at once, giving 20 valid lines. Two processes `join`
  with the same name: exactly one succeeds.
- **Scoping:** two worktrees see one channel; another repository sees none; a symlinked
  channel dir pointing outside is refused.
- **Claims:** glob conflicts, TTL expiry and refresh under a frozen clock, `done` releases.
- **Guard:** blocked; override passes and logs; owner passes and refreshes; expired claim
  passes; no channel passes; rename checks both sides; an injected exception fails open;
  install is idempotent and preserves existing hook content.
- **Retention:** rollover across a month boundary under a frozen clock; nothing is lost.
- **Hook:** with 30 agents and 500 messages the output stays ≤ 2400 bytes; empty output
  outside a repository with a channel.
- **Render:** snapshot tests of the dashboard layout at 80 and 120 columns.
- **Legacy import:** a fixture copied from the real prototype folder; idempotent re-run.
- **CI:** GitHub Actions, Python 3.9–3.13, on ubuntu-latest and macos-latest.

## 15. Decisions

| # | Decision | Source |
|---|---|---|
| 1 | English throughout | user, 2026-09-28 |
| 2 | Channel per git repository, found automatically, not globally discoverable | user, 2026-09-28 (security concern from the OpenAI/Hugging Face incident) |
| 3 | Guard blocks, with a logged override | user, 2026-09-28 |
| 4 | Plugin + stdlib Python CLI (not bash, not an MCP server) | user chose approach A, 2026-09-28 |
| 5 | CLI for agents + read-only curses `watch` for humans; no local web server | user, 2026-09-28 |
| 6 | TTL claims as heartbeat; hook budget 2400 bytes | market reference: MCP Agent Mail (TTL leases, pre-commit guard); multi-agent-coordination-skill (2400-byte cold-start budget) |
| 7 | Guard fails open on internal errors | INFERRED: accident-prevention tool must not become a single point of failure for commits |

## 16. Open questions

1. ~~GitHub owner~~ — resolved 2026-09-28: the user's personal account, public from day one.
2. ~~Plugin `bin/` on PATH~~ — resolved 2026-09-28: Claude Code adds a plugin's `bin/` to the
   Bash tool's PATH while the plugin is enabled
   ([manifest reference](https://code.claude.com/docs/en/plugins/manifest-reference.md#standard-layout)).
   Agents call `agent-channel` by name; the hook still prints the absolute path as a fallback.
