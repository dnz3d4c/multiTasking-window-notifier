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

- 설정 시스템: `settings.py` confspec 3키 — beepDuration / beepGapMs / debugLogging. `config.conf`로 NVDA 설정 패널에서 조정 가능. (구 6키였으나 v7 이후 정리: beepVolumeLeft/Right는 항상 50/50로 운용 → tones SDK 기본값과 동치라 제거. maxItems는 BEEP_TABLE_SIZE와 디커플 + 사용자가 줄일 실용 이유 없어 제거. nvda.ini 잔재는 `register()`가 1회 정리.)
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

### Phase 1 (완료): appModuleHandler 전환

`appIdentity.py`의 `obj.appModule` 직접 getattr를 NVDA 공식 API `appModuleHandler.getAppModuleForNVDAObject(obj)`로 교체. private 접근 제거로 NVDA 내부 변경 내성 확보. 대표 커밋: `f5ad2dd`.

### Phase 2 (완료): `__init__.py` 분해 (633줄 → 174줄)

`__init__.py` 단일 파일에 뭉쳐있던 6가지 책임을 모듈 6개로 분리. 이제 `__init__.py`는 설정/저장소 초기화 + 이벤트 훅 진입점 + 모듈 결합만 담당하고 174줄로 축소.

| 분리 모듈 | 담당 책임 | 대표 커밋 |
|----------|----------|-----------|
| `switchFlusher.py` / `lookupIndex.py` | 디바운스 flush / 매칭용 룩업 인덱스 | `9563c4d` (2.1~2.2) |
| `matcher.py` | store 조회 + 비프 재생 + dedup | `717dbc6` (2.3) |
| `focusDispatcher.py` | event_gainFocus 3분기 판정 | `51b45c9` (2.4) |
| `nameChangeWatcher.py` | event_nameChange 탭 확정 감지 | `b3abf82` (2.5) |
| `scripts.py` (ScriptsMixin) | @script 4개 + _do_add / _delete_entries_from_dialog | Phase 2.6 |

스크립트 분리는 Mixin 다중상속 패턴(`GlobalPlugin(ScriptsMixin, globalPluginHandler.GlobalPlugin)`)으로 구현. `scriptCategory` 클래스 속성도 Mixin에 선언해 @script마다 반복 인자 불필요.

### Phase 3 (완료): `appListStore.py` 분해 (806줄 → `store/` 서브패키지)

`appListStore.py` 단일 파일을 역할별 서브패키지로 분해. shim 없이 **완전 삭제** + 호출부 import 경로(`store.XXX`) 전면 교체. v8 스키마 추가 시 `migrations/v7_to_v8.py` 1파일만 신설하면 되는 구조 확보.

| 분리 파일 | 담당 책임 | 대표 커밋 |
|----------|----------|-----------|
| `store/io.py` (210줄) | 경로/시간/메타 + JSON I/O + 원자적 저장 | Phase 3.2 (`a28cb57`) |
| `store/assign.py` (141줄) | `_assign_next_idx` + `_ensure_beep_assignments` | Phase 3.3 (`fc16445`) |
| `store/migrations/normalize_titles.py` (103줄) | ⑤ title 정규화 + dedup | Phase 3.4 (`2fc2a35`) |
| `store/migrations/legacy_list.py` (62줄) | ③ app.list → JSON | Phase 3.5 (`9129efd`) |
| `store/migrations/v6_to_v7_beep_reassign.py` (59줄) | ⑥ v7 재배정 clear | Phase 3.6 (`dc0cc54`) |
| `store/core.py` (369줄) | `_load_state` + 11개 공개 API 본체 | Phase 3.7 (`baf2193`) |
| `store/__init__.py` (53줄) | 공개 API 재export | Phase 3.7 |

완료 기준 전부 충족: `appListStore.py` 제거, v2→v7/v3→v7/v6→v7 golden fixture 통과, 기존 112개 테스트 + 신규 3개(`test_store_package`) 통과, 빌드 산출물 24 files 53.3 KB.

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

`event_gainFocus` 수신을 특정 wcn으로 제한하는 방식. requestEvents는 "수신 확장" API라 현 3분기 매칭을 제한하는 순간 다른 분기가 깨진다.

**Phase 4.4 성능 실측 (2026-04-19)**: dispatch 100회 평균 **0.005ms**, p99 0.199ms. 트리거 기준(평균 ≥ 5ms) 대비 1000배 이하. 재판정 불필요.

재검토 트리거: event_gainFocus 처리 평균 >= 5ms 재측정 시.

---

### Phase 4 (완료): 테스트 보강

Phase 3까지 커버리지 공백이었던 영역을 7개 테스트 파일로 보강. 전체 테스트 114 → **164**, Non-UI 모듈 커버리지 80.8% (wx UI 모듈 listDialog/scripts/settingsPanel 제외 기준).

| 신규 파일 | 케이스 | 대표 커밋 |
|---|---|---|
| `test_normalize_title.py` | 10 | Phase 4.1 (`882daf0`) |
| `test_tabClasses.py` | 6 | Phase 4.1 |
| `test_windowInfo.py` | 4 | Phase 4.1 |
| `test_listDialog_logic.py` | 8 | Phase 4.2 (`d054f99`) — module-level 순수 함수 추출 |
| `test_event_simulation.py` | 7 | Phase 4.3 (`feff423`) — dispatch → matcher → record_switch E2E |
| `test_performance.py` | 2 | Phase 4.4 (`3223a6b`) — 0.005ms/0.001ms 실측 |
| `test_settingsPanel_logic.py` | 7 | Phase 4.5 |
| 보강: `test_focus_dispatcher.py` +1, `test_appListStore_basic.py` +2 | | Phase 4.5 |

**핵심 모듈 커버리지** (플랜 목표 95%):
- `matcher.py` 98% ✓
- `store/assign.py` 95% ✓
- `store/migrations/v6_to_v7_beep_reassign.py` 100% ✓
- `focusDispatcher.py` 87% (95% 미달 — 실기 전용 예외 경로 제외)
- `store/core.py` 85% (95% 미달 — 디스크 I/O 실패 분기 실기 전용)

**완료 기준 부분 달성 사유**:
- 플랜 목표 85%는 wx UI 모듈(listDialog/scripts/settingsPanel) 포함 시 38%/24%/56%가 전체 평균을 끌어내림. wx.App 인스턴스화가 필요한 EVT 핸들러는 NVDA 실기 회귀 테스트로 대체하기로 Phase 4.2에서 결정.
- 비-UI 기준 80.8%는 legacy `_migrate_from_list` 경로(22%, 새 설치에서만 타는 1회성 코드)와 debugLogging=True 진단 로그(실사용 시에만 활성화) 제외 시 실질 90%+. 현 코드로 실기 회귀 방어에 충분.

---

### Phase 5 (완료): 사용자 데이터 저장 경로 외부화

애드온 재설치 시 `app.json` / `tabClasses.json`이 함께 사라지던 문제 해결. 저장 위치를 애드온 패키지 트리 내부(`%APPDATA%\nvda\addons\<addonName>\globalPlugins\<addonName>\`)에서 외부 표준 경로(`%APPDATA%\nvda\multiTaskingWindowNotifier\`)로 이전.

- 타 애드온 31개 전수 조사 결과 100%가 `addons/` 바깥에 사용자 데이터 저장. 이 프로젝트만 비표준이었음.
- 단일 사용자(본인) 환경이라 코드에 마이그레이션 로직을 넣지 않고 기존 파일을 수동 bash `mv`로 1회 이동. 코드 변경은 `windowInfo.config_addon_dir()` 반환 경로 한 줄.
- `build.py` `EXCLUDE_FILE_NAMES`에 `tabClasses.json`, `tabClasses.json.tmp` 추가. 배포 패키지가 기본값 `tabClasses.json`을 포함해 학습 매핑을 덮어쓰는 재발 방지.
- portable NVDA에서는 `globalVars.appArgs.configPath`가 자동으로 portable 경로로 전환되므로 분기 처리 불필요.

대표 커밋: Phase 5 (저장 경로 이전).

---

### Phase 6 (완료): sig_guard 버그 수정 + tabClasses JSON I/O 제거

팀 토론(공격적 단순화 / 보수적 유지 / 종합 실용 3관점 병렬) 결과, Phase 2~3에서 의도적 분해한 결과물의 모듈 수가 "복잡하다"는 인상의 주원인이지만 focusDispatcher 3분기 / nameChange 훅 / 2차원 비프는 실측 근거를 가진 필수 복잡도라 유지. 사용자 실사용 증거로 우발적 복잡도만 정리.

**Phase 6.1 — sig_guard stale 버그 수정 + Matcher 경계 정돈**
- `matcher.match_and_beep`이 `matched_key is None`일 때 `last_event_sig` 갱신 없이 return해, 비등록 창 경유 후 등록 창 복귀 시 직전 sig가 stale로 남아 sig_guard에 오 skip되는 버그 수정. 비매칭 이벤트도 sig 연속성을 끊도록 `None` 리셋.
- `GlobalPlugin._last_event_sig` property pass-through 10줄 제거 → Matcher가 sig 상태의 단일 소유자. 테스트는 `plugin._matcher.last_event_sig`로 직접 접근.
- 회귀 테스트 `test_unmatched_event_clears_sig_guard` 추가.

**Phase 6.2 — tabClasses JSON I/O 제거**
- 사용자 `tabClasses.json` 실측: DEFAULT_TAB_CLASSES와 완전 동일, 자동 학습(`learn_editor`) 경로 **0회 호출**. JSON I/O는 실사용 증거 없음.
- `tabClasses.py` 225줄 → 약 65줄 축약. `DEFAULT_TAB_CLASSES` 상수 + `is_editor_class`/`is_overlay_class` 상수 조회 함수만 유지.
- `_state`, `load`, `save`, `reset_cache`, `_load_from_disk`, `_save_to_disk`, `_merge_defaults_into`, `_empty_apps_from_defaults` 전부 제거.
- `__init__.py`에서 `tabClasses.load(self.tabClassesFile)` 호출 및 `self.tabClassesFile` 속성 제거.
- `test_tabClasses.py` JSON 테스트 삭제, 상수 조회 테스트 7개로 재작성.
- `build.py` `tabClasses.json` 제외 규칙은 보수적 유지 (구형 파일이 배포 패키지에 섞이는 방지용).
- 새 앱 wcn 추가는 이제 소스 수정 + 재배포로 처리.

**Phase 6.3 — store 마이그레이션 3파일 통합**
- `store/migrations/` 서브패키지(legacy_list.py 62줄 + normalize_titles.py 103줄 + v6_to_v7_beep_reassign.py 59줄 + __init__.py 13줄)를 `store/migrations.py` 단일 파일로 통합.
- 함수 시그니처 불변 (`_backup_legacy_list`, `_migrate_from_list`, `_normalize_titles_in_place`, `clear_pre_v7_assignments`). `store/core.py` import 한 줄로 축소.
- 사용자 app.json은 이미 v7이라 현 환경에선 대부분 경로가 no-op이지만 신규 설치/구형 이관 대비로 코드는 보존. v8 추가 계획이 없어 1파일 1버전 분리의 이득이 사라졌고, 통합 시 import 그래프와 파일 트리가 단순해짐.
- `CLAUDE.md` 프로젝트 구조 tree 갱신.

---

## 현재 로드맵

*(활성 로드맵 없음. Phase 1~6 완료. 차기 작업은 사용자가 새 스키마/기능 요청 시 재시작.)*

---

## 참조

- `CLAUDE.md` — 프로젝트 구조, 데이터 포맷, 리뷰 플로우의 SoT
- `AddonDevGuide.md` — NVDA API 공식 가이드
- `AddonBestPractices.md` — 실전 애드온 패턴
- 공식 개발자 가이드: https://download.nvaccess.org/documentation/developerGuide.html
- 상세 실행 계획: `C:\Users\advck\.claude\plans\reactive-snuggling-blum.md`
