# R12 Agent4 Render Policy Handoff

## 1) 구현 내용
- `src/migrator/ui_codegen.py`
  - `auto` 렌더 정책 임계치를 외부에서 주입할 수 있도록 `generate_ui_codegen_artifacts(..., auto_risk_threshold=...)` 인자를 추가했습니다.
  - 임계치 해석 우선순위를 추가했습니다.
    - `auto` 모드: 함수 인자 → `MIFL_UI_AUTO_RISK_THRESHOLD` 환경변수 → 기본값(`0.58`)
    - `strict`/`mui` 모드: 모드 선택에는 영향 없음(인자 전달 시 값만 리포트에 반영)
  - 리포트 판단 근거를 구조화 필드로 확장했습니다.
    - `auto_risk_threshold`
    - `risk_signal_counts` (`total_nodes`, `positioned_nodes`, `fallback_nodes`, `tab_nodes`, `event_attributes`)
    - `risk_signal_scores` (`positioned_nodes`, `fallback_nodes`, `event_attributes`, `tab_nodes`, `total`)
  - `decision_reason`에 신호별 점수 스냅샷을 포함해 운영 시 원인 추적이 쉽도록 보강했습니다.

- `src/migrator/cli.py`
  - `--auto-risk-threshold` 옵션(0.0~1.0)을 `--render-policy-mode` 옵션 세트에 추가했습니다.
  - `gen-ui`, `migrate-e2e`에서 해당 옵션을 `generate_ui_codegen_artifacts`로 전달하도록 연결했습니다.
  - `migrate-e2e` 요약의 `gen_ui` stage에 신규 근거 필드(`auto_risk_threshold`, `risk_signal_counts`, `risk_signal_scores`)를 포함했습니다.

- `tests/test_ui_codegen.py`
  - 기존 `strict`/`mui`/`auto` 테스트에 신규 리포트 필드 검증을 추가했습니다.
  - auto 임계치 오버라이드 회귀 테스트를 추가했습니다.
    - 동일 화면에서 임계치(`0.10`, `0.95`)에 따라 `strict`/`mui` 분기 확인
  - explicit 모드 회귀 테스트를 추가했습니다.
    - `strict`/`mui`는 임계치 값을 받아도 모드 선택이 변하지 않음을 검증

- `docs/TECH_SPEC.md`
  - CLI 계약에 `gen-ui`/`migrate-e2e`의 `--auto-risk-threshold` 옵션을 명시했습니다.
  - UI codegen 리포트 및 migrate-e2e `gen_ui` stage의 신규 정책 근거 필드를 명시했습니다.
  - auto 임계치 소스 우선순위(인자/환경변수/기본값)를 문서화했습니다.

## 2) 수정 파일 목록
- `/Users/biblepark/Desktop/works/miflatform-migrator/src/migrator/ui_codegen.py`
- `/Users/biblepark/Desktop/works/miflatform-migrator/src/migrator/cli.py`
- `/Users/biblepark/Desktop/works/miflatform-migrator/tests/test_ui_codegen.py`
- `/Users/biblepark/Desktop/works/miflatform-migrator/docs/TECH_SPEC.md`
- `/Users/biblepark/Desktop/works/miflatform-migrator/R12_AGENT4_POLICY_HANDOFF.md`

## 3) 실행 테스트/결과
- 실행: `python3 -m unittest tests.test_ui_codegen tests.test_cli`
- 결과: 통과 (`Ran 31 tests`, `OK`)

## 4) 리스크/후속 제안
- 현재 신호별 점수는 가중합 기반 정적 정책(`0.4/0.4/0.1/0.1`)입니다. 운영 데이터가 누적되면 실측 품질지표 기반으로 가중치 재보정이 필요할 수 있습니다.
- `--auto-risk-threshold`는 CLI에서 범위를 강제하지만, 라이브러리 직접 호출 시에도 정책 통일을 위해 호출부 레벨에서 기본값 관리 규칙을 명시하는 것이 좋습니다.
- 필요 시 `tests/test_cli.py`에 신규 옵션(`--auto-risk-threshold`) 파싱/전달 전용 회귀를 추가하면 CLI 계약 안정성이 더 높아집니다.
