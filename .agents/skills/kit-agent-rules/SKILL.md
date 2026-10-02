---
name: kit-agent-rules
description: Keep AGENTS.md minimal and consistent with the repository skills and docs. Use when changing AGENTS.md or CLAUDE.md, or wiring a skill addition, rename, split, or removal into the repository. Do not use for writing skill content or human-facing documentation.
---

# Agent Rules

`AGENTS.md` is read on every model request, so every line costs tokens on every task. Skill content
quality belongs to `$kit-skill-authoring`.

## Wiring

- `AGENTS.md` is the single rules file. Codex reads it natively; `CLAUDE.md` holds one line,
  `@AGENTS.md`, so Claude Code imports the same file.
- `.agents/skills/` is the only skill source; Codex reads it natively. `.claude/skills` (Claude Code)
  is a relative symlink to it and never holds files of its own.
- Both clients discover skills from their `description` fields; a routing table in `AGENTS.md` is
  not needed and duplicates those descriptions.
- `.agents/handoff.md` and `.agents/tasks.md` are local, git-ignored session files.

## What belongs in AGENTS.md

Keep only what every task needs and the agent cannot infer:

- one or two sentences on what the project is and is not;
- hard invariants whose violation is costly (data, money, security, privacy, protected branches);
- pointers to canonical owners the agent would not find on its own.

Remove or move out:

- statements the file already implies ("this file is for agents", "write this file in English");
- general engineering advice any capable agent already follows;
- task-specific procedures (move to a skill) and human-facing explanations (move to docs);
- copies of facts owned elsewhere (link instead);
- examples, history, and rationale that do not change behavior.

State hard rules imperatively; give soft guidance as direction, not an algorithm. A skill rename,
split, or removal updates `.agents/skills/` and every reference in one change, without aliases.

## Check

Re-read the diff and ask for each added line whether an agent would act differently without it; if
not, delete it. Verify that the symlinks resolve and that referenced paths exist.
