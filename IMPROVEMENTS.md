# multiTaskingWindowNotifier 진화 이력 + 로드맵

이 파일은 "할 일 나열"이 아니라 "프로젝트 진화 연대기 + 현재 로드맵"이다.
구성: 완료 이력 → Non-goals(명시적 보류) → 현재 로드맵 → 참조.
신규 기여자는 "현재 로드맵" 섹션부터 읽으면 된다.

---

## 프로젝트 목적

NVDA 스크린 리더 애드온. Alt+Tab/Ctrl+Tab 창 전환 시 등록된 창마다 다른 비프음을 재생해 창을 청각적으로 구분하고 전환 속도를 높인다. 앱 단위(a 단음)와 창/탭 단위(a→b 2음) 2계층 등록을 지원한다. 구조·데이터 포맷·단축키 상세는 `CLAUDE.md` 참조.

---

## 완료 이력

### Phase A (v1~v3): 기본 골격

- 설정 시스템: `settings.py` confspec 6키 — beepDuration / beepGapMs / beepVolumeLeft / beepVolumeRight / maxItems / debugLogging. `config.conf`로 NVDA 설정 패널에서 조정 가능.
- GUI 설정 패널: `settingsPanel.py` SettingsPanel 구현. NVDA 설정 대화상자 "창 전환 알림" 패널.
- 로깅: 전역 log 호출 65개. 마이그레이션/매칭/폴백 흐름 추적 가능.
- 대표 커밋: `5482180` — "설정/저장소/GUI 패널을 GlobalPlugin에 통합 (Phase 1~3)"

### Phase B (v4~v6): 2차원 비프 + 3분기 매칭

- 앱/창 2계층 scope 도입: `SCOPE_APP`(appId 단독키, a 단음) / `SCOPE_WINDOW`(appId|title 복합키, a→b 2음). 매칭 우선순위 창>앱. 대표 커밋: `263b965`.
- 비프 2음 구조: `beepPlayer.play_beep(app_idx, tab_idx, scope)`. core.callLater 기반 gap 예약. 대표 커밋: `f290cbb`.
- `event_gainFocus` 3분기: (1) Alt+Tab 오버레이 wcn 고정 / (2) 앱별 overlay wcn / (3) editor 자식 컨트롤 wcn. 모든 title은 `normalize_title` 통과.
- 음성 우선순위: `speech.Spri` 적용. 즉시 알림은 `Spri.NOW`, 일반은 `Spri.NEXT`. 대표 커밋: `51cef3d`.
- `enableAllWindows` 설정 제거: 3분기가 주요 시나리오를 모두 커버. 미커버 앱은 NVDA+Shift+T로 editor wcn 학습이 정규 경로.
- 단축키 `@script` + `category` 한글("창 전환 알림")로 통일.
- `listDialog.py` guiHelper 부분 적용 — 대표 커밋: `f94c098`.

### Phase B' (v7): C major 온음계 전환

반음 64음 테이블(v6)을 C major 온음계 35음(C3 130Hz~B7 3951Hz)으로 교체했다. 배경은 사용자 피드백: "반음 간격은 인접 슬롯 변별이 약하다". 온음계로 바꾸면 1번(도)과 2번(레)이 전음 간격으로 분리돼 청각 구분이 명확해진다.

인덱스 의미 자체가 달라지므로 로드 시 기존 appBeepMap/tabBeepIdx를 전부 버리고 순차 재배정한다. 1회성 자동 마이그레이션. 사용자는 주파수 재학습 필요.

`event_nameChange` 기반 탭 전환 감지도 이 단계에서 도입됐다. 대표 커밋: `ae2e862`.

### 대체 완료

- **browseableMessage 목록 표시** (구 2.1): `listDialog.py` wx.Dialog로 대체. 다중 선택 + Delete 키 + 앱 일괄 삭제 확인까지 지원해 browseableMessage(읽기 전용 HTML)보다 기능적으로 우위. 재판정 대상 아님.
- **비프음 테이블 커스터마이징** (구 3.2): v7 C major 온음계 고정 채택 (커밋 `ae2e862`). "변별력 우선" 결정이라 사용자 정의 등비수열은 역효과. 재판정 대상 아님.
- **windowClassName 고정 조건** (구 1.4): Phase B 3분기로 대체. `enableAllWindows` 제거. 종료.
- **단축키 카테고리 한글 통일** (구 2.3): Phase B에서 완료.
- **guiHelper 다이얼로그 개선** (구 2.4): `listDialog.py`에 guiHelper 적용 완료 (커밋 `f94c098`).

---

## Non-goals (명시적 보류)

아래 항목은 "아직 안 한 것"이 아니라 "하지 않기로 결정한 것"이다. 재검토 트리거가 충족되지 않는 한 구현 시도 금지.

### #3 창 그룹/프로필

업무/개발/개인 프로필별 app.json 분리. 사용자 보류 결정 (`__init__.py:6` 메모 참조). 단일 저장소 철학과 충돌하고 마이그레이션 복잡도가 크다.

재검토 트리거: 사용자가 명시적으로 다시 꺼낼 때만.

### #9 통계 기능

일/주간 전환 집계 UI. 사용자 보류 결정 (`__init__.py:7` 메모 참조). `switchCount` 메타 수집은 유지하되 집계 UI는 만들지 않는다.

재검토 트리거: 사용자 요청.

### 3.3 requestEvents 최적화

`event_gainFocus` 수신을 특정 wcn으로 제한하는 방식. 현재 지연 실측 수치가 없다. requestEvents는 "수신 확장" API라 현 3분기 매칭을 제한하는 순간 다른 분기가 깨진다.

재검토 트리거: Phase 4 성능 측정에서 event_gainFocus 처리 평균 >= 5ms 확인 시.

---

## 현재 로드맵

### Phase 1 — appModuleHandler 전환

`appIdentity.py`의 `obj.appModule` 직접 getattr를 NVDA 공식 API `appModuleHandler.getAppModuleForNVDAObject(obj)`로 교체한다. `obj.appModule`은 private 접근이라 NVDA 내부 변경에 취약하다.

완료 기준:
- `obj.appModule` 직접 접근 0건
- 테스트 Green
- 기존 `app.json` appId 키 변화 없음

참조: `globalPlugins/multiTaskingWindowNotifier/appIdentity.py:9-19`

### Phase 2 — `__init__.py` 분해 (633줄 → 180줄)

현재 `__init__.py`가 설정 등록 / 이벤트 훅 / 스크립트 / 매칭 / 플러시 / 다이얼로그 6가지 책임을 혼재한다. 신규 모듈 6개로 분리:

- `focusDispatcher.py` — event_gainFocus 진입점, 3분기 라우팅
- `matcher.py` — appListStore 조회, 매칭 로직
- `lookupIndex.py` — 메모리 캐시 인덱스 (dedup 가드 포함)
- `nameChangeWatcher.py` — event_nameChange 기반 탭 전환 감지
- `scripts.py` — @script 핸들러 4개
- `switchFlusher.py` — 디바운스 flush 타이머

완료 기준: `__init__.py` <= 180줄, 각 모듈 <= 150줄, 순환 import 없음, 모든 단축키 회귀 없음.

### Phase 3 — `appListStore.py` 분해 (806줄 → 400줄)

`store/` 서브패키지 도입. v8 마이그레이션 추가 시 `migrations/v7_to_v8.py` 1파일만 신설하면 되는 구조.

서브 모듈:
- `store/core.py` — 공개 API (load/save/record_switch/flush 등)
- `store/io.py` — 파일 I/O, 원자적 저장
- `store/assign.py` — 비프 인덱스 할당 알고리즘
- `store/migrations/` — 버전별 마이그레이션 함수

완료 기준: `appListStore.py` 제거, v2→v7 / v3→v7 / v6→v7 golden fixture 3경로 byte-for-byte 동일.

### Phase 4 — 테스트 보강

현재 커버리지 공백: `listDialog.py` 0%, `event_nameChange` 시나리오 없음, 성능 수치 없음.

신규 테스트 파일:
- `test_list_dialog.py` — 다중 선택, Delete 키, 앱 일괄 삭제 확인 흐름
- `test_name_change.py` — event_nameChange 탭 전환 시나리오
- `test_perf_focus.py` — event_gainFocus 처리 시간 측정 (Non-goals 3.3 트리거 데이터)
- `test_phase1_appmodule.py`, `test_phase2_dispatch.py`, `test_phase3_store.py`, `test_phase4_integration.py` — 각 Phase 회귀 테스트

완료 기준: 커버리지 85%+. 성능 수치는 Non-goals 3.3 requestEvents 재검토 트리거로 사용.

---

## 참조

- `CLAUDE.md` — 프로젝트 구조, 데이터 포맷, 리뷰 플로우의 SoT
- `AddonDevGuide.md` — NVDA API 공식 가이드
- `AddonBestPractices.md` — 실전 애드온 패턴
- 공식 개발자 가이드: https://download.nvaccess.org/documentation/developerGuide.html
- 상세 실행 계획: `C:\Users\advck\.claude\plans\reactive-snuggling-blum.md`
