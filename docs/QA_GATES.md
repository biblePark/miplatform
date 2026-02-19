# QA Gates (R13)

이 문서는 R13 수용 게이트의 성공/실패 기준을 정의합니다.

R13 방향성:

- 운영 GUI의 기본 경로는 Python 데스크톱(`PySide6`)입니다.
- 웹(`preview-host`)은 생성된 React 산출물 검증용 브리지로만 사용합니다.
- 기존 migrator 코어/계약(`parse/map-api/gen-ui/fidelity/sync/preview-smoke`, Orchestrator API)은 하위 호환을 유지합니다.

## 1) 게이트 범위

- 단일 XML E2E 결과: `*.migration-summary.json`
- 실샘플 회귀 결과: `regression-summary.json`
- 프로토타입 수용 결과: `prototype-acceptance.json`
- 라운드 비교 결과: `baseline-diff.json`
- 데스크톱 런치 계약 테스트: `tests.test_desktop_launch_contract`
- 서비스 계약 테스트: `tests.test_runner_service_contract`
- 웹 프리뷰 브리지 스모크: `tests.test_preview_smoke`
- R13 QA 게이트 자동 실행 세트: `scripts/run_r13_qa_gates.py`
- R12 기존 게이트 하위 호환 세트: `scripts/run_r12_qa_gates.py`

## 2) 게이트 정의

### Gate A: 단일 E2E 파이프라인 성공

실행:

```bash
PYTHONPATH=src python3 -m migrator migrate-e2e data/input/xml/<파일명>.xml \
  --out-dir out/e2e \
  --api-out-dir generated/api \
  --ui-out-dir generated/frontend \
  --preview-host-dir preview-host \
  --pretty
```

성공 기준:

- 종료 코드 `0`
- `*.migration-summary.json`에서:
- `overall_status == "success"`
- `overall_exit_code == 0`
- `stages.parse|map_api|gen_ui|fidelity_audit|sync_preview|preview_smoke.status == "success"`
- `stages.preview_smoke.unresolved_module_count == 0`

실패 기준:

- 종료 코드 `2`
- 또는 위 성공 조건 중 하나라도 미충족

### Gate B: 프로토타입 수용 판정

실행:

```bash
PYTHONPATH=src python3 -m migrator prototype-accept out/e2e \
  --report-out out/e2e/prototype-acceptance.json \
  --pretty
```

성공 기준:

- 종료 코드 `0`
- `prototype-acceptance.json`에서:
- `verdict == "pass"`
- `kpi_results[*].passed == true`

실패 기준:

- 종료 코드 `2`
- `verdict == "fail"`
- `kpi_results` 중 하나 이상 `passed == false`

### Gate C: 실샘플 회귀 실행

실행:

```bash
PYTHONPATH=src python3 scripts/run_real_sample_e2e_regression.py \
  --samples-dir data/input/xml \
  --recursive \
  --out-dir out/real-sample-e2e-regression \
  --pretty
```

성공 기준:

- 종료 코드 `0`
- `regression-summary.json`에서:
- `overall_status == "success"`
- `overall_exit_code == 0`
- `totals.failure_count == 0`
- `malformed_xml_blockers` 길이 `0`

실패 기준:

- 종료 코드 `2`
- 또는 위 성공 조건 중 하나라도 미충족

### Gate D: 라운드 베이스라인 허용치

실행:

```bash
python3 scripts/real_sample_baseline.py diff \
  --current-summary-json out/real-sample-e2e-regression/regression-summary.json \
  --baseline-round <BASELINE_ROUND> \
  --current-round <CURRENT_ROUND> \
  --tolerances-file ops/real_sample_baseline_tolerances.json \
  --strict \
  --pretty
```

성공 기준:

- 종료 코드 `0`
- `baseline-diff.json`에서:
- `tolerance_evaluation.passed == true`
- `tolerance_evaluation.violation_count == 0`

실패 기준:

- 종료 코드 `2`
- `tolerance_evaluation.passed == false`
- `tolerance_evaluation.violation_count > 0`

### Gate E: 데스크톱 런치 계약

실행:

```bash
python3 -m unittest -v tests.test_desktop_launch_contract
```

성공 기준:

- 종료 코드 `0`
- 아래 계약 테스트가 모두 PASS:
- `test_parser_accepts_desktop_shell_command`
- `test_run_desktop_shell_returns_contract_error_when_module_is_missing`

실패 기준:

- 종료 코드 `0`이 아님
- 위 테스트 중 하나 이상 FAIL/ERROR

### Gate F: 서비스 계약 (Orchestrator Service)

실행:

```bash
python3 -m unittest -v tests.test_runner_service_contract
```

성공 기준:

- 종료 코드 `0`
- 아래 계약 테스트가 모두 PASS:
- `test_job_request_contract_exposes_cli_namespace_and_public_fields`
- `test_service_executes_job_and_surfaces_preview_stage_artifacts`
- `test_service_cancel_contract_marks_running_job_as_canceled`

실패 기준:

- 종료 코드 `0`이 아님
- 위 테스트 중 하나 이상 FAIL/ERROR

### Gate G: Preview 브리지 스모크

실행:

```bash
python3 -m unittest -v tests.test_preview_smoke
```

성공 기준:

- 종료 코드 `0`
- 생성 화면 route/module 계약 검증 테스트가 PASS

실패 기준:

- 종료 코드 `0`이 아님
- 테스트 FAIL/ERROR

### Gate H: R13 QA Gate 묶음 실행

실행:

```bash
python3 scripts/run_r13_qa_gates.py
```

성공 기준:

- 종료 코드 `0`
- 포함 테스트 모듈:
- `tests.test_desktop_launch_contract`
- `tests.test_runner_service_contract`
- `tests.test_orchestrator_api`
- `tests.test_cli`
- `tests.test_preview_smoke`
- `tests.test_prototype_acceptance`
- `tests.test_real_sample_e2e_regression`
- `tests.test_real_sample_baseline`
- `tests.test_report_view`

실패 기준:

- 종료 코드 `0`이 아님

### Gate I: R12 하위 호환 게이트 묶음

실행:

```bash
python3 scripts/run_r12_qa_gates.py
```

성공 기준:

- 종료 코드 `0`

실패 기준:

- 종료 코드 `0`이 아님

## 3) 운영 체크 순서

1. Gate A 통과 확인
2. Gate B 통과 확인
3. Gate C 통과 확인
4. Gate D 통과 확인 (`--strict`)
5. Gate E 통과 확인
6. Gate F 통과 확인
7. Gate G 통과 확인
8. Gate H 통과 확인
9. Gate I 통과 확인
10. `scripts/report_view.py`로 핵심 지표 최종 조회

## 4) 리포트 조회/게이트 실행 권장 명령

```bash
python3 scripts/report_view.py out/e2e/<파일명>.migration-summary.json
python3 scripts/report_view.py out/e2e/prototype-acceptance.json
python3 scripts/report_view.py out/real-sample-e2e-regression/regression-summary.json
python3 scripts/run_r13_qa_gates.py
python3 scripts/run_r12_qa_gates.py
```
