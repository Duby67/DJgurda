# URL Extraction And Routing Robustness

## Status

- Completed on 2026-03-24.

## Outcome

- `split_into_blocks()` теперь отделяет хвостовую пунктуацию от extracted URL и сохраняет suffix в surrounding context.
- `resolve_url()` теперь нормализует URL и fallback-path, чтобы punctuation noise не переживал resolve stage.
- `media_router` получил bounded-parallel preflight для multi-link batches с сохранением исходного порядка блоков и graceful fallback при resolver exceptions.

## Verification

- `.\venv\Scripts\python.exe -m pytest test/bot/processing/test_media_router_multi_link.py test/bot/processing/test_media_processor_errors.py test/handlers/test_cleanup_helpers.py -q`
- Result: `11 passed`

## Notes

- Repo-local swarm run `20260324-130030-swarm` был доведён до coder/tester artifacts и упёрся только в infra-level `docker_version_probe_failed`.
- Кодовые изменения и targeted verification в основной ветке завершены успешно; blocker остался только на sandbox adapter availability, а не на correctness change-set.
