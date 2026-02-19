# R12_AGENT1_API_HANDOFF

## 1) 구현 내용
- `POST /jobs/{id}/cancel` endpoint를 추가했습니다.
  - `queued` 상태는 즉시 `canceled` 전이
  - `running` 상태는 `cancel_requested=true`로 마킹 후 안전 지점에서 `canceled` 전이
  - 이미 terminal(`succeeded/failed/canceled`)이면 현재 상태 반환
- `GET /jobs` 목록 조회 endpoint를 추가했습니다.
  - `limit`(양의 정수) 필터 지원
  - `status`(단일/콤마 구분 복수) 필터 지원
  - 최신 생성 순(reverse chronological) 반환
- Job store 파일 영속화를 추가했습니다.
  - 기본 저장 경로: `<workspace-root>/out/orchestrator/jobs.json`
  - 서버 재기동 시 store 로드 후 기존 이력 조회 가능 (`GET /jobs`, `GET /jobs/{id}`)
  - 재기동 시점 non-terminal job은 `job_incomplete_after_restart`로 failed 전환
- 기존 구조화 에러 계약(`error.code/message/details`)을 유지했습니다.
- CLI 옵션 동기화를 위해 orchestrator request에 `auto_risk_threshold` 전달을 추가했습니다.

## 2) 수정 파일 목록
- `/Users/biblepark/Desktop/works/miflatform-migrator/src/migrator/orchestrator_api.py`
- `/Users/biblepark/Desktop/works/miflatform-migrator/tests/test_orchestrator_api.py`
- `/Users/biblepark/Desktop/works/miflatform-migrator/docs/ORCHESTRATOR_API.md`
- `/Users/biblepark/Desktop/works/miflatform-migrator/R12_AGENT1_API_HANDOFF.md`

## 3) 실행 테스트/결과
- 실행 명령:
  - `python3 -m py_compile src/migrator/orchestrator_api.py tests/test_orchestrator_api.py`
  - `python3 -m unittest -q tests.test_orchestrator_api`
- 결과:
  - `Ran 7 tests in 4.847s`
  - `OK`

## 4) 리스크/후속 제안
- 현재 cancel은 cooperative cancellation입니다. 이미 실행 중인 `run_migrate_e2e` 프로세스를 강제 중단하지 않고, 완료 후 `canceled`로 마감합니다.
- Job store는 단일 JSON 파일이므로 장기 운영 시 파일 크기 증가 가능성이 있습니다. 보관 기간/개수 기반 trim 정책을 후속으로 권장합니다.
- store 쓰기 실패(OSError)는 서비스 가용성을 우선해 무시합니다. 운영 가시성을 위해 추후 메트릭/경고 로그 연동을 권장합니다.
