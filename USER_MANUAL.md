# MIPLATFORM Migrator 사용자 매뉴얼

## 1. 프로젝트 개요

이 프로젝트는 레거시 MIPLATFORM XML 화면/기능 정의를 분석하여 아래 형태로 마이그레이션하기 위한 도구입니다.

- 운영 GUI: `Python + PySide6` 데스크톱 앱 (R13)
- Frontend: `Vite + React 19 + MUI v7 + Zustand` 기반 산출물
- API: `Express (JavaScript)` 라우트/서비스 스캐폴드
- 변환 엔진: `Python`

웹(`preview-host`)은 운영 GUI가 아니라, 생성된 React 화면을 확인하는 미리보기 브리지 용도입니다.

핵심 목표는 다음 3가지입니다.

1. XML를 누락 없이 파싱
2. 파싱 정확성을 검증 게이트로 증명
3. 기능 요소(이벤트/트랜잭션 등) 추출 및 후속 코드 생성 기반 확보

## 2. 사전 준비

아래 환경이 필요합니다.

- `python3`
- `node` + `npm` (preview-host 확인용)
- `PySide6` (데스크톱 GUI 실행 시 필요, 권장 설치: `pip install 'miflatform-migrator[desktop]'` 또는 `pip install PySide6`)

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

### 4.0 데스크톱 우선 실행 경로 (R13)

R13 기본 운영 경로는 CLI 직접 호출이 아니라 데스크톱 GUI입니다.

데스크톱 런치 계약 명령:

```bash
PYTHONPATH=src python3 -m migrator desktop-shell
```

환경/머지 상태 점검용(이벤트 루프 미진입):

```bash
PYTHONPATH=src python3 -m migrator desktop-shell --no-event-loop
```

데스크톱 워크플로우(운영 기준):

1. 실행 모드 선택: `Single XML` 또는 `Batch Folder`
2. 소스 입력 선택:
- `Single XML`: XML 파일 picker
- `Batch Folder`: 폴더 picker + `recursive`/`glob` 조건으로 실행 큐 구성
3. 출력 폴더 picker로 run 산출물 루트 지정
4. (선택) `Project key` 선택/입력
5. 실행 후 상태/로그 패널에서 단계별 결과 확인
6. 필요 시 실패 건만 재시도 큐(실패 전용 배치 플랜) 생성
7. 생성 결과 검증이 필요할 때만 웹 preview route(`/preview/<screenId>`)를 열어 React 렌더링 확인

`Project key` 입력 UX:

- 기존 프로젝트가 있으면 드롭다운/자동완성으로 바로 선택할 수 있습니다.
- 직전 실행 프로젝트(또는 최근 이력 프로젝트)가 기본값으로 우선 선택됩니다.
- 필요하면 새 `Project key`를 직접 입력해 신규 프로젝트로 실행할 수 있습니다.
- 비워두면 기본값으로 `Output root` 폴더명이 자동 적용됩니다.

참고:

- 데스크톱 모듈이 아직 합쳐지지 않았거나 `PySide6`가 없으면 `desktop-shell`은 종료 코드 `2`와 안내 메시지를 반환합니다.
- 이 경우 아래 CLI 경로(`4.1` 이후)를 동일 계약 검증용 fallback으로 사용합니다.

배치 중심 GUI 실행(파일/폴더 picker + 배치 플랜/요약):

```bash
PYTHONPATH=src python3 -m migrator.desktop_app
```

배치 실행 시 생성 파일(예시):

- `out/<...>/desktop-runs/<run_id>/batch-run-plan.json`
- `out/<...>/desktop-runs/<run_id>/batch-run-summary.json`
- `out/<...>/projects/<project_key>/project.json`
- `out/<...>/projects/<project_key>/artifacts/frontend/...`
- `out/<...>/projects/<project_key>/artifacts/api/...`
- `out/<...>/projects/<project_key>/reports/project-consolidation/<run_id>.consolidation.json`
- `out/<...>/projects/<project_key>/coverage-ledger.json`

데스크톱 GUI 탭 구성(현재):

- `Batch Run`: 파일/폴더 선택, 배치 플랜 생성, 실행/취소, 실패 재시도
  - `Live Pipeline Monitor` 포함: 진행률 바, KPI(`total/running/succeeded/failed/canceled/retryable`), 큐 상태 테이블
  - `Stage Status` 탭: 선택 행 기준 단계별 상태(`parse/map_api/gen_ui/fidelity_audit/sync_preview/preview_smoke`)
  - `Log Stream` 탭: 실행 중 선택 행의 실시간 로그 tail
  - `Contract JSON` 탭: 현재 plan/summary/runtime 계약 원문 확인
- `History`: 이전 실행 이력(`batch-run-summary.json`) 조회/선택 로드
  - `Project` 필터(`All/No project/개별 project_key`)로 실행 이력을 프로젝트 단위로 즉시 좁혀 조회
  - 실행 개수/선택 실행 KPI 카드, 선택 실행 메타(`Run ID/Generated/Counts/Run Root`) 제공
  - 우측 상세 패널에서 `Contract JSON`과 `Coverage Ledger` 탭 제공
  - `Coverage Ledger` 탭에서 누적 KPI(unknown tag/attr, unsupported event/tag), UI 렌더 커버리지 바, run별 집계 테이블 확인
- `Preview`: 실행 성공 후 `screenId` 선택 미리보기
  - 대상 개수/총 `screenId`/마지막 오픈 모드 KPI 제공
  - `Preview Controls`와 대형 `Embedded Preview` 캔버스를 분리해 검토 집중도 개선
  - `Route/Preview Host/Manifest` 진단 정보와 URL/오류 로그를 우측 패널에서 확인

`History`에서 과거 실행을 로드한 뒤에도 새 배치는 바로 다시 시작할 수 있습니다.

- `Start New Batch` 버튼으로 현재 로드된 플랜/실행 상태를 초기화
- 이후 `Generate Batch Plan`으로 새 입력 기준 플랜을 다시 생성

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
- 위젯 계열: `Button`, `Edit`, `TextArea`, `MaskEdit`, `Static`, `Combo`, `Grid`, `Image`, `Radio`, `Checkbox`, `Calendar`, `Spin`, `TreeView`, `WebBrowser`, `MSIE`, `Rexpert`, `XChart`
- 비시각 메타 계열(`Dataset`, `colinfo`, `head`, `body`, `summary`, `cell`, `Script` 등)은 fallback 경고를 남기지 않고 trace 목적의 shell로만 반영

Grid 렌더링 규칙(현재):

- `head`/`body`/`summary` 밴드를 분리 렌더링
- `head`는 `TableHead`, `body`는 `TableBody`, `summary`는 `TableFooter`로 생성
- `row` 인덱스가 비연속(`0,2,4` 등)이어도 `rowspan/colspan` 병합을 유지하도록 sparse row를 보존

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

참고:

- `sync-preview`는 preview-host 워크스페이스 루트 밖에 있는 generated screen 모듈을 자동 제외하고 경고를 남깁니다.
- 임시 디렉터리(`/private/var/...`) 기반 모듈이 registry에 고정되어 preview-host build가 깨지는 드리프트를 방지하기 위한 안전장치입니다.

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

## 5. 웹 미리보기로 결과 확인 (검증 전용)

주의:

- 웹은 운영 GUI가 아니라 React 산출물 검증 브리지입니다.
- 실행 제어(파일/폴더 선택, 배치 큐, 상태 관찰)는 데스크톱 GUI가 기본 경로입니다.

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

R13 QA 게이트 묶음 실행:

```bash
python3 scripts/run_r13_qa_gates.py
```

R12 하위 호환 게이트 묶음 실행:

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

### 5.1 데스크톱(PySide6) Preview Bridge 사용 (R13)

R13 방향은 웹 GUI 확장이 아니라 Python 데스크톱 GUI 전환이며, 웹은 React 산출물 검증 용도로만 사용합니다.

데스크톱 앱에서 `src/migrator/desktop_preview_bridge.py`의 `DesktopPreviewBridge`를 사용하면 다음 순서로 동작합니다.

1. preview-host 경로 해석
- 우선순위: `run_preview_host_dir` > `run_summary_file`(`stages.sync_preview.manifest_file`) > 기본 `preview-host`
2. manifest 로드 및 `screenId` 검증
- `<preview-host>/src/manifest/screens.manifest.json`에서 선택한 `screenId` 존재 여부 확인
3. preview-host 프로세스 lifecycle 제어
- start: `npm run dev -- --host <host> --port <port> --strictPort`
- health-check: `GET /`
- stop: 앱 종료 시 명시 정리
4. 라우트 오픈
- `http://<host>:<port>/preview/<screenId>`
5. 렌더링 경로
- 가능하면 embedded WebView(`PySide6.QtWebEngineWidgets`)
- 불가능하면 외부 브라우저로 자동 fallback

이 브리지는 샘플 하드코딩 없이 manifest 계약 기반으로만 `screenId`를 해석합니다.

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

### 6.4 데스크톱 셸이 실행되지 않음

- 증상: `desktop-shell` 실행 시 종료 코드 `2` 또는 `Desktop shell module is unavailable` 메시지
- 원인:
- R13 데스크톱 lane 미병합 상태
- `PySide6` 미설치
- 조치:
- `pip install 'miflatform-migrator[desktop]'` 또는 `pip install PySide6`
- R13 데스크톱 관련 브랜치 머지 상태 확인
- 임시로 CLI fallback(`migrate-e2e`, `run_r13_qa_gates.py`)으로 동일 계약 검증 진행

### 6.5 Desktop Preview Bridge 실패 처리

- `run_summary_file`에 `stages.sync_preview.manifest_file`가 없으면 경로 해석 실패
- 선택한 `screenId`가 manifest에 없으면 `PreviewScreenSelectionError`
- `node`/`npm` 미설치 또는 실행 실패 시 `PreviewHostProcessError`
- health-check timeout이면 `PreviewHostStartTimeoutError`
- Qt WebEngine 미사용 환경에서는 embedded 대신 외부 브라우저 fallback
- 외부 브라우저 열기 실패 시 URL/기본 브라우저 설정 확인 필요

## 7. 권장 실행 체크리스트

1. XML 입력 배치 (`data/input/xml`)
2. `desktop-shell` 실행 (또는 `--no-event-loop` 계약 점검)으로 데스크톱 경로 준비 확인
3. 데스크톱 GUI에서 `Single XML`/`Batch Folder` 모드 선택 + 입력/출력 picker 설정
4. `migrate-e2e` 실행으로 전체 파이프라인 1회 수행 (데스크톱 또는 CLI fallback)
5. 통합 요약 리포트(`out/e2e/<파일명>.migration-summary.json`) 검토
6. `run_real_sample_e2e_regression.py`로 실샘플 회귀 실행
7. `out/real-sample-e2e-regression/regression-summary.json`에서 실패/위험 추세 확인
8. `real_sample_baseline.py snapshot`으로 기준 라운드 베이스라인 저장
9. `real_sample_baseline.py diff --strict`로 라운드 델타/허용치 게이트 검증
10. `preview-smoke` 실행 후 `out/preview-smoke-report.json`의 `unresolved_module_count == 0` 확인
11. `python3 -m unittest -v tests.test_orchestrator_api`로 API 하위 호환 스모크 확인
12. `python3 scripts/run_r13_qa_gates.py`로 R13 게이트 묶음 검증
13. `python3 scripts/run_r12_qa_gates.py`로 R12 하위 호환 게이트 검증
14. `preview-host`에서 `npm run dev`로 육안 확인 (필요 시)
15. `preview-host`에서 `npm run build` 최종 확인
