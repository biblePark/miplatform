# R11_AGENT5_QA_HANDOFF

## 1) 구현 내용
- 리포트 조회 UX를 위한 `scripts/report_view.py`를 추가했습니다.
- 지원 타입: `migration_summary`, `regression_summary`, `prototype_acceptance`
- 입력 계약:
- 파일/디렉터리 입력 지원
- 디렉터리 입력 시 `*.json` 재귀 스캔
- `--report-type auto` 기반 자동 감지 + 강제 타입 지정 가능
- 출력 계약:
- `--format text`(기본): 터미널 스캔용 핵심 KPI 요약
- `--format json`: 공통 정규화 스키마(`schema_version`, `report_count`, `reports[]`)
- 실패 게이트:
- 명시 파일이 비지원 계약이면 종료 코드 `2`
- 필수 필드/JSON 파싱 오류 시 종료 코드 `2`
- 통합 테스트를 추가했습니다(`tests/test_report_view.py`).
- `migrate-e2e` + `prototype-accept` 산출물 조회 검증
- `run_real_sample_e2e_regression.py` 산출물 조회 JSON 계약 검증
- 비지원 명시 파일 실패 게이트 검증
- 문서화 반영:
- `docs/TECH_SPEC.md`에 Report Query/Display Contract (R11) 추가
- `USER_MANUAL.md`에 리포트 조회 UX 사용법 추가
- `docs/QA_GATES.md` 신설: 수용 게이트 성공/실패 기준 명문화
- `docs/INDEX.md`에 QA 게이트 문서 링크 및 권장 읽기 순서 반영

## 2) 수정 파일 목록
- `/Users/biblepark/Desktop/works/miflatform-migrator/scripts/report_view.py`
- `/Users/biblepark/Desktop/works/miflatform-migrator/tests/test_report_view.py`
- `/Users/biblepark/Desktop/works/miflatform-migrator/USER_MANUAL.md`
- `/Users/biblepark/Desktop/works/miflatform-migrator/docs/TECH_SPEC.md`
- `/Users/biblepark/Desktop/works/miflatform-migrator/docs/QA_GATES.md`
- `/Users/biblepark/Desktop/works/miflatform-migrator/docs/INDEX.md`

## 3) 실행 테스트/결과
- `python3 -m py_compile scripts/report_view.py tests/test_report_view.py` -> PASS
- `python3 -m unittest -v tests.test_report_view` -> PASS (3 tests)
- `python3 -m unittest -v tests.test_real_sample_e2e_regression tests.test_real_sample_baseline` -> PASS (6 tests)
- `python3 -m unittest -v tests.test_cli` -> PASS (16 tests)
- `python3 -m unittest -v` -> PASS (77 tests)

## 4) 리스크/후속 제안
- 현재 `report_view.py` 정규화 계약은 3개 상위 리포트 타입에 집중되어 있습니다. 단계별 리포트(`parse/map-api/gen-ui/fidelity/preview`)까지 단일 UX에서 동일 계약으로 조회하려면 후속 확장이 필요합니다.
- 디렉터리 스캔 시 비지원 JSON은 스킵하도록 설계했습니다. 운영 환경에서 비지원 파일 비율이 높아지면 `--strict-dir`(비지원 포함 즉시 실패) 같은 모드 추가를 고려할 수 있습니다.
- 수용 정책 변경 시 `docs/QA_GATES.md`와 `scripts/report_view.py`의 KPI 필드 해석(예: adapter signal 허용치)을 함께 업데이트해야 문서/실행 일치가 유지됩니다.
