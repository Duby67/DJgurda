# External Dependency Resilience

## Status

- Completed on 2026-03-24.

## Outcome

- В `HandlerRegistry` появился явный `SourceResilienceProfile` для всех stable sources, поэтому dependency surfaces, timeout expectations, retry posture и degrade signals теперь зафиксированы в tracked code metadata.
- `VK` остался вне stable runtime resilience contract и по-прежнему удерживается как отдельный R&D track, а не как обычный stabilization target.
- `docs/RELIABILITY.md` и `docs/design-docs/runtime-pipeline.md` теперь описывают тот же resilience posture, что и код, без скрытого tribal knowledge.
- Новый focused test закрепляет, что stable runtime sources обязаны иметь непустой resilience profile и что ключевые degrade signals остаются явной частью контракта.

## Verification

- `.\venv\Scripts\python.exe -m pytest test/handlers/test_registry_resilience_profiles.py -q`
- `.\venv\Scripts\python.exe -m pytest test/bot/processing -q test/handlers/test_cleanup_helpers.py`
- Result: `17 passed`

## Notes

- Repo-local swarm run `20260324-141720-swarm` доведён до coder/tester artifacts и опять упёрся только в infra-level `sandbox_blocked` на `docker`.
- Изменение намеренно осталось bounded: мы зафиксировали resilience contract и observability vocabulary, но не строили новый metrics subsystem и не переписывали все source handlers сразу.
