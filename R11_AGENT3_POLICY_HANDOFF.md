# R11_AGENT3_POLICY_HANDOFF

## 1) 구현 내용
- `ui_codegen`에 렌더 정책 엔진을 도입했습니다.
  - 지원 모드: `strict`, `mui`, `auto`
  - API 시그니처 확장: `generate_ui_codegen_artifacts(..., mode: UiRenderPolicyMode = "mui")`
- `strict` 모드 구현:
  - 화면/위젯 렌더를 MUI 컴포넌트 우선 경로가 아닌 저수준 HTML 태그 우선 경로로 분기
  - 위젯 shell도 `Box` 대신 `div` 기반으로 렌더링
- `mui` 모드 구현:
  - 기존 MUI 중심 고수준 렌더 경로를 유지
- `auto` 모드 구현:
  - AST 기반 리스크 신호(좌표 배치 노드 비율, fallback 위젯 비율, 탭 구조, 이벤트 밀도)로 `risk_score` 계산
  - 임계치(0.58) 이상이면 `strict`, 미만이면 `mui` 선택
  - 선택 사유(`decision_reason`) 문자열에 신호 스냅샷/임계치 기록
- 코드젠 리포트 확장:
  - `UiCodegenReport`에 아래 필드 추가
    - `requested_mode`
    - `mode` (실제 적용 모드)
    - `decision_reason`
    - `risk_score`
- CLI 인자 경유 모드 선택 지원:
  - `gen-ui`: `--render-policy-mode {strict,mui,auto}`
  - `migrate-e2e`: `--render-policy-mode {strict,mui,auto}`
- `migrate-e2e` stage 리포트(`stages.gen_ui`)에 정책 결정 정보 반영:
  - `requested_mode`, `mode`, `decision_reason`, `risk_score`

## 2) 수정 파일 목록
- `/Users/biblepark/Desktop/works/miflatform-migrator/src/migrator/ui_codegen.py`
- `/Users/biblepark/Desktop/works/miflatform-migrator/src/migrator/cli.py`
- `/Users/biblepark/Desktop/works/miflatform-migrator/tests/test_ui_codegen.py`
- `/Users/biblepark/Desktop/works/miflatform-migrator/R11_AGENT3_POLICY_HANDOFF.md`

## 3) 실행 테스트/결과
- 실행 명령:
  - `python3 -m unittest tests.test_ui_codegen tests.test_cli`
- 결과:
  - `Ran 29 tests in 0.091s`
  - `OK`

## 4) 리스크/후속 제안
- 리스크:
  - `auto` 리스크 스코어는 휴리스틱 기반이라, 실제 프로젝트 XML 분포에 따라 임계치(0.58) 튜닝 필요 가능성 있음
  - `strict` 경로는 저수준 렌더 우선 전략으로 도입했으나, 시각/상호작용 fidelity는 샘플군별 확인이 추가로 필요
- 후속 제안:
  1. 실데이터 셋으로 `auto` 모드 선택 분포(`strict`/`mui`)를 수집해 임계치 재보정
  2. `tests/test_cli.py`에 `--render-policy-mode` 명시 호출 케이스(특히 `auto`)를 추가해 CLI 회귀를 고정
  3. 필요 시 정책 엔진을 설정 파일(예: 임계치/가중치 외부화)로 분리해 하드코딩을 추가로 축소
