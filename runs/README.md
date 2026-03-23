# Runs

Эта папка хранит локальные swarm run artifacts:

- `run-summary.json`
- `plan.json`
- `context-pack.json`
- verification, review, approval и другие lifecycle-артефакты

Назначение папки:

- держать run bundles как отдельный операционный слой в корне репозитория;
- сохранять историю локальных запусков для orchestration и debugging;
- не смешивать run artifacts с policy-документами и source of truth.

Правила:

- содержимое папки не коммитится в git;
- в репозитории сохраняется только этот файл;
- каждый отдельный run должен жить в своей подпапке внутри `runs/`.
