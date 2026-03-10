# R14 Refactor Master Plan

## 1. 목적

레거시 MIPLATFORM XML 대량 변환 프로젝트를 다음 기준으로 재정렬한다.

1. 누락 없는 파싱/변환 증명 가능성 강화
2. 대규모 실무 운영에 맞는 프로젝트 단위 산출물 관리
3. 데스크톱 GUI 중심 운영 UX 고도화
4. 변환 정확도(좌표/크기/동작)와 현대화(MUI)의 선택적 균형

---

## 2. 현재 상태 점검 (요구사항 1~7 매핑)

### 2.1 요구사항별 상태

1) 대량 XML 배치 처리
- 상태: 부분 충족
- 근거: 폴더 선택/배치 큐/실행/취소/재시도/히스토리 가능
- 갭: 산출물이 run/item 단위로 분산되어 후속 개발 소비 관점에서 불편

2) UI/API 분리 산출
- 상태: 충족
- 근거: `parse -> map-api -> gen-ui -> fidelity-audit -> sync-preview -> preview-smoke` 체인 구현
- 갭: API/화면 산출물을 프로젝트 단위로 일관 집계하는 계약이 약함

3) 누락 없는 변환 + 감사/로그/리포트
- 상태: 부분 충족
- 근거: strict parse gate, roundtrip/canonical gate, fidelity audit, runtime wiring coverage, report_view 존재
- 갭: "미지원 태그/속성/이벤트"를 프로젝트 레벨에서 누적 추적하고 차단 정책으로 운영하는 레이어 부족

4) 동일 최종 폴더로 반복 작업 시 집계 저장
- 상태: 부분 충족
- 근거: 동일 output root 하위 run history는 조회 가능
- 갭: 명시적 project 개념(프로젝트명/ID/manifest/활성 산출물)이 없음

5) 다양한 XML 구조 유연 대응
- 상태: 부분 충족
- 근거: fallback 렌더, 태그 매핑 확장, grid expression 일부 지원
- 갭: 태그/속성 핸들러가 단일 대형 모듈에 밀집되어 확장성/회귀 제어가 어려움

6) 대형 미리보기 화면
- 상태: 부분 충족
- 근거: 데스크톱 preview 탭 + 임베드 웹뷰 + 확장된 캔버스
- 갭: 전용 fullscreen preview 워크스페이스/뷰포트 고정 정책 미흡

7) MUI 적용 시 겹침/깨짐 최소화 + 원본 좌표 충실
- 상태: 부분 충족
- 근거: `strict|mui|auto` 렌더 정책, 절대 좌표 스타일 반영, grid band 분리
- 갭: 자동 정책이 화면/컨테이너 단위 미세 전환을 못함 (현재 screen-level 휴리스틱 중심)

### 2.2 기술 부채 (핵심)

- 데스크톱 엔트리포인트 이원화
  - `src/migrator/desktop_app.py` (실사용)
  - `src/migrator/desktop/*` + `desktop-shell` (초기 foundation)
- `ui_codegen.py` 단일 파일 과대(관심사 분리 필요)
- 프로젝트 단위 artifact registry 부재
- preview-host registry 경로 드리프트 리스크
  - 실제 점검 시 `preview-host` 빌드 실패 확인
  - 원인: `preview-host/src/screens/registry.generated.ts`가 임시 절대 경로 import 포함

---

## 3. 점검 결과 요약 (2026-02-23)

- Python 전체 테스트: PASS (`Ran 128 tests`)
- preview-host build: FAIL
  - 오류 파일: `preview-host/src/screens/registry.generated.ts`
  - 증상: 임시경로 import (`/private/var/.../generated-ui/...`) 잔존

의미:
- 코어 변환 파이프라인의 테스트 커버리지는 양호
- 그러나 "운영 미리보기 안정성"은 생성물 드리프트 방지 계약이 추가로 필요

---

## 4. 목표 아키텍처 (Project-Centric V2)

### 4.1 프로젝트 단위 워크스페이스

권장 구조:

- `<output_root>/projects/<project_key>/project.json`
- `<output_root>/projects/<project_key>/runs/<run_id>/...`
- `<output_root>/projects/<project_key>/artifacts/frontend/...`
- `<output_root>/projects/<project_key>/artifacts/api/...`
- `<output_root>/projects/<project_key>/reports/...`
- `<output_root>/projects/<project_key>/preview-workspace/...`

핵심 원칙:

- 실행 격리(run/item)는 유지
- 소비 산출물(frontend/api/reports)은 프로젝트 단위로 집계
- 집계 전략은 충돌 안전 규칙 적용
  - 기본: 화면/트랜잭션 키 중복 시 버전 suffix 또는 latest alias
  - 모든 덮어쓰기/충돌은 `project.json`에 이력 기록

### 4.2 정책 엔진 2단계화

- Stage A: screen-level 정책(`strict|mui|auto`)
- Stage B: container/node-level 재평가(밀집 영역 strict 강제)

산출:
- policy decision trace를 node_path 단위로 리포트화
- "왜 MUI/strict가 선택되었는지"를 근거값과 함께 남김

### 4.3 완전성 증명 레이어 강화

프로젝트 단위 `coverage-ledger.json` 신설:
- 태그/속성/이벤트 총량
- 지원/미지원/대체(fallback)/무시(meta) 분류
- strict 차단 정책 결과
- 라운드별 추세(감소/증가)

---

## 5. 리팩토링 라운드 계획

## R14 (Stabilize + Architecture Baseline)

목표:
- 운영 흔들림 제거 + 구조 리팩토링 착수

작업:
1. preview-host registry 드리프트 방지
2. 데스크톱 진입점 단일화
   - `desktop-shell`과 `desktop_app`의 실행 경로 통합
3. Project Workspace 데이터모델 도입 (읽기/쓰기 최소 계약)
4. 기존 경로 하위 호환(shim) 유지

완료 기준:
- preview-host build 재통과
- 데스크톱 GUI 실행 경로 1개로 수렴
- 신규 project manifest 생성 및 history 연동 가능

## R15 (Artifact Consolidation + UX)

목표:
- 사용자 관점 핵심 가치: "결과물 한곳에 모으기" 실현

작업:
1. run/item 산출물 -> project artifacts 집계기 구현
2. GUI에서 프로젝트명/프로젝트 선택/생성 지원
3. history를 프로젝트 경계로 조회
4. preview를 프로젝트 단위 workspace 기반으로 동작

완료 기준:
- 동일 프로젝트로 여러 batch 실행 시 산출물이 일관 집계
- 다른 프로젝트는 완전 분리

## R16 (Completeness Proof 강화)

목표:
- "누락 없음"을 수치/근거로 설명 가능하게 만들기

작업:
1. coverage ledger + unsupported inventory 통합 리포트
2. strict 정책 레벨화
   - warn-only / gate / block
3. 실패 원인 분류 체계 표준화(파싱/매핑/렌더/동작)

완료 기준:
- 실패 케이스별 근거가 GUI와 JSON에서 동일하게 조회
- KPI 게이트(누락/미지원/미해결) 수치화

## R17 (UI Fidelity 고도화)

목표:
- 겹침/깨짐 감소, 복잡한 대형 화면 재현력 향상

작업:
1. 컨테이너/노드 단위 hybrid policy
2. layout drift score 계산 + 자동 strict fallback
3. grid 렌더 심화 (band/span/expr/summary 검증 강화)
4. preview fullscreen 모드 + 1:1 viewport 점검 도구

완료 기준:
- 실샘플 기준 fidelity risk 지표 개선
- 대형 관리자 화면의 읽기 가능성/정렬 안정성 향상

---

## 6. 병렬 작업 레인 제안 (5-agent)

1. Core Architecture
- project workspace 모델/계약
- 경로 하위호환 shim

2. Desktop UX
- 프로젝트 선택/생성
- artifacts/hierarchy browser
- fullscreen preview UX

3. Codegen Policy
- hybrid policy 엔진
- node-level decision trace

4. Fidelity/QA
- coverage ledger
- strict 레벨 정책 + 게이트
- 회귀 테스트 강화

5. Preview/Integration
- preview registry 안정화
- preview-host build/smoke 자동 점검

---

## 7. 즉시 우선순위 (다음 실행 단위)

P0:
1. `registry.generated.ts` 절대경로 드리프트 방지
2. desktop entrypoint 단일화

P1:
3. project key/manifest 도입
4. artifacts consolidation MVP

P2:
5. coverage ledger MVP
6. hybrid render policy MVP

---

## 8. 운영 KPI (라운드 종료 게이트)

- 변환 성공률 (batch 기준)
- unsupported tag/attr/event 비율
- fidelity risk count
- preview unresolved module count
- 프로젝트 artifacts 집계 성공률
- 재시도 후 회복률

