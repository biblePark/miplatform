# QA Gates (R11)

이 문서는 리포트 기반 수용 게이트의 성공/실패 기준을 정의합니다.

## 1) 게이트 범위

- 단일 XML E2E 결과: `*.migration-summary.json`
- 실샘플 회귀 결과: `regression-summary.json`
- 프로토타입 수용 결과: `prototype-acceptance.json`
- 라운드 비교 결과: `baseline-diff.json`

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

## 3) 운영 체크 순서

1. Gate A 통과 확인
2. Gate B 통과 확인
3. Gate C 통과 확인
4. Gate D 통과 확인 (`--strict`)
5. `scripts/report_view.py`로 핵심 지표 최종 조회

## 4) 리포트 조회 권장 명령

```bash
python3 scripts/report_view.py out/e2e/<파일명>.migration-summary.json
python3 scripts/report_view.py out/e2e/prototype-acceptance.json
python3 scripts/report_view.py out/real-sample-e2e-regression/regression-summary.json
```
