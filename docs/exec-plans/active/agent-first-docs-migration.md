# Agent-First Docs Migration

## Goal

Move repository context from a few overloaded files into a small set of focused, agent-friendly documents.

## Scope

- create the new document structure;
- split old context by topic;
- archive replaced context files under `local/`;
- keep the new top-level reading path short and predictable.

## Current Sources Being Migrated

- `README.md`
- `.github/ai-context.md`
- `.github/ai-agent-technical-task.md`
- `docs/documentation-sources.md`
- `docs/repository-root-map.md`
- `docs/deploy_layout.md`
- `docs/improvements.md`
- `local/REFACTORING.md`

## Success Criteria

- agents can find architecture, product, reliability, security, and plan context without reading large mixed files;
- legacy context files are no longer the primary source of truth;
- the repository has a clear reading order from root policies to module-specific context.
