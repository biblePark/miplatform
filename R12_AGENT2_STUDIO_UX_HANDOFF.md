# R12 Agent2 Studio UX Handoff

## 1) 구현 내용
- `/studio` 실행 UX 개선
  - Run History 패널 추가: 최근 실행 이력(상태, runId, 시작/종료 시각, 요약 메시지) 표시
  - Retry 버튼 추가: 직전 실행 시점 config로 재실행 (`Retry Last Config`)
  - Cancel 버튼 동작 개선: 단순 `AbortController` 중단이 아니라 cancel API 호출 후 로컬 abort 수행
  - 실패 원인 패널 개선: `error code / message / details`를 구조화해서 표시
- 실행 상태/에러 컨텍스트 보강
  - adapter에서 run 시작 시점 `runId` 콜백 제공
  - adapter 에러를 구조화(`code`, `message`, `details`)하여 UI 패널로 전달
  - 실패 시 stage 요약(실패 stage + warnings/errors)을 details에 포함

## 2) 수정 파일 목록
### 담당 범위
- `/Users/biblepark/Desktop/works/miflatform-migrator/preview-host/src/app/StudioMonitoringPage.tsx`
- `/Users/biblepark/Desktop/works/miflatform-migrator/preview-host/src/components/monitoring/LiveMonitoringPanel.tsx`
- `/Users/biblepark/Desktop/works/miflatform-migrator/preview-host/src/components/monitoring/monitoringModel.ts`
- `/Users/biblepark/Desktop/works/miflatform-migrator/preview-host/src/styles.css`

### 범위 외 최소 수정 (빌드/취소 API 연동 위해 불가피)
- `/Users/biblepark/Desktop/works/miflatform-migrator/preview-host/src/components/studio/studioAdapter.ts`
  - `onRunId` 콜백 추가
  - `cancel(runId)` API 추가 및 orchestrator/legacy cancel endpoint 시도 로직 추가
  - 구조화 에러 메타 변환(`toStudioErrorMetadata`) 추가
- `/Users/biblepark/Desktop/works/miflatform-migrator/preview-host/src/vite-env.d.ts`
  - `import.meta.env` 타입 인식용 `vite/client` 참조 추가
- `/Users/biblepark/Desktop/works/miflatform-migrator/preview-host/src/screens/registry.generated.ts`
  - 생성된 절대 임시경로 정적 import로 인한 빌드 실패를 막기 위해 동적 import(+fallback) 형태로 보강

## 3) 실행 테스트/결과
- 실행: `npm run build` (workdir: `/Users/biblepark/Desktop/works/miflatform-migrator/preview-host`)
- 결과: 통과
  - `tsc -b && vite build` 성공
  - 산출: `dist/index.html`, `dist/assets/*` 생성 확인

## 4) 리스크/후속 제안
- cancel endpoint 계약이 환경별로 다를 수 있어 adapter에서 다중 후보 경로를 순차 시도하도록 구현했습니다.
  - 후속: orchestrator/legacy cancel API 경로를 단일 계약으로 확정 후 후보 경로 정리 권장
- `registry.generated.ts`는 원래 생성물이므로, 현재 보강 로직(동적 import/fallback)은 임시 안정화 성격입니다.
  - 후속: `sync-preview` 생성기에서 절대 임시경로가 들어가지 않도록 생성 규칙 수정 권장
