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

하나의 XML 기준으로 `parse -> map-api -> gen-ui -> sync-preview`를 한 번에 실행합니다. (`gen-ui` 단계에서 behavior store/actions wiring 산출물도 함께 생성)

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
- 단계별 리포트: `out/e2e/<파일명>.parse-report.json`, `out/e2e/<파일명>.map-api-report.json`, `out/e2e/<파일명>.gen-ui-report.json`, `out/e2e/<파일명>.preview-sync-report.json`
- 생성 코드:
- API 스텁: `generated/api/src/routes`, `generated/api/src/services`
- UI 화면: `generated/frontend/src/screens`
- UI behavior wiring: `generated/frontend/src/behavior/*.store.ts`, `generated/frontend/src/behavior/*.actions.ts`
- Preview 동기화: `preview-host/src/manifest/screens.manifest.json`, `preview-host/src/screens/registry.generated.ts`

확인 포인트:

- 통합 리포트 `overall_status`, `overall_exit_code`
- `stages`별 상태(`parse`, `map_api`, `gen_ui`, `sync_preview`)
- `generated_file_references` 목록

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

### 4.6.1 Behavior 스캐폴드만 재생성 (선택)

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

## 5. 브라우저에서 결과 확인

Preview Host 실행:

```bash
cd /Users/biblepark/Desktop/works/miflatform-migrator/preview-host
npm install
npm run dev
```

접속:

- `http://127.0.0.1:5173/`
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
- `screens.manifest.json`에 대상 `screenId`가 있는지 확인
- `preview-host`에서 `npm install` 후 `npm run dev` 재실행

## 7. 권장 실행 체크리스트

1. XML 입력 배치 (`data/input/xml`)
2. `migrate-e2e` 실행으로 전체 파이프라인 1회 수행
3. 통합 요약 리포트(`out/e2e/<파일명>.migration-summary.json`) 검토
4. `run_real_sample_e2e_regression.py`로 실샘플 회귀 실행
5. `out/real-sample-e2e-regression/regression-summary.json`에서 실패/위험 추세 확인
6. `preview-host`에서 `npm run dev`로 육안 확인
7. `preview-host`에서 `npm run build` 최종 확인
