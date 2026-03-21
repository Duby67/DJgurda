# Security

## Purpose

This file captures security, secret-handling, and approval boundaries for the repository.

## Secret Rules

- Secrets must not be committed to tracked files.
- `local/` may contain sensitive or stale material and is not a tracked policy source.
- Deploy-side secret materialization must stay separate from tracked source files.
- Cookie files are operational artifacts, not repository knowledge documents.

## Access Rules

- Remote server access is a human-only operation unless an explicitly approved safe workflow exists.
- Agents should not perform SSH, RDP, WinRM, or ad hoc remote shell actions.
- Approval is required before `push`, release, tag creation, or infrastructure-changing actions.

## Repository Hygiene

- Prefer UTF-8 without BOM for tracked files.
- Treat `.env`, `venv/`, caches, and other local environment artifacts as non-canonical.
- Keep tracked docs free from copied secrets, local paths that reveal credentials, or deploy-only values.
