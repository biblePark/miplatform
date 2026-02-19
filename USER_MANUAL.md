# MIPLATFORM Migrator 사용자 매뉴얼

## 1. 프로젝트 개요

이 프로젝트는 레거시 MIPLATFORM XML 화면/기능 정의를 분석하여 아래 형태로 마이그레이션하기 위한 도구입니다.

- Frontend: `Vite + React 19 + MUI v7 + Zustand` 기반 산출물
- API: `Express (JavaScript)` 라우트/서비스 스캐폴드
- 변환 엔진: `Python`

핵심 목표는 다음 3가지입니다.

1. XML를 누락 없이 파싱
2. 파싱 정확성을 검증 게이트로 증명
3. 기능 요소(이벤트/트랜잭션 등) 추출 및 후속 코드 생성 기반 확보

## 2. 사전 준비

아래 환경이 필요합니다.

- `python3`
- `node` + `npm` (preview-host 확인용)

프로젝트 루트로 이동:

```bash
cd /Users/biblepark/Desktop/works/miflatform-migrator
```

## 3. 입력 파일 위치 규칙

실제 변환 대상 XML은 아래 경로를 권장합니다.

- XML 입력: `data/input/xml/`
- (선택) strict 프로파일:
- `data/input/profiles/known_tags.txt`
- `data/input/profiles/known_attrs.json`

초기 폴더 생성:

```bash
mkdir -p data/input/xml data/input/profiles out generated/frontend/src/screens
```

참고:

- `data/`, `out/`, `generated/`, `*.xml`은 기본적으로 Git 추적 대상이 아닙니다.

## 4. 기본 작업 순서

### 4.1 원커맨드 E2E 마이그레이션 (R07 권장)

하나의 XML 기준으로 `parse -> map-api -> gen-ui -> fidelity-audit -> sync-preview -> preview-smoke`를 한 번에 실행합니다. (`gen-ui` 단계에서 behavior store/actions wiring 산출물도 함께 생성)

```bash
PYTHONPATH=src python3 -m migrator migrate-e2e data/input/xml/<파일명>.xml \
  --out-dir out/e2e \
  --api-out-dir generated/api \
  --ui-out-dir generated/frontend \
  --preview-host-dir preview-host \
  --strict \
  --capture-text \
  --known-tags-file data/input/profiles/known_tags.txt \
  --known-attrs-file data/input/profiles/known_attrs.json \
  --pretty
```

주요 산출물:

- 통합 요약 리포트: `out/e2e/<파일명>.migration-summary.json`
- 단계별 리포트: `out/e2e/<파일명>.parse-report.json`, `out/e2e/<파일명>.map-api-report.json`, `out/e2e/<파일명>.gen-ui-report.json`, `out/e2e/<파일명>.fidelity-audit-report.json`, `out/e2e/<파일명>.preview-sync-report.json`, `out/e2e/<파일명>.preview-smoke-report.json`
- 생성 코드:
- API 스텁: `generated/api/src/routes`, `generated/api/src/services`
- UI 화면: `generated/frontend/src/screens`
- UI behavior wiring: `generated/frontend/src/behavior/*.store.ts`, `generated/frontend/src/behavior/*.actions.ts`
- Preview 동기화: `preview-host/src/manifest/screens.manifest.json`, `preview-host/src/screens/registry.generated.ts`

확인 포인트:

- 통합 리포트 `overall_status`, `overall_exit_code`
- `stages`별 상태(`parse`, `map_api`, `gen_ui`, `fidelity_audit`, `sync_preview`, `preview_smoke`)
- `stages.gen_ui` 이벤트 wiring 지표:
- `wired_event_bindings`
- `total_event_attributes`
- `runtime_wired_event_props`
- `unsupported_event_bindings`
- `generated_file_references` 목록

### 4.1.1 프로토타입 수용 KPI 판정 (R10)

`migrate-e2e` 요약 리포트(`*.migration-summary.json`)를 읽어 프로토타입 수용 여부를 pass/fail로 판정합니다.

```bash
PYTHONPATH=src python3 -m migrator prototype-accept out/e2e \
  --report-out out/e2e/prototype-acceptance.json \
  --pretty
```

기본 임계치(default):

- `max_failed_migration_count = 0`
- `max_fidelity_risk_count = 0`
- `min_event_runtime_wiring_coverage_ratio = 1.0`
- `max_unsupported_event_bindings = 0`
- `max_unresolved_transaction_adapter_signals = 0`

임계치 커스터마이즈:

```bash
PYTHONPATH=src python3 -m migrator prototype-accept out/e2e \
  --report-out out/e2e/prototype-acceptance.json \
  --thresholds-file out/e2e/acceptance-thresholds.json \
  --max-unresolved-transaction-adapter-signals 5 \
  --pretty
```

확인 포인트:

- `verdict` (`pass`/`fail`)
- `kpi_results`별 actual/threshold 비교
- `totals.fidelity_risk_count`, `totals.unsupported_event_bindings`, `totals.unresolved_transaction_adapter_signals`
- `evaluations[*]`의 파일별 위험 세부값

### 4.2 실샘플 E2E 회귀 실행 (R08)

합의된 실샘플 XML 세트 전체를 대상으로 `migrate-e2e`를 반복 실행하고, 추출/매핑/정합성(fidelity) 위험 추세를 통합 리포트로 생성합니다.

```bash
PYTHONPATH=src python3 scripts/run_real_sample_e2e_regression.py \
  --samples-dir data/input/xml \
  --recursive \
  --out-dir out/real-sample-e2e-regression \
  --strict \
  --capture-text \
  --known-tags-file data/input/profiles/known_tags.txt \
  --known-attrs-file data/input/profiles/known_attrs.json \
  --pretty
```

`--samples-dir` 대신 `--sample-list-file`을 사용하면 합의된 파일 목록만 실행할 수 있습니다.

```bash
PYTHONPATH=src python3 scripts/run_real_sample_e2e_regression.py \
  --sample-list-file data/input/profiles/real_sample_set.txt \
  --out-dir out/real-sample-e2e-regression \
  --strict \
  --capture-text \
  --known-tags-file data/input/profiles/known_tags.txt \
  --known-attrs-file data/input/profiles/known_attrs.json \
  --pretty
```

주요 산출물:

- 통합 JSON 리포트: `out/real-sample-e2e-regression/regression-summary.json`
- 통합 Markdown 리포트: `out/real-sample-e2e-regression/regression-summary.md`
- 샘플별 실행 결과: `out/real-sample-e2e-regression/runs/<순번>-<xml-stem>/`
- 샘플별 단계 리포트: `.../reports/<xml-stem>.*-report.json`, `.../reports/<xml-stem>.migration-summary.json`

확인 포인트:

- 전체 성공/실패 건수: `totals.success_count`, `totals.failure_count`
- 단계별 실패 현황: `stage_status_counts`, `stage_failure_details`
- 상위 경고: `top_warnings`
- 위험 추세: `risk_trends.extraction`, `risk_trends.mapping`, `risk_trends.fidelity`
- 미해결 XML 파싱 차단 이슈: `malformed_xml_blockers`

### 4.2.1 라운드 베이스라인 스냅샷/델타 비교 (R10)

실샘플 회귀 KPI의 라운드 간 변동을 추적하려면, 기준 라운드의 스냅샷을 저장한 뒤 다음 라운드에서 델타 비교를 수행합니다.

```bash
# 기준 라운드 스냅샷 저장 (예: R09)
python3 scripts/real_sample_baseline.py snapshot \
  --summary-json out/real-sample-e2e-regression/regression-summary.json \
  --round R09 \
  --pretty
```

```bash
# 현재 라운드 비교 + 허용치 초과 시 실패 (예: R10)
python3 scripts/real_sample_baseline.py diff \
  --current-summary-json out/real-sample-e2e-regression/regression-summary.json \
  --baseline-round R09 \
  --current-round R10 \
  --tolerances-file ops/real_sample_baseline_tolerances.json \
  --strict \
  --pretty
```

베이스라인 산출물 경로:

- 스냅샷 JSON: `out/real-sample-e2e-regression/baselines/<ROUND>/baseline-summary.json`
- 스냅샷 Markdown: `out/real-sample-e2e-regression/baselines/<ROUND>/baseline-summary.md`
- 델타 JSON: `out/real-sample-e2e-regression/baseline-diff.json`
- 델타 Markdown: `out/real-sample-e2e-regression/baseline-diff.md`
- KPI 허용치 설정: `ops/real_sample_baseline_tolerances.json`

검증 포인트:

- 델타 리포트가 `stage.*`/`risk.*` 차원별로 `regression`/`improvement`를 분류하는지
- `tolerance_evaluation.violations`가 허용치 초과 KPI를 정확히 기록하는지
- `--strict` 실행 시 허용치 초과가 있으면 종료 코드 `2`로 실패하는지

### 4.2.2 리포트 조회 UX (R11)

JSON 리포트를 직접 열지 않고, 조회 전용 스크립트로 핵심 지표를 빠르게 확인할 수 있습니다.

```bash
# 텍스트 요약 조회 (기본)
python3 scripts/report_view.py out/e2e/<파일명>.migration-summary.json
python3 scripts/report_view.py out/e2e/prototype-acceptance.json
python3 scripts/report_view.py out/real-sample-e2e-regression/regression-summary.json
```

```bash
# 디렉터리 전체 스캔 + 기계처리용 JSON 출력
python3 scripts/report_view.py out/real-sample-e2e-regression \
  --format json \
  --pretty
```

출력 계약 요약:

- 지원 리포트 타입: `migration_summary`, `regression_summary`, `prototype_acceptance`
- JSON 출력 루트 필드:
- `schema_version`
- `report_count`
- `reports[]` (`source_file`, `report_type`, `summary`)
- 디렉터리 입력 시 비지원 JSON은 스킵되며 stderr에 스킵 개수가 출력됩니다.
- 명시적으로 지정한 파일이 비지원 계약이면 종료 코드 `2`로 실패합니다.

수용 게이트의 성공/실패 기준은 `docs/QA_GATES.md`를 참고하세요.

### 4.3 단일 XML 파싱 검증

```bash
PYTHONPATH=src python3 -m migrator parse data/input/xml/<파일명>.xml \
  --out out/parse-<파일명>.json \
  --strict \
  --capture-text \
  --known-tags-file data/input/profiles/known_tags.txt \
  --known-attrs-file data/input/profiles/known_attrs.json \
  --pretty
```

확인 포인트:

- `out/parse-<파일명>.json` 생성 여부
- `gates` 항목이 모두 `passed=true`인지

### 4.4 다수 XML 일괄 파싱

```bash
PYTHONPATH=src python3 -m migrator batch-parse data/input/xml \
  --out-dir out/batch-reports \
  --summary-out out/batch-summary.json \
  --recursive \
  --strict \
  --capture-text \
  --known-tags-file data/input/profiles/known_tags.txt \
  --known-attrs-file data/input/profiles/known_attrs.json \
  --pretty
```

확인 포인트:

- `out/batch-summary.json`의 `failures`, `gate_pass_fail_counts`
- 개별 리포트: `out/batch-reports/*.json`

### 4.5 API 스캐폴드 생성

```bash
PYTHONPATH=src python3 -m migrator map-api data/input/xml/<파일명>.xml \
  --out-dir out/generated-api \
  --report-out out/map-api-<파일명>.json \
  --strict \
  --capture-text \
  --known-tags-file data/input/profiles/known_tags.txt \
  --known-attrs-file data/input/profiles/known_attrs.json \
  --pretty
```

산출물:

- 라우트/서비스 스텁: `out/generated-api/src/routes`, `out/generated-api/src/services`
- 매핑 보고서: `out/map-api-<파일명>.json`

### 4.6 UI TSX 스캐폴드 생성 (R06)

```bash
PYTHONPATH=src python3 -m migrator gen-ui data/input/xml/<파일명>.xml \
  --out-dir generated/frontend \
  --report-out out/gen-ui-<파일명>.json \
  --strict \
  --capture-text \
  --known-tags-file data/input/profiles/known_tags.txt \
  --known-attrs-file data/input/profiles/known_attrs.json \
  --pretty
```

산출물:

- 생성 컴포넌트: `generated/frontend/src/screens/*.tsx`
- behavior wiring 스캐폴드: `generated/frontend/src/behavior/*.store.ts`, `generated/frontend/src/behavior/*.actions.ts`
- 코드젠 보고서: `out/gen-ui-<파일명>.json`

기본 UI 태그 매핑(현재 기준):

- 컨테이너 계열: `Screen`, `Contents`, `Container`, `Window`, `Form`, `Div`, `Shape`, `Tab`, `TabPage`
- 위젯 계열: `Button`, `Edit`, `TextArea`, `MaskEdit`, `Static`, `Combo`, `Grid`, `Image`, `Radio`, `Checkbox`, `Calendar`, `Spin`, `TreeView`, `WebBrowser`, `MSIE`, `Rexpert`
- 비시각 메타 계열(`Dataset`, `colinfo`, `cell`, `Script` 등)은 fallback 경고를 남기지 않고 trace 목적의 shell로만 반영

### 4.6.1 UI Fidelity 감사 리포트 생성 (R09)

생성된 UI TSX가 XML 노드/스타일 속성을 얼마나 커버하는지 deterministic 리포트를 생성합니다.

```bash
PYTHONPATH=src python3 -m migrator fidelity-audit data/input/xml/<파일명>.xml \
  --generated-ui-file generated/frontend/src/screens/<screen-file>.tsx \
  --report-out out/fidelity-audit-<파일명>.json \
  --strict \
  --capture-text \
  --known-tags-file data/input/profiles/known_tags.txt \
  --known-attrs-file data/input/profiles/known_attrs.json \
  --pretty
```

확인 포인트:

- `summary.missing_node_count`
- `summary.position_attribute_coverage_ratio`, `summary.style_attribute_coverage_ratio`
- `missing_node_paths`, `position_style_coverage_risks`

확인 포인트(이벤트 wiring 리스크):

- `summary.total_event_attributes`: XML에서 감지된 `on*` 속성 수
- `summary.runtime_wired_event_props`: 실제 React 이벤트 prop으로 매핑된 수
- `summary.unsupported_event_bindings`: 미지원/미결선 이벤트 수
- `unsupported_event_inventory[]`: 구조화된 미지원 이벤트 목록 (`reason`, `event_name`, `action_name`, `warning` 포함)

### 4.6.2 Behavior 스캐폴드만 재생성 (선택)

behavior 파일만 별도로 다시 만들고 싶다면 아래 명령을 사용합니다.

```bash
PYTHONPATH=src python3 -m migrator gen-behavior-store data/input/xml/<파일명>.xml \
  --out-dir generated/frontend \
  --report-out out/gen-behavior-store-<파일명>.json \
  --strict \
  --capture-text \
  --known-tags-file data/input/profiles/known_tags.txt \
  --known-attrs-file data/input/profiles/known_attrs.json \
  --pretty
```

### 4.7 Preview Host 동기화 (R06)

UI 생성 결과를 브라우저에서 열 수 있도록 manifest/registry를 동기화합니다.

```bash
PYTHONPATH=src python3 -m migrator sync-preview \
  --generated-screens-dir generated/frontend/src/screens \
  --preview-host-dir preview-host \
  --report-out out/preview-sync-report.json \
  --pretty
```

산출물:

- `preview-host/src/manifest/screens.manifest.json`
- `preview-host/src/screens/registry.generated.ts`
- `out/preview-sync-report.json`

### 4.8 Preview Host Smoke 증거 생성 (R10)

생성된 화면 모듈이 실제로 로더/경로에서 해석 가능한지 증거 리포트를 생성합니다.

```bash
PYTHONPATH=src python3 -m migrator preview-smoke \
  --generated-screens-dir generated/frontend/src/screens \
  --preview-host-dir preview-host \
  --report-out out/preview-smoke-report.json \
  --pretty
```

산출물:

- `out/preview-smoke-report.json`

확인 포인트:

- `screens[]`: 화면별 `module_present`, `loader_registered`, `route_resolvable`
- `route_paths[]`: 생성 화면 기준 `/preview/<screenId>` 목록
- `unresolved_module_count`: 0이어야 통과 (0보다 크면 명령 종료코드 2)

## 5. 브라우저에서 결과 확인

Smoke 확인:

```bash
PYTHONPATH=src python3 -m migrator preview-smoke \
  --generated-screens-dir generated/frontend/src/screens \
  --preview-host-dir preview-host \
  --report-out out/preview-smoke-report.json \
  --pretty
```

`out/preview-smoke-report.json`에서 `unresolved_module_count == 0` 확인 후 dev/build 검증을 진행합니다.

Preview Host 실행:

```bash
cd /Users/biblepark/Desktop/works/miflatform-migrator/preview-host
npm install
npm run dev
```

Studio 모니터링(`/studio`)까지 사용하려면 Orchestrator API도 함께 실행하세요:

```bash
cd /Users/biblepark/Desktop/works/miflatform-migrator
PYTHONPATH=src python3 -m migrator.orchestrator_api --host 127.0.0.1 --port 8765 --workspace-root .
```

- `preview-host/vite.config.ts`는 기본적으로 `/jobs`, `/health`를 `http://127.0.0.1:8765`로 프록시합니다.
- 다른 API 주소를 사용하려면 `MIFL_STUDIO_API_TARGET` 환경변수를 설정한 뒤 `npm run dev`를 실행하세요.

Studio + Orchestrator 연계 스모크(자동) 실행:

```bash
python3 -m unittest -v tests.test_orchestrator_api
```

핵심 확인 테스트:

- `test_studio_orchestrator_e2e_smoke_contract`
- `test_post_jobs_cancel_marks_running_job_as_canceled`
- `test_history_retry_flow_records_failed_then_successful_reexecution`

R12 QA 게이트 묶음 실행:

```bash
python3 scripts/run_r12_qa_gates.py
```

참고:

- Preview Host는 대형 ERP 화면 확인을 위해 데스크탑 캔버스 기준으로 표시됩니다.
- 기본적으로 넓은 캔버스(`min-width` 기반) + 내부 스크롤 영역을 사용하므로, 화면 요소가 많은 경우 가로/세로 스크롤로 확인하세요.

접속:

- `http://127.0.0.1:5173/`
- `http://127.0.0.1:5173/studio`
- `http://127.0.0.1:5173/preview/<screenId>`

`screenId` 확인 방법:

- `preview-host/src/manifest/screens.manifest.json`의 `screens[].screenId` 값 사용

빌드 검증:

```bash
npm run build
```

## 6. 자주 발생하는 이슈

### 6.1 strict 파싱 실패

- 원인: `unknown_tag_count`, `unknown_attr_count` 게이트 실패
- 조치: `known_tags.txt`, `known_attrs.json`에 누락 항목 보완

### 6.2 XML 파싱 실패

- 원인: 원본 XML 문법 오류(태그 불일치, invalid token 등)
- 조치: 해당 XML를 먼저 정합성 수정 후 재실행

### 6.3 미리보기 화면이 열리지 않음

- `sync-preview`를 먼저 실행했는지 확인
- `preview-smoke` 결과에서 `unresolved_module_count`가 0인지 확인
- `screens.manifest.json`에 대상 `screenId`가 있는지 확인
- `preview-host`에서 `npm install` 후 `npm run dev` 재실행

## 7. 권장 실행 체크리스트

1. XML 입력 배치 (`data/input/xml`)
2. `migrate-e2e` 실행으로 전체 파이프라인 1회 수행
3. 통합 요약 리포트(`out/e2e/<파일명>.migration-summary.json`) 검토
4. `run_real_sample_e2e_regression.py`로 실샘플 회귀 실행
5. `out/real-sample-e2e-regression/regression-summary.json`에서 실패/위험 추세 확인
6. `real_sample_baseline.py snapshot`으로 기준 라운드 베이스라인 저장
7. `real_sample_baseline.py diff --strict`로 라운드 델타/허용치 게이트 검증
8. `preview-smoke` 실행 후 `out/preview-smoke-report.json`의 `unresolved_module_count == 0` 확인
9. `python3 -m unittest -v tests.test_orchestrator_api`로 Studio/Orchestrator 연계 스모크 확인
10. `python3 scripts/run_r12_qa_gates.py`로 R12 게이트 묶음 검증
11. `preview-host`에서 `npm run dev`로 육안 확인
12. `preview-host`에서 `npm run build` 최종 확인
