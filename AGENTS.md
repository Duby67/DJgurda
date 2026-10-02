# Agents

## Project

DJgurda is a Telegram bot being rewritten to transfer media from links into chats.
Scope and branch lifecycle are defined in [README.md](README.md).

## Rules

Hard rules; stop and report instead of working around them.

- **Keep this file minimal.** It is loaded on every request. Add only rules every task needs; move
  task-specific detail to a skill or a doc and link to it. Never add text the agent already knows,
  text implied by the file itself (its audience, purpose, or language), or copies of other files.
- **Branch isolation:** new branch from `development`. Never work or
  commit directly on `development` or `main`; changes enter these branches through pull requests.
- **Commits** only with the user's explicit permission for that change.
- **No silent fallback:** fail with an actionable error instead of substituting a default.
- **Secrets** come from the environment; never commit them or put them in logs, reports, or session
  files.
- **Honest evidence:** never report an unrun or skipped check as passed; completion needs checks run
  after the last change.
- **Small VM first:** optimize for bounded memory, CPU, disk usage, and concurrency. Give
  production priority; keep development lightweight and stop it when unused. Build images off
  the server. Resource budgets and deployment instructions live in `docs/DEPLOYMENT.md`.
- **No heavy local builds:** ask before building a large image or one that downloads during the
  build. Never build `deploy/bot-api/Dockerfile` locally: it crashes WSL; CI builds it.
- **Focused tests:** prefer a few tests of meaningful behavior and real regressions. Avoid
  repetitive micro-cases, implementation-mirroring, and raise coverage tests.

When docs, config, code, and tests disagree, report the contradiction instead of choosing.

## Work

Trace the real flow, then make the smallest correct change. Prefer, in order: no change, existing
code, the standard library, an installed dependency, new code. Stay in scope. Read narrowly:
focused search, bounded reads, `git diff --stat` before diffs, quiet test output.

## Report

One line per point: result, checks actually run with outcome, concrete risks. Omit empty
categories; never list what was not done.
