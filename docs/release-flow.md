# Release Flow

## Purpose

Этот документ кратко описывает, как продвигать код в вышестоящие ветки и какие версии при этом формируются.

Использовать его стоит как human-facing памятку для разработчика. Каноническая логика automation живет в:

- `scripts/release/automation/promote.py`
- `scripts/release/automation/sync.py`
- `scripts/release/rules/versioning.py`
- `.github/workflows/release-promote.yml`
- `scripts/AGENTS.md`
- `docs/release-promote-examples.md`

Канонический локальный запуск теперь делается через module-path:

- `python -m scripts.release.automation.promote`
- `python -m scripts.release.automation.sync`

## Branch Roles

- `swarm-dev` и другие feature-ветки: обычная разработка и локальная отладка
- `dev`: preview-ветка для промежуточных версий и проверки на dev-боте
- `main`: stable release-ветка для production

Поднятие кода в вышестоящую ветку выполняется только по явному запросу разработчика через ручной workflow.

## Preview Promotion

Типовой сценарий preview promotion:

- источник: feature-ветка, например `swarm-dev`
- цель: `dev`
- результат: preview tag и preview версия в `src/__init__.py`

Правила versioning:

- если `main` сейчас на `v1.2.4`, а preview-цикл для следующей версии еще не начат, promotion в `dev` создаст `v1.2.5_a`
- если `dev` уже находится на `v1.2.5_a`, следующий promotion создаст `v1.2.5_b`
- если `dev` уже находится на `v1.2.5_c`, следующий promotion создаст `v1.2.5_d`

То есть `dev` всегда двигается в пределах следующей stable версии после `main`.

## Stable Promotion

Типовой сценарий stable promotion:

- источник: `dev`
- цель: `main`
- результат: stable tag и stable версия в `src/__init__.py`

Правила versioning:

- если `dev` находится на `v1.2.5_c`, promotion в `main` создаст `v1.2.5`
- буквенный preview suffix отбрасывается
- если stable release идет напрямую не из `dev`, automation помечает это как нежелательный сценарий warning-ами

## Version Rules

Базовые правила bump:

- `v1.2.3 -> v1.2.4`
- `v1.2.9 -> v1.3.0`

Базовые правила preview suffix:

- `v1.2.5_a -> v1.2.5_b`
- `v1.2.5_z -> v1.2.5_aa`

## Manual Workflow

Для promotion используется ручной workflow:

- `.github/workflows/release-promote.yml`

Он всегда сначала строит dry-run план, а реальное выполнение merge/version bump/tag/push делает только при `execute=true`.

Если нужен сетевой `push`, он включается отдельно через `push=true`.

Dry-run plan теперь также показывает `execution preflight` для execute-стадии.
Этот preflight проверяет чистоту рабочего дерева, наличие нужных refs, возможность fast-forward целевой ветки до remote, то что source все еще опережает remote target, и что запланированный release tag не успел устареть относительно текущего remote state.

## Recommended Modes

В workflow есть типовые режимы запуска:

- `feature_to_dev_preview`: обычное продвижение feature-ветки в `dev`
- `dev_to_main_release`: выпуск проверенной preview-версии из `dev` в `main`
- `direct_to_main_release`: прямой stable release в `main`, допустимый, но нежелательный
- `custom`: ручная настройка для нетиповых сценариев

Эти режимы нужны как подсказки и guardrails:

- чтобы не ошибиться целевой веткой
- чтобы workflow сам подставлял ожидаемый `target_kind`
- чтобы типовой путь был быстрее ручного ввода параметров

## Typical Process

Обычный путь до production выглядит так:

1. Разработка идет в feature-ветке, например `swarm-dev`.
2. По явному запросу запускается preview promotion в `dev`.
3. Dev-бот проверяется на версии вида `v1.2.5_a`, `v1.2.5_b` и так далее.
4. Когда preview-версия подтверждена, по явному запросу запускается stable promotion из `dev` в `main`.
5. В `main` появляется stable version/tag без suffix, например `v1.2.5`.

## Safety Notes

- Workflow не обязан выполнять promotion автоматически по push.
- Dry-run можно запускать сколько угодно раз для проверки плана.
- Merge в `main` из feature-ветки допустим, но должен рассматриваться как осознанное исключение.
