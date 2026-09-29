---
name: kit-docs
description: Synchronize human-facing Markdown with behavior verified in code, tests, configuration, or workflows. Use when editing README.md or other human documentation. Do not use for AGENTS.md or skills.
---

# Documentation

Keep human documentation true to current behavior, concise, and with each fact in exactly one
canonical owner.

- Confirm a claim from the smallest source that proves it: code, tests, configuration, or
  workflows. A backlog is never a behavior source.
- Update the owner and only the links or one-line summaries that point to it.
- Document stable contracts; details that change often are proven by code and tests, not prose.
- Remove rollout- or migration-specific instructions once the cutover is confirmed; Git keeps the
  history.
- If the text exposes a defect in code or configuration, report it; fix it only within the
  authorized scope.
- Do not copy secrets or real identifiers, keep historical drafts, or change code to match text.

Check that every link and referenced path in the edited files resolves.
