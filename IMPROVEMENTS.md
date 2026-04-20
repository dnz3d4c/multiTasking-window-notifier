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

### SFX 기반 프리셋 (synthSpec 모델)

drum_kit / lazer_pack / eight_bit_jump / daily_life / humor_pack 유형. Phase 4~6에서 시도했다가 Phase 7(2026-04-20)에서 전면 철거. 실패 원인은 단일 `synthSpec` 모델이 "짧은 SFX 한 덩이"로 실제 소리(전화벨/박수/방귀)를 근사하려는 접근의 구조적 한계 — 만화풍 근사 / 단일 voice / 옥타브 부재로 반복 변주 불가.

구조 확장(voices layer / AM / cadence)은 "복잡도 억제" 원칙과 정면 충돌. 재도입 시 성공 조건: (1) 다음 2조건 모두 충족하는 프리셋이 최소 3종 이상 제안되고, (2) 3관점 토론(오디오 엔지니어 / SFX 설계자 / 리뷰어+반대자)에서 합의.
- classic 대비 A/B 블라인드 식별 가능 + 하루 100회+ 청취 피로 없음
- TTS formant 대역(200~3000Hz) 에너지 집중 회피

재검토 트리거: 위 조건을 만족하는 구체 설계안이 제시될 때만.

### v9 이전 데이터 자동 마이그레이션 재도입

Phase 10(2026-04-20)에서 v1~v8 자동 승격 경로와 `presets.migrate_deprecated_preset`을 전면 제거했다. 실 환경은 이미 v9로 수렴됐고 마이그레이션 코드는 no-op 상태로 유지 비용만 발생.

재검토 트리거: v10 스키마 변경이 필요할 때만, **1회성 v9→v10 경로 하나만** 도입. v9 이전 경로는 복원 금지.

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

**Phase 6.4 — nameChangeWatcher 조기 컷 (`obj.windowHandle != fg.windowHandle`)**
- 기존 구현은 "창 제목 변경에만 관심"이라는 의도를 `obj_name != fg_name` 문자열 비교로 **우회 표현**. NVDA의 글로벌 `event_nameChange` 훅은 Firefox 북마크 메뉴 항목, DOM 자식 등 임의 accessible 객체의 name 변경까지 전달하는데, 전부 handle 본체까지 들어와 문자열 비교 + `DBG nameChange skip` 로그까지 남겼음.
- `handle` 진입 직후 `obj.windowHandle != fg.windowHandle` 정수 비교로 조기 컷. NVDAObject.`__eq__`가 `Window._isEqual`을 거쳐 결국 windowHandle 비교지만, `type(self) is not type(other)` 첫 단계 때문에 같은 hwnd에 서로 다른 wrapper 클래스(UIA/IA2 등)가 붙은 Firefox 특수 케이스에서 False가 반환될 위험이 있어 hwnd 정수 비교가 더 견고함 (NVDA Addon Dev Specialist 리뷰 권고 반영).
- `obj_name` 추출/비교/`DBG nameChange skip` 로그 제거 (노이즈 근원 소멸). `fg_name` 자체가 empty인 드문 케이스는 `skip-empty-name` 로그로 관찰 유지.
- `obj_hwnd`는 조기 컷에서 이미 추출되므로 이후 `tab_sig` 계산이 재활용 (중복 getattr 제거).
- 회귀 테스트 2개 추가: `test_menu_item_obj_is_cut_before_name_compare` (hwnd 다른 객체가 이름 우연 일치 시에도 cut), `test_fg_identity_allows_match` (같은 hwnd면 정상 매칭).
- 기존 테스트 조정: `test_empty_obj_name_is_skipped` → `test_empty_fg_name_is_skipped`(의미 전환: obj.name 대신 fg.name 기준), `test_invalid_window_handle_falls_back_to_zero` → `test_invalid_window_handle_is_cut`(hwnd 없는 창은 판정 불가 → cut).
- 실기 검증 필요: Firefox Ctrl+Tab / Notepad++ Ctrl+Tab 비프 유지 확인 후 커밋 (NVDA 소스 분석상 이론적 안전성 확보, 실기 실패 시 롤백).

---

### Phase 7 (완료): SCOPE_APP 진입로 정상화 (event_foreground 도입)

`focusDispatcher` 3분기는 모두 "같은 앱 내 탭 전환"용이라 SCOPE_APP entry는 어떤 매칭 분기에도 안 걸려 비프 무음이던 설계 갭 해소.

**근본 원인** (2026-04-19 사용자 디버그 로그로 발견):
- Spotify(SCOPE_APP) 진입 → focusDispatcher 분기 1(Alt+Tab)은 `match_appId=""` 강제로 matcher의 `app_lookup`을 SKIP, 분기 2/3은 tabClasses 미등록 → 매칭 0.
- KakaoTalk(SCOPE_APP+SCOPE_WINDOW) 동일 — title 변동성('KakaoTalk Dialog' ↔ 'ChatDlg - 링키지접근성')으로 SCOPE_WINDOW도 깨짐.
- nameChange는 foreground hwnd 진입 시 title 안 바뀌는 앱(Spotify Premium 등)에서는 미발화.

**해결** — NVDA 내장 `event_foreground` 훅 활용:
- C:/project/ext/nvda/source 조사로 NVDA가 `eventHandler.py:145-148`에서 globalPlugin의 `event_foreground`를 dispatch하고 `IAccessibleHandler/orderedWinEventLimiter.py:66-68`에서 hwnd dedup을 보장함을 확인.
- `_last_fg_hwnd` 직접 추적, 모듈 전역 상태, `_consume_fg_change()` 헬퍼, 4번째 fallback 분기 모두 **불필요** — NVDA 책임으로 이관.
- 신규 모듈 `foregroundWatcher.py` (nameChangeWatcher 동일 패턴, ~70줄): obj.appId/title 추출 → `_match_and_beep` 위임. title=""도 통과 → matcher의 `app_lookup` fallback이 SCOPE_APP 자동 매치.
- `__init__.py`에 `event_foreground` 훅 메서드 추가 (try/except/finally + nextHandler).
- `focusDispatcher`/`nameChangeWatcher` 로직 0줄 수정. docstring만 책임 분리 명시.

**책임 분리 매트릭스**:
| 이벤트 | 모듈 | 트리거 |
|---|---|---|
| event_foreground | foregroundWatcher | foreground hwnd 변경 (앱 간 전환) |
| event_nameChange | nameChangeWatcher | foreground 본체 title 변경 (Ctrl+Tab) |
| event_gainFocus | focusDispatcher | 같은 앱 내 탭/자식 (Alt+Tab 미리듣기, MRU, 에디터 자식 hwnd) |

**검증**:
- NVDA Addon Development Specialist 리뷰 통과 (시그니처/체인/appModule override/obj 신뢰성/Alt+Tab 중복 발화/부팅 직후 fg 5개 항목 검증).
- 기존 168 테스트 전건 PASS (회귀 0건). 빌드 22 files 53.1 KB 성공.
- 실기 검증: Spotify SCOPE_APP / KakaoTalk SCOPE_APP+window / 메모장 SCOPE_WINDOW Ctrl+Tab 정상 비프 확인 필요.

대표 커밋: `1f3363a` (feat) + `fe50568` (chore: settings.json 권한 자동화).

### Phase 8 (완료): v8 aliases — foreground ≠ Alt+Tab 이름 앱 매칭

카카오톡처럼 foreground title("카카오톡")과 Alt+Tab 오버레이 이름("링키지접근성")이 다른 앱을 단일 entry로 매칭하기 위한 aliases 필드 도입. 2026-04-19 사용자 실측 로그로 문제 재확인 후 착수.

**근본 원인**:
- 현재 한 entry는 title 1개만 저장 → 두 경로 중 어느 쪽으로 등록해도 반대 경로에서 매칭 실패.
- focusDispatcher Alt+Tab 분기가 `match_appId=""`를 matcher에 내려 scope=app fallback 자체가 차단됨 (matcher.py:114 `appId and ...`). 즉 scope=app으로 등록해도 Alt+Tab 경로는 못 탐.
- matcher의 title-only 역매핑 분기는 `scope=SCOPE_WINDOW` 하드코딩. scope=app entry가 alias로 잡히면 잘못된 2음 재생.

**Phase 8.1 — 스키마 v8 + 마이그레이션 + 매칭 확장**:
- `store/io.py`: `_new_meta`에 `aliases: []` 기본값 주입(scope 무관). `_load_from_json`에서 aliases 필드 부재/타입 불량 시 [] 보정. `_save_to_disk`에 `"version": 8`.
- `store/migrations.py`: `ensure_aliases_v8(state)` 신규 — source_version < 8이면 모든 entry에 aliases 필드 확보 + dirty=True. 비프 재배정 없음.
- `store/core.py`: `_load_state`에 ⑥' 단계 삽입. 저장 성공 시 `source_version = 8`. legacy app.list 경로 `source_version = 8`로 표시. `set_aliases(path, key, [str])` 공개 API 신규 — entry alias 즉시 원자 저장.
- `lookupIndex.py`: `meta_provider` 콜백 반환을 scope 문자열 → 전체 메타 dict로 변경. `rebuild`에서 scope=window/app 양쪽에 alias 순회 `windowLookup.setdefault(alias, idx)`. scope=app alias도 windowLookup에 주입(Alt+Tab 분기가 appLookup fallback에 도달 못 하므로).
- `matcher.py`: title-only 역매핑 분기에서 `plugin._meta_for(matched_key).get("scope", SCOPE_WINDOW)`로 entry 실제 scope 조회. scope=app alias 히트 시 단음 재생 보장.
- `__init__.py`: `_meta_for` 반환을 dict로. 미사용 SCOPE_WINDOW import 제거.

**Phase 8.2 — 등록/편집 UI**:
- `scripts.py`: `_prompt_for_alias(current_alias="")` 모듈 수준 헬퍼 — `wx.TextEntryDialog`, Cancel→None, OK+빈값→"", OK+값→원문. `script_addCurrentWindowTitle`이 scope 선택 직후 호출, Cancel 시 등록 전체 취소. `_do_add(..., alias="")`에 alias 인자 추가, `normalize_title` 후 `set_aliases` 호출. alias 저장 실패 시 등록 자체는 유지(non-destructive). `_edit_alias_from_dialog(entry)` 신규 — 목록 편집 버튼 콜백. 성공 알림은 f-string 조사 템플릿 대신 `": %s"` 경계로 NVDA 발화 품질 확보.
- `listDialog.py`: `format_display_text(entry, scope, aliases=None)` 꼬리 `(대체: X)` 표시. `AppListDialog`에 `get_meta`, `on_edit_alias` 파라미터 신설(`get_scope`는 하위호환 어댑터). "대체 제목 편집(&E)" 버튼 — 단일 선택 강제. 편집 성공 시 `SetString`으로 해당 행만 즉시 갱신.

**Phase 8.3 — 문서 동기화** (본 커밋):
- `CLAUDE.md`: app.json 예제 v7→v8, aliases 필드 설명, 마이그레이션 체인, 단축키 설명 갱신.
- 본 이력.

**검증**:
- 기존 176 + 신규 13(alias 3 + scripts 10) = 189 테스트 전건 통과.
- Phase 1/2 각각 NVDA Addon Development Specialist 리뷰 통과. Phase 2 Must fix(발화 품질 포매팅) 반영 완료.
- scope=window + alias / scope=app + alias 양쪽 매칭 경로 단위 테스트로 가드.

**매칭 흐름 예시** (카카오톡을 scope=app으로 등록 + alias="링키지접근성"):
1. Alt+Tab 오버레이 → focusDispatcher가 `match_appId="", title="링키지접근성"` 전달.
2. matcher: 정확 매치 실패 → `windowLookup["링키지접근성"]` 히트(scope=app entry idx) → `_meta_for`로 scope=SCOPE_APP 조회 → 단음 재생.
3. 카카오톡 foreground → foregroundWatcher가 `appId="kakao", title="카카오톡"` 전달 → appLookup 히트 → 같은 단음 재생.

대표 커밋: Phase 1(`71bf8e4`), Phase 2(`5a681fb`).

### Phase 9 (완료): normalize_title 파이프라인 확장 — 브라우저 탭 카운트 흡수

브라우저 탭 제목 두 케이스가 매칭 실패하던 문제 해결. 핵심 사용자 요구는 "(N) 카운트가 변해도 같은 창으로 인식".

**문제**:
- `(12) · news_Healing — Mozilla Firefox` — em-dash 미인식이라 입력 그대로 통과 → 12 변동 시마다 다른 키.
- `받은편지함 (79) - advck1123@gmail.com - Gmail — Mozilla Firefox` — em-dash 미인식 + 인라인 카운트 무처리.

**Phase 9.1 — `appIdentity.normalize_title` 4단계 파이프라인**:
- `appIdentity.py`: 함수 시그니처 불변(`name: str -> str`). 호출처 7곳(windowInfo, focusDispatcher, foregroundWatcher, nameChangeWatcher, scripts ×2, store/migrations) 무수정. 모듈 레벨 `_RE_COUNT_TOKEN = re.compile(r"^(\(\d{1,4}\+?\)|\[\d{1,4}\+?\]|\{\d{1,4}\+?\})$")` 1회 컴파일.
  - 1단계 `_strip_dirty_markers` — 선두 `*●◌•` (기존 동작).
  - 2단계 `_strip_app_suffix` — `' — '`(em-dash, U+2014) 1순위, `' - '`(hyphen) 2순위 rsplit. 브라우저는 em-dash, hyphen은 콘텐츠에 흔함.
  - 3·4단계 `_strip_volatile_tokens` — `(N)`/`[N]`/`{N}`/`(N+)` 카운트 토큰 위치 무관 제거 + 선두/꼬리 dangling 구분자(`·`, `•`, `-`, `—`) 정리.
- `tests/test_normalize_title.py`: 신규 13개(브라우저 탭 4 + 카운트 변동 4 + 보존 회귀 4 + helper 단언 9 alternation 포함).

**Phase 9.2 — `app.json` v8 → v9 자동 마이그레이션**:
- `store/migrations.py`: `backup_v8_before_v9(list_path, source_version)` 신규 — `app.json.v8.bak` 1회 백업(이미 존재하면 보존). `renormalize_aliases_v9(state)` 신규 — source_version<9 가드 + 모든 entry aliases 필드를 새 normalize_title로 재처리(빈 결과 드롭).
- `store/core.py`: `_load_state` 단계 ⑥'' 추가. title 재정규화는 매 부팅 호출되는 기존 `_normalize_titles_in_place`가 자동 흡수(dedup 합병 가능). 저장 성공 시 `source_version = 9`. legacy `app.list` 경로 `source_version = 9`로 표시.
- `store/io.py`: `_save_to_disk`의 `"version": 8` → `9`.
- `tests/test_migration_v4.py`: 신규 5개(v8 title 카운트 흡수 + v8 aliases 재정규화 + .v8.bak 생성 + 기존 백업 보존 + 1회성 보장). 기존 8곳 v8 → v9 assertion 일괄 갱신.

**검증**:
- 219 테스트 전건 통과 (기존 211 + Phase 9.1 13 + Phase 9.2 5 + Phase 9.1d alternation 회귀 가드 –10 중복 정리).
- NVDA Addon Development Specialist 리뷰 통과. Critical 0건. 권장 사항 4개(dedup 결과 사용자 안내, 백업 실패 정책, alias dedup, 정규식 alternation) 중 alternation은 즉시 반영(검토포인트 8).
- 비프 매핑 보존(재배정 없음). dedup 합병 시 사용자 데이터는 `.v8.bak`으로 1회 백업되어 롤백 가능.

**설계 토론**: 시니어 프로그래머 안(정규식+명시 룰 테이블) vs UX 전문가 안(휴리스틱+alias 강화). 합의 부분(em-dash 1순위, 시그니처 불변, v9 마이그레이션) 채택, 이메일 자동 마스킹은 비채택(변동값 아님 + 개인정보 보수). 사이트별 룰 테이블도 비채택(새 사이트 = 사용자 alias로 흡수).

대표 커밋: TBD.

---

### Phase 10 (완료): 마이그레이션 코드 전면 제거 — v9 고정 스펙

v1~v9까지 여섯 번의 스키마 전환으로 누적된 마이그레이션 코드를 전면 정리. 사용자 실 환경은 이미 v9로 수렴됐고 legacy 승격 경로(v6↓ 비프 재배정, v7↓ aliases 주입, v8↓ .v8.bak 백업 + aliases 재정규화, app.list 텍스트 → JSON)는 전부 no-op 상태로 유지 비용만 발생. 프리셋 철회 id silent write(`presets.migrate_deprecated_preset`)도 동일 이유로 제거.

**Phase 10.1 — `store` 서브패키지 정리** (커밋 `bcf1954`):
- `store/migrations.py` 324줄 전체 삭제 — `_migrate_from_list`/`_backup_legacy_list`/`_normalize_titles_in_place`/`clear_pre_v7_assignments`/`ensure_aliases_v8`/`backup_v8_before_v9`/`renormalize_aliases_v9` 일괄 제거.
- `store/core.py::_load_state` 7단계 파이프라인 → 3단계로 축약 (캐시 → v9 JSON 로드 → `_ensure_beep_assignments`(누락 필드 보강) → 영구화 → 캐시 등록). `state["source_version"]` 필드 제거.
- `store/io.py::_load_from_json` v9 엄격 모드로 전환 — version!=9 / scope 누락·무효는 전부 `None` 반환으로 "손상" 취급. 반환 튜플 `(items, appBeepMap, version)` → `(items, appBeepMap)` 축소. `_bak_path` dead code 제거. `_new_meta`의 `tabBeepIdx` 파라미터 제거(호출부 전무).
- `store/assign.py` dead import 3개 제거 (`BEEP_TABLE_SIZE`/`BEEP_USABLE_SIZE`/`BEEP_USABLE_START`).

**Phase 10.2 — 프리셋 마이그레이션 제거** (커밋 `65a6b8c`):
- `presets.py`의 `migrate_deprecated_preset` 함수 + `_DEPRECATED_PRESET_IDS` frozenset 삭제. 폐기 id(drum_kit/lazer_pack/eight_bit_jump/daily_life/humor_pack/arcade_pop/coin_dash/glass_step)가 nvda.ini에 남아있어도 `get_preset_or_classic` 폴백이 매칭/재생 시점에 classic으로 흡수 — 런타임 안전성 확증.
- `__init__.py`의 부팅 호출부 + `presets`/`ADDON_NAME` 미사용 import 정리.

**Phase 10.3 — 테스트 정리** (커밋 `999d675`):
- `tests/test_migration_v4.py` 530줄 전체 삭제 (v3→v9 / v4→v9 / v5→v9 / v6→v9 / v7→v9 / v8→v9 체인 14개).
- `tests/test_appListStore_scope.py`의 v2 호환 테스트 3개 삭제. 손상 처리 검증 4개 신규(`test_non_v9_version_is_treated_as_corrupted` / `test_missing_scope_is_treated_as_corrupted` / `test_unknown_scope_value_is_treated_as_corrupted` / `test_save_after_corruption_clears_flag`).
- 전체 202개 테스트 PASS (이전 164개에서 일부 제거·추가).

**Phase 10.4 — 문서 동기화** (본 커밋):
- `CLAUDE.md`: "하위 호환" 7개 bullet 삭제, tree 블록에서 `migrations.py` 제거, `presets.py` 주석에서 `migrate_deprecated_preset` 제거, "하위호환: app.list" 섹션 삭제, "데이터 포맷" 섹션을 v9 고정 + 손상 처리로 재작성.
- `IMPROVEMENTS.md`: 본 완료 이력 + Non-goals에 "v9 이전 마이그레이션 재도입 금지" 명시.

**근거 및 안전망**:
- NVDA Addon Development Specialist 2회 리뷰 통과 (Phase 10.1, 10.2 각각). 차단 이슈 0건.
- 사용자 데이터 보호: v9 외 파일은 `corrupted=True` + 빈 목록으로 시작하며 원본 파일은 덮어쓰지 않음(`_save_to_disk` 호출 차단). `is_corrupted` → `ui.delayedMessage` 안내 경로 유지.
- 재검토 트리거: v10 스키마 변경 필요 시 **1회성 v9→v10 경로만** 도입. v9 이전 경로는 복원 금지 (Non-goals 섹션 참조).

대표 커밋: `bcf1954`, `65a6b8c`, `999d675` + 본 docs 커밋.

---

### Phase R (완료): NVDA 관행 기준 리팩토링 정리

NVDA 소스(`ext/nvda/source/`)와 프로젝트 소스를 교차 탐색해 "NVDA가 보장하는 조건의 중복 방어"와 "관행 일탈"을 근거 기반으로 식별·정리. 대규모 구조 변경 없이 5개 소커밋으로 집중 수정.

- **R0**: `.claude/settings.local.json` 권한 사전 허용 (chore)
- **R2**: gesture identifier 소문자 통일 — `scripts.py` 4곳 + `AddonDevGuide.md` 4곳. NVDA `inputCore.py:922`의 `.lower()` 정규화로 기능 동등.
- **R1**: `beepPlayer._schedule_second_beep` 3단 폴백(core→wx→sync) → `core.callLater` 단일 호출 + `log.exception` 한 겹. NVDA `core.py:1187-1202` 근거로 GlobalPlugin 실행 시점 실패 경로 닫힘.
- **R4b**: `beepPlayer`의 `BEEP_DURATION_MS`/`BEEP_GAP_MS` 모듈 상수 제거, `play_beep`의 `duration`/`gap_ms`를 필수 인자로 전환. `settings.CONFSPEC`을 단일 SoT로 확정.
- **R4a**: `switchFlusher`의 `DEFAULT_FLUSH_EVERY_N=10`, `DEFAULT_FLUSH_INTERVAL_SEC=30`을 `constants.py`로 승격(`FLUSH_EVERY_N_DEFAULT`, `FLUSH_INTERVAL_SEC_DEFAULT`).
- **R3**: `store.prune_stale` 함수 본체 + 테스트 2건 완전 제거(런타임 호출 0건, Phase 8 대비 예비 코드였음). `reset_cache`는 테스트 코드 4개가 명시 참조 중이라 재export는 유지하되 `__all__`에서만 격리. `test_store_package.py`에 `__all__` 드리프트 방지 단언 3개 추가.

**세션 교훈**:
- 플랜의 전제(예: "A 모듈에 이런 코드가 있다")는 실행 에이전트 보고만 믿지 말고 **Read로 직접 재검증**해야 한다. 이번 Phase 1에서 에이전트 한 명이 `beepPlayer` 3단 폴백을 "현 코드에 없다"고 오인 보고해 플랜 검증 단계에서 교정함.
- "NVDA가 이미 보장하는 조건"(core.callLater 안전성, inputCore 정규화, eventHandler dedup)을 재방어하지 않는다 — 상세는 `CLAUDE.md` "개발 시 주의사항" 섹션 참조.
- 시간 가드(예: "0.3초 내 재매칭 skip")로 증상을 가리지 말고 **이벤트 식별자/내용** 기반으로 분기.
- 예비 코드는 남기지 않는다(YAGNI). 실제 Phase 착수 시점엔 신규 설계 가능성이 높다.

대표 커밋: `dd03ffc` (R3) + `3a592c9` (R4a) + `1f482b4` (R4b) + `ee2bfb3` (R1) + `7eb06c2` (R2) + `d5f959b` (R0).

---

### 비프 프리셋 확장 시리즈 Phase 1 (완료)

"비프 소리가 단조롭다 + 8비트/만화풍으로 다양화" 사용자 요구에 대응하는 신규 Phase 시리즈의 첫 단계. 상세 플랜: `C:\Users\advck\.claude\plans\gleaming-drifting-dragonfly.md`.

**변경**:
- `constants.py`: `PRESETS` dict + `CLASSIC_PRESET_ID` 신설. classic(현행 C major 35음), pentatonic(C D E G A × 7옥타브), fifths(완전5도 진행 재배열) 3개. 부팅 시 slotCount/freqs 길이/previewSlots 범위 assert 검증. 기존 `BEEP_TABLE`/`BEEP_TABLE_SIZE`는 classic.freqs 공유 참조로 유지(Phase 3에서 상수 제거 예정).
- `settings.py`: CONFSPEC에 `beepPreset: string(default="classic")` 추가. 기존 `register()` 기본값 주입 경로로 무변경 동작.
- `beepPlayer.py`: `_get_active_preset()`(미지 id 시 classic 폴백 + 1회 log.warning) + `play_preview()` 신규. `play_beep()`가 프리셋 freqs/slotCount 룩업으로 교체. 시그니처/호출부 호환 유지.
- `settingsPanel.py`: `wx.ListBox` + 설명 `wx.StaticText` + "미리듣기(&P)"/"기본값(&D)" 버튼 추가. 기존 SpinCtrl/CheckBox 유지. onSave에 beepPreset 저장. 번역 레이어에서 nameLabel/descriptionLabel `_()` 처리.
- `store/assign.py`: 동작 무변경. 모듈 docstring에 Phase 3 예고(할당공간 128 고정 + modulo wrap) 주석만 추가.

**설계 원칙** (플랜 반영):
- **8비트 본질은 소리 스타일이지 다채널 믹싱이 아님** — 기존 "app음 + tab음 2음 순차"가 사실상 동시 영역을 커버. 다채널 PCM 믹싱은 범위 밖(`voices` 필드/Chord Duet 프리셋 모두 비채택).
- Non-goals: wav 번들, numpy 의존, nvwave.WavePlayer 다중 스트림, 엄숙 모드, 미리듣기 경합 락(Phase 3 이관), `voices` 필드.
- 컨벤션: dict 필드 camelCase, Python 변수 snake_case, 이모지 제거.

**검증**:
- NVDA Addon Development Specialist 리뷰 통과("반드시 수정" 0건, 제안 1건 "settings.get 통일" 반영).
- 빌드: `multiTaskingWindowNotifier-0.9-dev.nvda-addon` 22 files 65.1 KB 성공.
- 기존 169+개 테스트 회귀 검증은 Phase 2 전 실기 확인 단계에서.

**차기**: Phase 2(반복 억제 + 옥타브 변주 플래그), Phase 3(합성 엔진 + 파형 다양화 + slotCount 가변 인프라), Phase 4(synthSpecs 타악/SFX), Phase 5(Daily Life + Humor Pack 옵트인).

### 비프 프리셋 확장 시리즈 Phase 2 (완료)

**반복 억제 + 옥타브 변주**를 프리셋별 플래그로 도입. Pentatonic Calm 기본 on, 그 외 현행 동작 유지.

**변경**:
- `constants.py`: `pentatonic` 프리셋의 `suppressRepeat`/`octaveVariation` 기본값 True. descriptionLabel 보강("같은 창 빠른 재진입 시 탭음 생략 + 옥타브 변주로 반복감 완화").
- `matcher.py`: `Matcher` 클래스에 `_last_matched_key` / `_last_match_time` / `_octave_toggle` 인스턴스 상태 추가. `match_and_beep` 끝부분에 로직 삽입.
  - **반복 억제**: `is_repeat + scope=SCOPE_WINDOW + tab_idx≠None + suppressRepeat + now - last_time < _SUPPRESS_REPEAT_SEC(0.3s)` → `tab_idx=None`(단음).
  - **옥타브 변주**: `is_repeat + scope=SCOPE_WINDOW + tab_idx≠None + octaveVariation` → `_octave_toggle ^= 1` 후 `shift=±7` 적용, 범위 밖은 `[0, slotCount-1]`로 clip(Phase 3에서 modulo wrap 예정).
  - `_active_preset()` 헬퍼: `settings.get("beepPreset")` + `PRESETS.get()` 조회 + classic 폴백.
  - 비매칭 이벤트에서 `_last_matched_key`는 의도적으로 리셋 안 함("미스 창 경유 후 빠른 복귀"도 반복으로 간주). 주석으로 명시.
  - `time.monotonic()` 사용(시계 조정 무관).

**분리된 계층**:
- 기존 `last_event_sig`(NVDA 이벤트 중복 흡수용, tab_sig 포함) — **일체 변경 없음**. 완전 독립 레이어로 공존.
- 반복 억제/옥타브 변주 — 사용자 행동(같은 창 재진입) 기반. 스킵이 아니라 "tab음만 생략" 또는 "변주 적용"이라 sig_guard와 중복 아님.

**검증**:
- NVDA Addon Development Specialist 리뷰 통과("반드시 수정" 0건, 제안 2건 반영: slotCount 직접 참조로 단순화 + 리셋 정책 주석 보강).
- 빌드: `multiTaskingWindowNotifier-0.9-dev.nvda-addon` 22 files 66.7 KB 성공.
- 기존 테스트는 기본 프리셋(classic, 두 플래그 False)에서 돌아가 회귀 없음.

**차기**: Phase 3(합성 엔진 + 파형 다양화 + slotCount 가변 인프라), Phase 4(synthSpecs 타악/SFX), Phase 5(Daily Life + Humor Pack 옵트인).

### 비프 프리셋 확장 시리즈 Phase 3 (완료)

**합성 엔진 도입 + 파형 다양화 + Hybrid 프리셋 3개**. 실무상 slotCount 가변 인프라(할당 공간 `MAX_ITEMS=128` 고정)는 Phase 4로 이관하고 Phase 3는 모든 프리셋 slotCount=35 유지 — modulo wrap이 no-op이라 store 레이어 수정 없이 안전.

**변경**:
- `synthEngine.py` **신규** — 순수 함수 모듈. sine/square(pulse50)/pulse25/pulse12/triangle/saw/noise 7종 파형. precomputed sine LUT(1024) + 위상 누적으로 `math.sin` 호출 제거. 노이즈는 결정론적 `random.Random(str seed)`. 파일 기반 wav 캐시(`tempfile.gettempdir()` 하위 `mtwn_wavcache/`, SHA1 해시 파일명, atomic write). 모듈 dict + `threading.Lock`, maxsize=1024 FIFO. 미지 waveform은 sine 폴백 + 1회 log.warning. `nvwave`/`config`/`settings` import 금지(계층 분리).
- `beepPlayer.py`:
  - `_play_via_synth(freq, duration, waveform)` / `_play_one_beep(freq, duration, waveform)` 헬퍼 추가. synthEngine + `nvwave.playWaveFile(wav_path, asynchronous=True)` 경로. 전 계층 try/except → `tones.beep` 폴백(절대 침묵 금지).
  - `_schedule_second_beep(freq, duration, gap_ms, waveform=None)` 일반화.
  - `play_beep` / `play_preview`가 프리셋 메타의 `waveform` 키 분기. 없으면 기존 tones.beep 경로(classic/pentatonic/fifths 그대로).
  - **시그니처 변경 없음** — 기존 186개 테스트 호환, matcher.py 변경 없음.
- `constants.py` — Hybrid 프리셋 3개 추가, 모두 slotCount=35, freqs는 BEEP_TABLE 공유(음정 동일, 음색만 교체):
  - `arcade_pop` — Pulse 50% 사각파
  - `coin_dash` — Pulse 25% 얇은 사각파
  - `soft_retro` — Triangle 삼각파

**핵심 기술 결정**:
- **`nvwave.playWaveFile`은 파일 경로만 수용** — BytesIO/bytes 거부(NVDA `source/nvwave.py:82-155`의 `os.path.basename(fileName)` 근거). 첫 리뷰에서 Critical로 잡혀 `io.BytesIO` 반환에서 **파일 경로 문자열 반환**으로 전면 교체. 같은 (waveform, freq, duration, sample_rate) 입력 → 결정론적 해시 경로 → 첫 호출만 디스크 I/O, 이후 dict lookup만.
- **"8비트 본질은 소리 스타일"** 원칙 그대로 — 다채널 믹싱/`voices` 필드/`play_preset(preset, …)` 시그니처 변경 전부 도입하지 않음. 기존 2음 순차 구조 유지 + 파형만 교체.

**실측** (NVDA 외 CPython 3.11):
- Cold render (PCM 합성 + 디스크 쓰기): **0.8ms/call** (목표 <5ms 달성)
- Cached hit (dict lookup): **<1μs/call**
- 노이즈 결정성 확인

**검증**:
- NVDA Addon Development Specialist 리뷰 2회차. 1차 리뷰에서 BytesIO→파일 경로 Critical 수정, 2차에서 통과. 경미 제안(`to_wav_bytes` dead code) 반영 — 제거 + `io` import 정리.
- 186 unit 테스트 전건 PASS.
- 빌드: `multiTaskingWindowNotifier-0.9-dev.nvda-addon` 23 files 73.0 KB.
- **실기 검증 필요**: arcade_pop/coin_dash/soft_retro 선택 후 Alt+Tab 비프 청취. tones.beep 폴백 없이 정상 nvwave 재생 확인 필수.

**차기**: Phase 4(synthSpecs + Percussive/Atonal 프리셋 3개), Phase 5(Daily Life + Humor Pack).

### 비프 프리셋 확장 시리즈 Phase 4 (완료 → 2026-04-20 부분 철회)

> **2026-04-20 부분 철회 — 비프 프리셋 확장 시리즈 Phase 7.1~7.3.** Phase 4에서 추가된 신규 프리셋 3종(drum_kit/lazer_pack/eight_bit_jump)과 synthSpecs 스키마·render_spec 경로는 사용자 실사(Phase 4~6 5종 통합) 평가에서 "다 별로" 판정 후 철거.
> 실패 원인 (3관점 토론 결론): (1) 만화풍 근사 한계 — 인지 가능한 실제 소리는 단일 synthSpec 구조로 재현 불가, (2) 단일 voice 모델 — dual-tone/AM/cadence 없이 "진짜처럼" 안 됨, (3) 옥타브 개념 부재로 반복 변주 불가. 상세 Phase 7 참조.
>
> 유지 인프라: `store/assign.py`의 `size=MAX_ITEMS=128` 할당 공간 분리, `beepPlayer.play_beep`의 `effective_idx = stored_idx % slotCount` modulo wrap은 Phase 7 이후에도 남은 프리셋 수 변화 대비로 보존.

**slotCount 가변 인프라 + synthSpecs 스키마 + Percussive/Atonal/Hybrid 프리셋 3개**. Phase 3 6프리셋에 이어 총 9프리셋(기본 포함).

**인프라 변경**:
- `store/assign.py`: `_assign_next_idx` 기본 `size=MAX_ITEMS=128`. `_ensure_beep_assignments` 호출도 동일. 할당 공간을 프리셋 slotCount와 분리 — 항상 0..127, 프리셋 왕복 시 stored idx 보존.
- `store/core.py` / `store/io.py`: stored idx 범위 검증을 `< BEEP_TABLE_SIZE` → `< MAX_ITEMS`로 교체. 기존 사용자 데이터(v8, idx ≤ 34)는 여전히 유효 통과.
- `beepPlayer.play_beep`: 재생 시점 `effective_idx = stored_idx % slotCount` modulo wrap. out-of-range silent/fallback 경로 제거(wrap이 대체). 관련 테스트 2건 의미 업데이트(`test_app_idx_wraps_via_modulo`, `test_tab_idx_wraps_via_modulo`).

**synthSpecs 스키마**:
- 프리셋 dict에 `synthSpecs: list[dict]` (freqs 대안). 각 슬롯 spec: `{kind, waveform, freq, endFreq?, durationMs, envelope?}`. 슬롯별 고유 duration/envelope/portamento.
- `synthEngine.render_spec(spec)` — 파일 캐시 + nvwave 경로. `_render_spec_pcm`가 파형+엔벨로프+포르타멘토 조합 렌더링.
- 엔벨로프 3종: `exp_decay`(타악), `pluck`(어택 5%+감쇠), `boing`(바운스 진동).
- 포르타멘토: spec.endFreq 설정 시 freq → endFreq 선형 보간.
- 부팅 assert: `freqs` 또는 `synthSpecs` 중 하나 필수 + 길이 == slotCount. synthSpecs 프리셋은 `octaveVariation=False` 강제(옥타브 개념 없음).
- `beepPlayer._play_spec` / `_schedule_second_spec`: spec 재생 + tones.beep 폴백(freq=0 방어로 440Hz 기본).

**신규 프리셋 3개**:
- `drum_kit` — Percussive, 8슬롯. kick/snare/hihat_closed/hihat_open/clap/tom_low/tom_high/cymbal. sine+envelope 또는 noise+envelope. 권장 ≤8앱.
- `lazer_pack` — Atonal, 16슬롯. freq 슬라이드 "뾰옹/퓨웅/뽀용" 만화 레이저 효과. pulse25/saw/triangle/square/pulse12 × 상승/하강/bounce. 권장 ≤16앱.
- `eight_bit_jump` — Hybrid, 20슬롯. 10 pulse50 음계(pentatonic C3~A4) + 10 SFX(jump_up/jump_down/shoot/coin/power_up/damage/explosion/bump/star/life_up). 권장 ≤20앱.

**실측**: spec 렌더 0.8~3.2ms cold, 캐시 히트 <1μs. 노이즈 + envelope 결정성 확인.

**검증**:
- NVDA Addon Development Specialist 리뷰 통과. Must fix 2건 반영(lazer_pack recommendedMaxApps 16 정정 + `_play_spec` freq=0 방어) + 개선 S3(synthSpecs는 octaveVariation=False 강제 assert).
- 186 unit 테스트 전건 PASS. 빌드 23 files 76.9 KB.
- **실기 검증 필요**: drum_kit/lazer_pack/eight_bit_jump 각각 선택 후 Alt+Tab 여러 번 눌러 슬롯별 SFX 청취.

**차기**: Phase 5(Daily Life + Humor Pack). 진단 덤프 단축키 / recommendedMaxApps UI 경고는 Phase 5로 이월.

### 비프 프리셋 확장 시리즈 Phase 6 (완료 → 2026-04-20 부분 철회)

> **2026-04-20 부분 철회 — 비프 프리셋 확장 시리즈 Phase 7.2/7.4.** 아래 §3 노이즈 1-pole IIR LPF와 §9 슬롯 축소(daily_life 12슬롯 / humor_pack 8슬롯)는 synthSpecs 프리셋 자체가 철거되며 대상 소멸. `_MAX_SPEC_FREQ=3500` validator도 함께 제거.
> 유지 항목: §1 어택/릴리즈 램프(`_edge_ramp`, `_ATTACK_MS`/`_RELEASE_MS`), §2 파형별 게인(`_WAVEFORM_GAIN`, noise 엔트리만 제거), §5 `beepVolume` 슬라이더(50~150%), §8 `_ENGINE_VERSION=2` 캐시 suffix. 남은 8프리셋에서 계속 효과 발휘.

### 비프 프리셋 확장 시리즈 Phase 6 (완료) — 날카로움/볼륨 완화 + 슬롯 축소

Phase 5 실기 사용 후 사용자 피드백 4건(날카로움/볼륨 문제/실측 데이터 근거 부재/로직 복잡성)에 대응. 3관점 에이전트 팀(사운드 디자이너 Foley 20년 / 접근성 UX / 엔지니어링 회의론자) 재진단 결과 **"전화벨/방귀 등 실제 소리는 단일 synthSpec 구조로 원리적 재현 불가"** 합의. 구조 확장(voices/AM/cadence)은 "복잡도 억제" 원칙 위반 → **재현 불가 슬롯 제거 + 공통 경로 개선 + 볼륨 슬라이더** 방향 전환.

**변경 (synthEngine.py)**:
- §1 어택/릴리즈 램프: `_ATTACK_MS=1`, `_RELEASE_MS=2`, `_edge_ramp()`. 샘플 0에서 ±peak 계단 도약으로 발생하던 클릭/팝 트랜지언트 제거. 짧은 duration(15ms clock_tick 등) 안전 위해 `n_samples // 3` cap + 1/2ms 값으로 본체 손상 최소화.
- §2 파형별 게인 dict: sine 1.0 / triangle 0.95 / pulse50/square 0.55 / pulse25 0.5 / pulse12 0.4 / saw 0.55 / noise 0.6. Crest factor 역보정으로 파형 간 체감 RMS 균일화.
- §3 노이즈 1-pole IIR LPF: `y = y + α*(x - y)`, spec의 `noiseLpfHz`(기본 1200). drum_kit hihat_closed=4000 / hihat_open=3000 / cymbal=5000. `_spec_cache_key`에 cutoff 포함 + 시드 문자열에도 포함해 결정성 유지.
- §5 `volume` 파라미터(50~150%) 전파: `render_wav`/`render_spec`/캐시 키까지.
- §8 `_ENGINE_VERSION=2` 캐시 suffix.
- 리뷰 S2 반영: `amp = min(..., 32767)` clamp + 샘플 레벨 `v = max(-1.0, min(1.0, v))` clamp로 volume=150 + sine/triangle 조합의 int16 OverflowError 방어.

**변경 (settings/beepPlayer/settingsPanel)**:
- `settings.CONFSPEC`에 `beepVolume: integer(default=100, min=50, max=150)`.
- `settingsPanel`에 `wx.Slider`(50~150, SL_HORIZONTAL | SL_VALUE_LABEL). "비프 볼륨 (%)" 라벨. onSave 저장. `_onPreviewClicked`가 slider 현재값을 volume override로 전달(저장 전 즉시 체감).
- `beepPlayer._resolve_volume(None→settings/명시값 override)` 헬퍼. `_play_via_synth`/`_play_spec`/`_play_one_beep`/`_schedule_second_*`에 `volume=None` 추가. `play_beep` 시그니처 유지(matcher 호환) + docstring에 정책 주석. classic(tones.beep 경로)은 volume 무시 — NVDA 내부 볼륨 체계 준수.

**변경 (constants.py) — §9 슬롯 축소**:
- `daily_life` **24 → 12슬롯**. 제거 12: phone_ring/thunder/cat_meow/dog_bark/crow_caw/chicken/cough/sneeze/yawn/clap_double/camera_shutter/desk_bell (모두 단일 synthSpec 구조로 재현 불가 L/X 등급).
- `humor_pack` **16 → 8슬롯**. 제거 8: fart_long/fart_wobble/burp_long/sneeze_loud/cough_loud/snore/tongue_cluck/kiss (fart류 변형 중복 + 생리음 구조적 불가).
- previewSlots 재조정(daily_life (0,3)=doorbell→clap / humor_pack (0,3)=fart_short→boing_fall).
- freq 교정: cricket(5000→3500, duration 50→70) / bird_chirp(endFreq 3000→2400) / cartoon_slip(freq 2000→1400). 모두 §7 `_MAX_SPEC_FREQ=3500` 상한 준수.
- drum_kit cymbal envelope pluck→exp_decay + noiseLpfHz=5000.
- 부팅 assert에 `_MAX_SPEC_FREQ=3500` validator 추가.

**기존 사용자 데이터 호환 (app.json v8)**: stored idx는 [0, 128) 공간. 축소된 프리셋(12/8) 사용 중이면 재생 시점 modulo wrap으로 자동 매핑. 예: daily_life 사용자 15개 앱 등록 → 15 % 12 = 3번 슬롯으로 자연 wrap. 침묵 없음. 단 제거된 phone_ring(원 0번) 자리의 소리가 doorbell로 바뀌는 등 **체감 변화 있음** — 트레이드오프 수용.

**정직한 답변 (사용자 3가지 질문)**:
- "전화기 소리 어떻게?": 단일 synthSpec 구조로 불가(dual-tone+AM+cadence 동시 필요). 제거가 정답. 구조 확장은 Non-goal.
- "방귀 실효과 검증?": 논문(Bharucha 2010)에 주파수 100-200Hz 난류 명시 있으나 saw 주기파로는 재현 불가. fart_short만 대표로 유지.
- "실측 데이터로 구현?": S/A급 근거 있는 슬롯(phone_ring ITU-T, 뻐꾸기 G4→E4 등) 존재하나 단일 synthSpec 한계로 "진짜처럼" 안 됨. 재현 불가 슬롯 제거가 엄밀한 답.

**검증**:
- NVDA Addon Development Specialist 리뷰 통과. 반드시 수정 0건(R1 문서 주석 이슈), 개선 제안 4건 중 S1(어택 램프 5→1ms) + S2(amp clamp) 즉시 반영.
- 186 unit 테스트 전건 PASS. `test_beep_pair.py`의 modulo wrap 테스트는 classic 기준이라 축소 영향 없음.
- 빌드: `multiTaskingWindowNotifier-0.9-dev.nvda-addon` 23 files 81.4 KB.
- **실기 검증 필요**: (a) arcade_pop/coin_dash/soft_retro가 classic 대비 체감 볼륨 유사 (§2 효과), (b) 첫 음 클릭/팝 사라짐 (§1 효과), (c) drum_kit hihat/cymbal이 colored noise로 부드러워짐 (§3 효과), (d) daily_life 12슬롯/humor_pack 8슬롯만 재생 (§9 효과), (e) 설정 패널 비프 볼륨 슬라이더 50/100/150 체감 차이.

**Non-goals 재확인**: voices layer / AM / FM / cadence 확장 / RMS 정규화 / 40슬롯 실측 전수 조사 / 슬롯 이름 rename / `_AMPLITUDE` 전역 하향.

---

### 비프 프리셋 확장 시리즈 Phase 5 (완료 → 2026-04-20 철회)

> **2026-04-20 철회 — 비프 프리셋 확장 시리즈 Phase 7.1/7.4.** 신규 2종(daily_life, humor_pack)과 `humorPackWarningShown` 옵트인 경고 다이얼로그 전부 철거. humorPackWarningShown은 `settings._OBSOLETE_KEYS`에 추가돼 기존 nvda.ini에서 자동 정리.
> 실패 원인: Phase 4와 동일 — 단일 synthSpec 구조의 실제 소리 재현 한계.

**일상 소리 프리셋(Daily Life 24슬롯) + 옵트인 Humor Pack(16슬롯)**. 기본 9프리셋 + 옵트인 1 = 총 11프리셋. 시리즈 완결.

**신규 프리셋**:
- `daily_life` (atonal, 24슬롯, recommendedMaxApps=24, optIn=False): 전화벨/초인종/노크/문닫기/박수×2/휘파람/기침/재채기/하품/시계 째깍/알람/카메라 셔터/물방울/탁상종/뱃고동/고양이/개/새/뻐꾸기/까마귀/닭/귀뚜라미/천둥. 각 슬롯 synthSpec은 pulse50/sine/square/saw/noise + envelope(exp_decay/pluck) 조합. Portamento 활용으로 만화풍 "미끄러지는 느낌" 표현(doorbell E5→C5, cat_meow 600→900, water_drop 400→1200).
- `humor_pack` (atonal, 16슬롯, recommendedMaxApps=16, **optIn=True**): 방귀 3종(short/long/wobble) + 트림 2종 + 딸꾹질 + 큰 재채기 + 큰 기침 + 코골기 + 혀차기 + 뽀뽀 + boing fall + 슬라이드 휘파람(상/하) + "하" 웃음 + cartoon slip.

**1회성 경고**:
- `settings.py` CONFSPEC에 `humorPackWarningShown: boolean(default=False)` 추가.
- `settingsPanel.onSave`에서 **optIn=True 프리셋** 저장 시 플래그 False면 `gui.messageBox`로 1회 경고:
  - 제목: "유머 프리셋 안내"
  - 본문: "이 프리셋은 방귀/트림 같은 유머성 소리를 포함합니다. 회의나 공공장소에서는 다른 프리셋을 선택하시기를 권장합니다."
  - 확인 후 플래그 True 갱신. 재선택 시 조용히 통과.
- NVDA 코어(`gui/settingsDialogs.py:GeneralSettingsPanel.onSave`)의 modal 호출 패턴과 동일 경로 — 접근성/저장 타이밍 검증됨.

**검증**:
- NVDA Addon Development Specialist 리뷰 통과("반드시 수정" 0건, 제안 2건 반영: `wx.MessageBox` → `gui.messageBox` 관용 패턴 + `conf.get` → `conf[key]` 스타일 일관성).
- 186 unit 테스트 전건 PASS. 빌드 23 files 78.5 KB.
- **실기 검증 필요**: daily_life/humor_pack 각각 선택 후 Alt+Tab 청취. humor_pack 첫 선택 시 경고 1회 표시 + 재선택 시 무음 확인.

**Phase 5 범위 축소 결정**:
- 진단 덤프 단축키(NVDA+Shift+B) — YAGNI, 실사용 요청 전 보류.
- `recommendedMaxApps` 동적 UI 경고(현재 등록 앱 수 vs 권장 수 비교) — settingsPanel이 appListFile 경로를 모르는 구조적 한계. descriptionLabel에 "권장 ≤N앱" 이미 정적 명시로 갈음.

---

### 비프 프리셋 확장 시리즈 Phase 7 (완료) — synthSpecs 철거 + 모듈 책임 분리 + tonal 2종 추가

사용자 실사 피드백 "혼합 아케이드부터 다 별로"에 따른 라인업 정리. 다관점 토론(오디오 엔지니어 / SFX 설계자 / NVDA 리뷰어+반대자)으로 "최대 2개, tonal 전용, 축 차별화 필수" 합의 후 실행.

**철거**:
- synthSpecs 프리셋 5종: drum_kit / lazer_pack / eight_bit_jump / daily_life / humor_pack
- synthEngine: `render_spec` / `_render_spec_pcm` / envelope 3종(exp_decay/pluck/boing) / noise 파형 / noiseLpfHz LPF / portamento(endFreq) / amp 필드
- beepPlayer: `_play_spec` / `_schedule_second_spec` / `_warned_preset_ids` 전역 set / synth_specs 분기
- settings: `humorPackWarningShown` CONFSPEC 키 (`_OBSOLETE_KEYS` 경로로 nvda.ini 자동 청소)
- settingsPanel: humor_pack 경고 다이얼로그, `_TYPE_CATEGORY_LABELS`의 percussive/atonal, "(옵트인)" 접미사

**추가 — tonal 2종**:
- `moss_bell` (tonal, sine) — A 자연단음계 7음 × 5옥 = 35. A2(110Hz)~G7(3136Hz). 정서축(애조) 신규.
- `glass_step` (hybrid, saw) — whole-tone 6음 × 6옥-1 = 35. C2(65Hz)~G#7(3322Hz). 파형축(saw) + 음정구조축(whole-tone) 동시 신규.

**모듈 책임 재설계**:
- 신규 `presets.py` — 프리셋 데이터 단일 소유자. `PRESETS` / `CLASSIC_PRESET_ID` / freqs 빌더 / 부팅 assert / 폴백(`get_preset_or_classic`) / 폐기 감지(`is_deprecated`) / 마이그레이션(`migrate_deprecated_preset`) 전부 포함.
- 의존 방향: `presets.py → constants.py` 단일. settings/beepPlayer/synthEngine 역참조 없음.
- beepPlayer/matcher의 `_warned_preset_ids` 이중 가드 제거 — presets가 단일 소유.
- obsolete 키 청소는 `settings._OBSOLETE_KEYS` 단일 경로 (기존 3종과 동일 메커니즘).

**Phase 세분화 및 커밋**:

| Phase | 커밋 | 요약 |
|------|------|------|
| 7.1 | `55f985b` | presets.py 신설 + synthSpecs 5종 철거 + import 경로 교체 + `__init__.py`에 migrate 호출 |
| 7.2 | `243c06b` | synthEngine render_spec 경로 제거 (YAGNI) |
| 7.3 | `4246467` | beepPlayer synthSpec 분기 철거 + presets API 위임 (matcher도 동일 정렬) |
| 7.4 | `8c121c6` | humorPackWarningShown + percussive/atonal 카테고리 제거 |
| 7.5 | `17b724e` | moss_bell + glass_step 추가 |
| 7.6 | (본 커밋) | 문서 동기화 |

**사용자 저장값 마이그레이션**: `GlobalPlugin.__init__`에서 `settings.register()` 직후 `presets.migrate_deprecated_preset(config.conf[ADDON_NAME])` 호출. 폐기 프리셋 id가 저장돼 있으면 classic으로 silent write + 1회 log.warning. 멱등.

**검증**:
- 각 Phase 커밋마다 NVDA Addon Development Specialist 리뷰 통과. Phase 7.1에서 `migrate_deprecated_preset` 호출부 누락 + None 타입 방어 지적 반영. Phase 7.5에서 `glass_step` previewSlots 인덱스 오류(18→21) 지적 반영.
- `uv run python build.py` 각 Phase 성공. 최종 `multiTaskingWindowNotifier-0.9-dev.nvda-addon` 24 files.
- 실기 검증 필요: NVDA 재설치 → 설정 > 창 전환 알림 ListBox 8개 확인 → moss_bell/glass_step 미리듣기 → Alt+Tab 실사용.

**Non-goals 추가**: SFX 기반 프리셋(atonal/percussive) — Phase 4~6 5/5 실패로 확장 비용 대비 이득 수렴. synthSpec 모델은 단일 voice 한계가 본질적이라 재시도 시 구조 변경(voices/AM/cadence) 필수 → 복잡도 억제 원칙과 충돌.

---

### 비프 프리셋 확장 시리즈 Phase 8 (완료) — 날카로운 hybrid 3종 철회

사용자 실사 피드백 "아케이드/코인/글래스 제거해. 다 소리가 날카롭다". arcade_pop(pulse50) / coin_dash(pulse25) / glass_step(saw) 3종 제거. 배음 밀도가 높은 파형 계열 전반이 TTS 공존 환경에서 날카로움으로 판정됨. 남는 hybrid는 soft_retro(triangle) 한 종.

**철거**:
- 프리셋 3종: `arcade_pop` / `coin_dash` / `glass_step`. `_WHOLE_TONE_FREQS` 리스트도 미사용으로 같이 제거.
- synthEngine 파형: `_gen_square` / `_gen_pulse25` / `_gen_pulse12` / `_gen_saw` + `WAVEFORMS`의 square/pulse50/pulse25/pulse12/saw 엔트리. `_WAVEFORM_GAIN`에서 해당 5종 엔트리 제거(sine/triangle만 유지).
- `_DEPRECATED_PRESET_IDS`에 3종 추가 → 기존 사용자 `beepPreset` 값이 이 셋 중 하나면 `classic`으로 silent 마이그레이션.

**최종 라인업 5종**: classic / pentatonic / fifths / soft_retro / moss_bell.

**남은 synthEngine 파형**: triangle(soft_retro가 사용) + sine(미지 파형 폴백).

**원칙 근거**:
- Phase R3 YAGNI — "실사용 없는 예비 코드는 남기지 않는다". pulse/saw 계열을 쓰는 프리셋이 0이 된 시점에 파형 구현체도 같이 제거.
- 모듈 책임 분리(Phase 7 원칙) — 사용자 지시는 "프리셋 제거"였지만 synthEngine이 "하위 의존"이라 dead code를 같이 정리하지 않으면 다시 산재.

**검증 예정**:
- NVDA Addon Development Specialist 리뷰 통과 필요.
- `uv run python build.py` 성공.
- 실기: NVDA 재설치 → ListBox 5개 확인 → 기존 저장값 `beepPreset=arcade_pop/coin_dash/glass_step` 환경이면 classic 폴백 + 로그 경고 1회.

---

## 현재 로드맵

*(활성 로드맵 없음. 비프 프리셋 확장 시리즈 Phase 1~8 완료. 총 **5프리셋** 운영 — classic / pentatonic / fifths / soft_retro / moss_bell. 차기 작업은 사용자 요청 시 재시작.)*

---

## 참조

- `CLAUDE.md` — 프로젝트 구조, 데이터 포맷, 리뷰 플로우의 SoT
- `AddonDevGuide.md` — NVDA API 공식 가이드
- `AddonBestPractices.md` — 실전 애드온 패턴
- 공식 개발자 가이드: https://download.nvaccess.org/documentation/developerGuide.html
- 상세 실행 계획: `C:\Users\advck\.claude\plans\reactive-snuggling-blum.md`, `C:\Users\advck\.claude\plans\groovy-tickling-reddy.md` (Phase 8 aliases)
