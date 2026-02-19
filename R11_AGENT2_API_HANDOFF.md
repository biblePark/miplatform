# R11 Agent-2 API Handoff

## 1) 구현 내용

- 로컬 Orchestrator API 계층 추가 (`src/migrator/orchestrator_api.py`)
  - `POST /jobs`
  - `GET /jobs/{id}`
  - `GET /jobs/{id}/logs`
  - `GET /jobs/{id}/artifacts`
  - `GET /health`
- 비동기 job 실행 모델 구현
  - in-memory job store + background worker queue
  - 상태 모델: `queued`, `running`, `succeeded`, `failed`, `canceled`
- 구조화된 에러 응답 구현
  - 공통 형태: `error.code`, `error.message`, `error.details`
- 기존 파이프라인 재사용 보장
  - API job 실행 시 `run_migrate_e2e(...)` 직접 호출
  - 내부적으로 `parse -> map-api -> gen-ui -> fidelity-audit -> sync-preview -> preview-smoke` 순서 사용
- API 단위 테스트 추가 (`tests/test_orchestrator_api.py`)
  - 정상/실패 job, health, 구조화 에러, logs/artifacts 검증
- 문서화
  - `docs/ORCHESTRATOR_API.md` 신규 작성
  - `README.md`, `docs/INDEX.md`, `pyproject.toml` 업데이트

## 2) 수정 파일 목록

- `/Users/biblepark/Desktop/works/miflatform-migrator/src/migrator/orchestrator_api.py` (new)
- `/Users/biblepark/Desktop/works/miflatform-migrator/tests/test_orchestrator_api.py` (new)
- `/Users/biblepark/Desktop/works/miflatform-migrator/docs/ORCHESTRATOR_API.md` (new)
- `/Users/biblepark/Desktop/works/miflatform-migrator/pyproject.toml`
- `/Users/biblepark/Desktop/works/miflatform-migrator/README.md`
- `/Users/biblepark/Desktop/works/miflatform-migrator/docs/INDEX.md`

## 3) 실행 테스트/결과

- `python3 -m unittest tests.test_orchestrator_api -v`
  - 결과: Passed (`Ran 4 tests`, `OK`)
- `python3 -m unittest tests.test_cli tests.test_orchestrator_api -v`
  - 결과: Passed (`Ran 20 tests`, `OK`)
- `python3 -m unittest discover -s tests -p 'test_*.py' -v`
  - 결과: Failed (`tests/test_report_view.py::test_view_text_for_migration_summary_and_prototype_acceptance`)
  - 비고: Agent-2 변경 범위 외 기존 실패로 확인됨 (단독 재실행에서도 동일 실패)

## 4) 리스크/후속 제안

- 현재 job 저장소는 메모리 기반이므로 프로세스 재시작 시 job 이력 유실.
- `canceled` 상태 모델은 포함되지만 cancel endpoint는 이번 필수 범위에 없어서 외부 트리거는 미구현.
- 단일 worker queue 구조라 동시 대량 요청 시 처리량 제한 가능성 있음.
- 후속 라운드에서 필요 시:
  - `DELETE /jobs/{id}` 또는 `POST /jobs/{id}/cancel` 추가
  - 영속 job store(예: sqlite) 및 재시작 복구
  - 멀티 워커/동시성 정책(최대 동시 실행 수) 구성화
