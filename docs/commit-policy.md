# Commit Policy

## Purpose

Этот документ фиксирует правила финального git handoff для swarm-run.

## Approval Rules

- `commit` и `push` должны запрашиваться отдельно.
- `push`, tag, release и другие необратимые git-операции запрещены без отдельного явного approval пользователя.
- Approval на `commit` не означает approval на `push`.

## What To Show Before Approval

Перед финальным handoff пользователю нужно показать:

- цель изменения;
- какие файлы были использованы как контекст;
- какие файлы были реально изменены;
- какие проверки были проведены и где именно;
- какие residual risks остались;
- какой commit message предлагается.

## Approval Packet

Approval packet должен по возможности ссылаться на:

- `context-summary.md`
- `changed-files.json`
- `verification-result.json`
- `sandbox-result.json`
- `review-result.json`
- `workspace-diff.patch`

## Git Boundaries

- Агент не должен молча объединять `commit` и `push` в одну операцию.
- Если run дошел только до `commit`, решение о `push` остается отдельным шагом.
- Если для `push` нужно повышение прав или внешняя сеть, approval запрашивается непосредственно перед этой операцией.

## Related Docs

- `AGENTS.md`
- `docs/SECURITY.md`
- `docs/swarm-usage.md`
