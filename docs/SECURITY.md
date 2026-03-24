# Security

## Purpose

Этот файл фиксирует security-, secret-handling- и approval-границы репозитория.

## Secret Rules

- Секреты не должны попадать в tracked-файлы.
- Untracked legacy/archive материалы могут содержать чувствительные или устаревшие данные и не являются tracked policy source.
- Deploy-side materialization секретов должна быть отделена от tracked source files.
- Cookie-файлы - это operational artifacts, а не knowledge-documents репозитория.

## Access Rules

- Удаленный доступ к серверу остается действием человека, если только не существует явно одобренный безопасный workflow.
- Агентам нельзя выполнять SSH, RDP, WinRM или ad hoc remote shell действия.
- Approval обязателен перед `push`, release, созданием tag и инфраструктурными изменениями.

## Repository Hygiene

- Для tracked-файлов предпочитать UTF-8 без BOM.
- `.env`, `venv/`, caches и другие локальные environment artifacts считать неканоничными.
- Не допускать, чтобы в tracked docs попадали секреты, чувствительные локальные пути или deploy-only значения.
