# R12 Agent3 Adapter Handoff

## 1) 구현 내용

- `studioAdapter`의 상태/스테이지/로그 매핑 규칙을 단일 정규화 계층으로 통합했습니다.
  - run status 정규화: `queued/running/succeeded/failed/canceled` 계열 alias 통합
  - stage status 정규화: `success/failure/skipped` 계열 alias 통합
  - log level 정규화: `info/warn/error` 계열 alias 통합
- `/jobs` 계약 파서를 강화해 누락/변형 필드에 방어적으로 대응하도록 변경했습니다.
  - job 식별자 alias: `id`, `job_id`, `run_id`, `runId`
  - 상태 alias: `status`, `state`, `job_status`, `run_status`
  - logs alias: `logs`, `log_entries`, `entries`, `events`, `items`
  - stage 요약 alias: 배열/객체(`stageSummaries` 또는 `stages`) 모두 파싱
  - report/artifact alias: `reports`, `report_files`, `markdown/json` 경로/본문 key 변형 수용
- Orchestrator polling 안정성을 강화했습니다.
  - `/jobs/{id}/logs` 실패 시 1회 경고 로그 후 상태 polling은 계속 진행
  - `/jobs/{id}/artifacts` recoverable 오류 시 job 상태 기준으로 최소 리포트 생성
- URL 처리 backward compatibility를 보완했습니다.
  - `statusUrl`이 절대 URL일 때도 정상 처리하도록 `buildApiUrl` 보강
  - Legacy adapter에서 `runId` 누락 시에도 `statusUrl`이 있으면 polling 가능
  - polling 중 응답에 새 `statusUrl`이 오면 갱신 사용
- fallback 체인(`orchestrator -> legacy -> mock`)은 유지했습니다.
- `vite.config.ts`에서 adapter 기본 호출 prefix(`/jobs`, `/health`, `/api/studio`)와 dev proxy prefix를 단일 상수로 맞췄습니다.

- 빌드 차단 해소(범위 외 최소 수정):
  - `preview-host/src/screens/registry.generated.ts`의 임시 절대경로 import를 로컬 placeholder 경로로 치환해 `npm run build`를 통과시켰습니다.

## 2) 수정 파일 목록

- `/Users/biblepark/Desktop/works/miflatform-migrator/preview-host/src/components/studio/studioAdapter.ts`
- `/Users/biblepark/Desktop/works/miflatform-migrator/preview-host/vite.config.ts`
- `/Users/biblepark/Desktop/works/miflatform-migrator/preview-host/src/screens/registry.generated.ts` (빌드 unblock 목적의 최소 수정)
- `/Users/biblepark/Desktop/works/miflatform-migrator/R12_AGENT3_ADAPTER_HANDOFF.md`

## 3) 실행 테스트/결과

1. `cd /Users/biblepark/Desktop/works/miflatform-migrator/preview-host && npm run build`
- 결과: 성공
- 비고: 초기 1회는 `registry.generated.ts`의 삭제된 임시 디렉터리 import 경로로 실패했으며, 경로 정리 후 재실행하여 통과했습니다.

## 4) 리스크/후속 제안

- `registry.generated.ts`는 생성 산출물 성격이므로, 후속으로 실제 generated screens 기준 `sync-preview`를 다시 돌려 정식 경로로 재생성하는 것이 안전합니다.
- `/jobs` alias 파싱 확장 범위가 넓어진 만큼, 프런트 단에서 계약 회귀 테스트(샘플 payload fixture 기반) 추가를 권장합니다.
- `VITE_STUDIO_API_BASE_URL`를 사용하는 배포 시나리오가 있다면 운영 가이드(USER_MANUAL)에도 설정 우선순위를 명시하는 것이 좋습니다.
