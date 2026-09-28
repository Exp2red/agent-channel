# Security model

agent-channel coordinates cooperative agents. It is not an access-control system.

## What it guarantees

- **No new reach.** The channel lives in `$(git rev-parse --git-common-dir)/agent-channel`.
  Reading or writing it requires access to the repository's git directory, which an agent
  working in that repository already has. The path is fixed: there is no option or
  environment variable to point the tool elsewhere, and a symlinked channel or
  sub-directory is refused.
- **No global discovery.** No command lists channels of other repositories.
- **Messages are data.** Bodies are limited to 4000 characters and are never executed,
  evaluated or interpolated into commands.
- **Never committed.** The channel is inside `.git/`.
- **Every override leaves a record.** A commit that passes the guard with
  `AGENT_CHANNEL_OVERRIDE` writes a `GUARD` message naming the paths, owners and reason.

## What it does not guarantee

- **Identity is self-declared.** Every agent commits as the same git user and can name
  itself anything. `AGENT_CHANNEL_AS` is a declaration, not authentication.
- **The guard can be bypassed** with `AGENT_CHANNEL_OVERRIDE` (recorded) or
  `git commit --no-verify` (not recorded). It prevents accidents between cooperating
  agents; it does not stop a deceptive one.
- **The guard fails open.** An internal error lets the commit through with a warning, so a
  bug in this tool cannot block a repository.

## Why scope matters

In July 2026 OpenAI disclosed that agents in an evaluation run coordinated through
channels nobody gave them (see the README). A coordination channel that is global to a
machine would be exactly such a side channel, handed over deliberately. Scoping it to one
repository keeps the channel from adding reach.

## Reporting

Open a GitHub issue, or for anything sensitive, contact the maintainer through the email
on their GitHub profile.
