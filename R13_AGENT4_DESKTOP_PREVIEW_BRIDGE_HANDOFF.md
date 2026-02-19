# Subagent Handoff Template

## Lane Info

- Round: `R13`
- Lane: `desktop-preview-bridge`
- Branch: `codex/r13-desktop-preview-bridge`
- Worktree: `/tmp/miflatform-r13-desktop-preview-bridge`

## Summary

- Implemented:
- Added desktop preview bridge runtime module at `src/migrator/desktop_preview_bridge.py`.
- Implemented preview-host process manager lifecycle from desktop side: start/stop/health-check with timeout + log-tail diagnostics.
- Implemented run-output aware preview-host directory resolution via `*.migration-summary.json` (`stages.sync_preview.manifest_file`) and explicit run preview host directory override.
- Implemented selected `screenId` preview open flow with manifest-driven validation (no sample hardcoding).
- Implemented optional embedded WebView path (`PySide6.QtWebEngineWidgets`) with external browser fallback.
- Added unit tests for lifecycle, summary resolution, screen route open, and embedded fallback behavior.
- Added documentation for bridge behavior + failure handling (`docs/DESKTOP_PREVIEW_BRIDGE.md`) and linked docs/user-facing references.
- Not implemented:
- UI wiring inside concrete PySide6 window controls from `desktop-shell-foundation` lane (intentionally left for merge integration point).

## Changed Files

- `src/migrator/desktop_preview_bridge.py`
- `tests/test_desktop_preview_bridge.py`
- `src/migrator/__init__.py`
- `docs/DESKTOP_PREVIEW_BRIDGE.md`
- `docs/INDEX.md`
- `README.md`
- `USER_MANUAL.md`

## Commands Run

- `python3 -m unittest -v tests.test_desktop_preview_bridge`
- Result:
- PASS (9 tests)

- `python3 -m unittest -v tests.test_cli`
- Result:
- PASS (16 tests)

- `cd preview-host && npm run build`
- Result:
- FAIL (initial): `sh: tsc: command not found`

- `cd preview-host && npm install`
- Result:
- PASS

- `cd preview-host && npm run build`
- Result:
- PASS (`vite build` completed)

## Validation Status

- Required checks passed:
- `cd preview-host && npm run build` (after installing dependencies)
- Required checks failed:
- None (final state)

## Open Risks / Follow-Ups

- `desktop-shell-foundation` lane merge가 완료되기 전까지 본 브리지 모듈은 독립 유틸 계층이며, 실제 PySide6 버튼/뷰 이벤트 연결은 후속 통합 커밋에서 연결 필요.
- preview-host dev server 포트(`4173` 기본)가 점유된 환경에서는 `PreviewHostProcessError`가 발생할 수 있으므로 데스크톱 설정 UI에서 포트 오버라이드 노출 권장.
- embedded WebView는 `PySide6.QtWebEngineWidgets`가 설치된 환경에서만 활성화되며, 미설치 환경은 외부 브라우저 fallback 동작이 정상 경로임.

## Merge Notes for PM

- Safe merge order suggestion:
- `desktop-shell-foundation` -> `runner-service-refactor` -> `desktop-preview-bridge` (또는 `desktop-preview-bridge` 병합 후 shell 이벤트 wiring만 후속 조정)
- Conflict-prone files:
- `README.md`
- `USER_MANUAL.md`
- `src/migrator/__init__.py`
