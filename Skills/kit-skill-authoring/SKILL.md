---
name: kit-skill-authoring
description: Create, split, review, or refactor repository skills shared by Codex and Claude Code. Use when changing Skills/*/SKILL.md, trigger descriptions, bundled resources, or agents/openai.yaml. Do not use for AGENTS.md wiring.
---

# Skill Authoring

Create focused skills that activate only for intended tasks, consume little context, and give the
agent direction rather than a script. Wiring belongs to `$kit-agent-rules`.

## Package

- `Skills/<skill-name>/SKILL.md`; the lowercase hyphenated directory matches the frontmatter `name`
  (at most 64 characters). Codex and Claude Code read the same files through the `.agents/skills`
  and `.claude/skills` symlinks, so write for any capable agent, not for one tool.
- Frontmatter holds `name` and `description`. A user-gated skill says so in `description`, sets
  `disable-model-invocation: true` in the frontmatter (Claude Code) and
  `policy.allow_implicit_invocation: false` in `agents/openai.yaml` (Codex).
- `agents/openai.yaml` is optional Codex UI metadata: `display_name`, `short_description`, and a
  `default_prompt` that mentions `$skill-name`.
- `$skill-name` is the reference syntax for a skill in any text, not an invocation command.
- No secrets, absolute or private paths, or claims about unavailable capabilities.
- Stay well under 200 lines; the shortest complete skill wins.

## Content

- **Description** decides activation and is paid for on every request: the job and the project
  nouns first, then exact `Use when ...` and `Do not use ...` boundaries.
- **Body:** purpose, owned area, the guardrails that are actually hard, useful sources, and checks
  specific to this work. Link to canonical owners instead of copying them.
- Leave research approach and reply shape to the agent: no output contracts, mandatory headings, or
  step lists unless the order itself is the safety property or the output is machine-read.
- One coherent job or risk class per skill; split only when triggers, risks, or checks differ.
  Conditional detail goes to one-level `references/`, deterministic logic to `scripts/` with
  explicit inputs, no hidden network calls, and actionable non-zero failures.
- Do not create skills for generic reasoning, planning, or mandatory task stages; keep a skill only
  when it adds project knowledge or tools beyond ordinary agent abilities.

## Shared and project skills

Shared `kit-` skills hold reusable procedures and no project names, paths, or domain rules. Project
skills use the project prefix (`<project>-<job>`), supply local context, and refer to shared skills
instead of copying them.

## Best practices

Consult when a format or design question needs it, not on every task:

- [Agent Skills specification](https://agentskills.io/specification)
- [Best practices for skill creators](https://agentskills.io/skill-creation/best-practices)
- [Claude skill authoring best practices](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/best-practices)
- [Claude Code skills](https://docs.claude.com/en/docs/claude-code/skills)
- [Codex skills](https://developers.openai.com/codex/skills)
- Example skills: [anthropics/skills](https://github.com/anthropics/skills),
  [openai/skills](https://github.com/openai/skills)

External examples are guidance, not extra workflow requirements.

## Check

Sanity-check activation against a few prompts that should and should not trigger the skill, and
against adjacent skills.
