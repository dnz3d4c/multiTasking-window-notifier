# *중요* 대화 원칙
- *중요* 불필요한 메타 발언 자제
- 명시하지 않는한 이모지 사용 자제
- 장황하게 설명하지 않고 핵심과 주요 포인트만 설명
- 코드 전문가가 아니므로 어려운 개념, 코드 등은 일반인 입장에서 자세히 설명, 이러한 케이스 발생시 자세한 설명 가능.
# *중요* 응답 속도 최적화
- **간결한 응답**: 이미 "장황하게 설명하지 않기" 원칙이 있으므로 더욱 준수. 코드 변경 후 긴 설명 불필요
- **파일 읽기 최소화**: 이미 읽은 파일은 다시 읽지 않기. 필요한 부분만 offset/limit로 읽기
- **병렬 작업**: 독립적인 파일 수정은 한 번에 여러 Edit 호출
- **명확한 요청**: 사용자가 구체적으로 요청하면 불필요한 확인 단계 생략 가능
# *중요* 구현 후 필수 리뷰

`globalPlugins/**/*.py` 또는 `manifest.ini` 수정 후 "완료" 선언 전 아래 절차를 반드시 수행.

1. `@NVDA Addon Development Specialist` 에이전트로 변경된 파일을 리뷰
   - NVDA API 사용 적절성, 이벤트 훅 안정성(`event_gainFocus`는 모든 포커스 전환마다 호출됨 → 성능/예외 처리 필수)
   - 스크린리더 접근성, 번역(`_()`) 누락, 설정(`config.conf`) 스키마 일관성
2. 리뷰 지적사항 수정 후 재리뷰 (동일 지적 반복 방지 위해 최대 2회)
3. 리뷰 통과 시 **반드시 `uv run python build.py` 실행** — 사용자가 재빌드를 따로 요청하지 않아도 자동 수행.
   - 빌드 실패 시 원인 수정 후 재실행. 성공 표기(`OK: multiTaskingWindowNotifier-*.nvda-addon`) 확인 필수.
   - 과거 "리뷰는 통과했는데 재빌드를 빠뜨려 사용자가 구버전 애드온으로 테스트"한 이력 있음. 빌드는 리뷰와 동급의 필수 절차.
4. **Phase X.Y 커밋인 경우** IMPROVEMENTS.md 동기화
   - 커밋 메시지가 `Phase 1.` / `Phase 2.` / `Phase 3.` / `Phase 4.` 프리픽스면 IMPROVEMENTS.md의 해당 항목을 "현재 로드맵" → "완료 이력"으로 이동
   - Phase 전체가 끝난 시점에만 이동. 부분 커밋 중엔 건드리지 않음
   - 새 Non-goal 결정이 코드 주석(`__init__.py:6-8` 류)으로 추가됐으면 IMPROVEMENTS.md Non-goals 섹션에도 동기화
5. 빌드 성공 후 `.claude/last-review.txt` 파일을 현재 시각으로 갱신 (Stop hook 마커)
   - Windows bash: `date > .claude/last-review.txt`
6. 기록 후에만 사용자에게 "완료" 응답. 응답에 생성된 `.nvda-addon` 파일명을 명시.

**리뷰 강도 판단 기준**
- "NVDA API 오용 / `nextHandler()` 누락 / 예외 미처리 / 접근성 회귀" → 반드시 수정 후 재통과
- "경미한 스타일 / 타이핑 개선 제안" → 사용자에게 보고하고 계속 진행 가능

**예외 (리뷰 생략 가능)**
- `CLAUDE.md`, `IMPROVEMENTS.md`, `AddonDevGuide.md`, `AddonBestPractices.md`, `docs/**/*.md` 등 **문서만** 수정한 경우
- `.claude/` 디렉터리 내 하네스 설정만 수정한 경우

**사용자가 명시적으로 "리뷰 생략"이라고 지시하면** `.claude/last-review.txt`를 touch해 Stop hook을 통과시킨다.

# *중요* 빌드/설치 플로우

**원칙: 수동 복사 설치 금지.** 과거 `globalPlugins/` 레벨을 한 번 빠뜨린 수동 복사로 설정 패널 미표시 + 비프 회귀가 동시에 발생한 이력 있음(`%APPDATA%\nvda\addons\<name>\`에 소스 파일이 곧장 박히고 `manifest.ini` 누락). 이후로 반드시 빌드 스크립트 경유.

## 정식 설치 절차

1. `uv run python build.py` — `manifest.ini` + `globalPlugins/`를 묶어 `multiTaskingWindowNotifier-<version>.nvda-addon` 생성
2. NVDA 메뉴 → 도구 → 애드온 스토어 → "외부 파일로부터 애드온 설치" → 생성된 `.nvda-addon` 선택
3. NVDA 재시작
4. (필요 시) 기존 사용자 데이터 이식: `tmp_merged_app.list` 류 병합 파일을 `%APPDATA%\nvda\multiTaskingWindowNotifier\app.list`에 복사 후 NVDA 재시작 (마이그레이션은 `store.core._load_state`가 알아서 함)

## 설치 구조 검증 체크리스트

NVDA 애드온 로드 오류가 의심되면 **코드보다 설치 트리를 먼저** 확인:

| # | 확인 | 명령 | 정상 상태 |
|---|------|------|-----------|
| 1 | `manifest.ini` 존재 | `ls %APPDATA%\nvda\addons\multiTaskingWindowNotifier\manifest.ini` | 파일 있음 |
| 2 | 플러그인 엔트리 포인트 | `ls %APPDATA%\nvda\addons\multiTaskingWindowNotifier\globalPlugins\multiTaskingWindowNotifier\__init__.py` | 파일 있음 |
| 3 | 소스가 루트에 박혀있지 않은지 | `ls %APPDATA%\nvda\addons\multiTaskingWindowNotifier\*.py` | 결과 **없어야** 정상 |
| 4 | 사용자 데이터 위치 | `ls %APPDATA%\nvda\multiTaskingWindowNotifier\` | `app.json` / `tabClasses.json` 존재(애드온 실행 후). `addons\...\globalPlugins\` 내부에 이 파일들이 있으면 구 위치 — 삭제 대상 |
| 5 | 설정 섹션 생성 여부 | `grep multiTasking %APPDATA%\nvda\nvda.ini` | 섹션 헤더 보임 (애드온 최소 1회 실행 후) |

3번은 "수동 복사 오타 재발" 탐지용. 설치 경로에 `__init__.py`가 루트 레벨에 있으면 즉시 깨끗이 제거하고 `.nvda-addon`으로 재설치.
4번은 Phase 5에서 사용자 데이터를 애드온 패키지 외부로 이전한 이후의 규약. 재설치 시 데이터가 유지되는 표준 위치.

## 빌드 스크립트 (`build.py`) 제외 규칙

- `__pycache__`, `.pytest_cache`, `.venv`, `venv`, `.git`, `tests` 디렉토리는 패키지에 포함하지 않음
- `.pyc/.pyo/.pyd` 컴파일 산출물 제외
- `app.list`, `app.list.bak`, `app.json`, `app.json.tmp`, `tabClasses.json`, `tabClasses.json.tmp` 런타임 사용자 데이터 제외
- 포함 대상은 오직 `manifest.ini` + `globalPlugins/` 트리

# 기본
## 프로그램 목적
NVDA 스크린 리더 추가 기능으로 Alt+Tab를 눌렀을 때 여러 창을 탐색할 때 창 이름을 효과적으로 구분하기 위해 각기 다른 비프음으로 재생해 창 전환 속도를 높히기 위함.
## NVDA 추가 기능 개발 가이드

### NVDA API 레퍼런스 (★ 주요 참조)
**내용**: NVDA 소스 코드 독스트링 기반 완전한 API 레퍼런스
- **1. 핵심 모듈**: GlobalPlugin, NVDAObjects, Speech, UI, API
- **2. GUI 모듈**: guiHelper, settingsDialogs
- **3. 입력 처리**: inputCore, scriptHandler
- **4. 이벤트 시스템**: eventHandler
- **5. 데이터/설정**: config, addonHandler
- **6. 유틸리티**: controlTypes, textInfos, tones
- **7. 브라우즈 모드**: browseMode, treeInterceptorHandler, cursorManager
- **8. 앱 모듈**: appModuleHandler, addonHandler
- **9. Windows API**: winUser
- **실전 예제 및 학습 순서 포함**

**언제 사용**:
- 새로운 기능 개발 시 (API 함수/클래스 검색)
- 설정 시스템 구현 (config 모듈)
- GUI 다이얼로그 생성 (guiHelper)
- 이벤트 처리 패턴 확인 (eventHandler)
- 음향 효과 (tones.beep)
- 모든 NVDA API 참조가 필요할 때

---

### 공식 API 문서
**파일**: [AddonDevGuide.md](AddonDevGuide.md)
**출처**:
- https://github.com/nvdaaddons/devguide/wiki/NVDA%20Add-on%20Development%20Guide
- https://download.nvaccess.org/documentation/developerGuide.html

**용도**:
- NVDA API 참조 (api, ui, tones, speech 등)
- 이벤트 처리 패턴 확인
- 스크립트/제스처 정의 방법
- 객체 조작 및 내비게이션
- GUI 다이얼로그 생성
- 컨트롤 타입 및 상태 enum
- NVDA 내부 구조 이해

**언제 사용**:
- 새로운 NVDA 모듈/메서드 사용 시
- 이벤트 핸들러 구현 시
- 객체 속성/메서드 확인 필요 시
- GUI 개발 패턴 참고 시

---

### 실전 개발 팁
**파일**: [AddonBestPractices.md](AddonBestPractices.md)
**출처**: 실제 애드온 개발자들의 경험
- Golden Cursor 내부 분석
- StationPlaylist 내부 분석
- SysTray List 내부 분석

**용도**:
- 실전 구현 패턴 (레이어 커맨드, API 래핑, 스레딩 등)
- 성능 최적화 기법 (캐싱, 지연 초기화, 스레드 분리)
- 설정 관리 전략 (프로필 풀링, 온라인 캐시)
- 일반적인 함정과 해결책
- 코드 조직화 및 아키텍처 패턴
- 디버깅 기법 및 도구 활용
- Windows API 통합 방법

**언제 사용**:
- 복잡한 기능 설계 시 (레이어, 상태 관리)
- 성능 문제 해결 시
- 설정 시스템 구현 시
- Windows API 호출 필요 시
- 다른 애드온 패턴 참고 시

---

### 프로젝트 진화 이력 + 현재 로드맵
**파일**: [IMPROVEMENTS.md](IMPROVEMENTS.md)
**내용**: Phase A/B/B' 완료 이력 + 명시적 Non-goals + 현재 로드맵(Phase 1~4)

**언제 사용**:
- "이거 이미 된 건가?"를 확인할 때 (완료 이력)
- 보류 결정이 내려진 항목인지 확인할 때 (Non-goals)
- 지금 할 일을 파악할 때 (현재 로드맵)
## 기본 사양
- 언어: Python

## *중요* 모듈 문서화 원칙
- **새 모듈 추가 시**: 아래 "프로젝트 구조" tree의 해당 위치에 파일명 + 인라인 주석(1줄 역할 설명) 추가
- **형식**: tree 안에서 `파일명.py      # 간결한 역할 설명 (핵심 기능만)` 정렬
- **자동화**: 모듈 생성 완료 후 반드시 tree 블록 업데이트

## 프로젝트 구조
```
multiTaskingWindowNotifier/
├── manifest.ini                           # 추가 기능 메타정보
└── globalPlugins/
    └── multiTaskingWindowNotifier/
        ├── __init__.py                    # GlobalPlugin + 이벤트 훅 진입점 (+ ScriptsMixin 결합)
        ├── constants.py                   # ADDON_NAME, MAX_ITEMS(128), BEEP_TABLE(C major 온음계 35음), BEEP_TABLE_SIZE(35)
        ├── appIdentity.py                 # 앱 식별/복합키 + normalize_title
        ├── store/                         # v7 JSON 저장소 서브패키지 (Phase 3 분해)
        │   ├── __init__.py                # 공개 API 재export (load/save/record_switch/flush/…)
        │   ├── core.py                    # _load_state + 11개 공개 API 본체
        │   ├── io.py                      # JSON I/O + 원자적 저장
        │   ├── assign.py                  # 순차 비프 인덱스 할당
        │   └── migrations/                # 버전별 마이그레이션 (1파일 = 1버전 전환)
        │       ├── legacy_list.py         # ③ app.list → JSON
        │       ├── normalize_titles.py    # ⑤ title 정규화 + dedup
        │       └── v6_to_v7_beep_reassign.py  # ⑥ v7 재배정 clear
        ├── tabClasses.py                  # 앱별 editor/overlay wcn 매핑 + 자동 학습
        ├── windowInfo.py                  # 창 정보·경로 헬퍼 (title normalize 적용)
        ├── beepPlayer.py                  # v4 2음 비프 (core.callLater 기반 gap 예약)
        ├── listDialog.py                  # 목록 표시 wx.Dialog
        ├── settings.py                    # NVDA config 스키마 (confspec)
        ├── settingsPanel.py               # NVDA 설정 > 창 전환 알림 패널
        ├── focusDispatcher.py             # event_gainFocus 3분기 판정
        ├── nameChangeWatcher.py           # event_nameChange 탭 확정 감지
        ├── matcher.py                     # 매칭 + 비프 재생 + 시그니처 dedup
        ├── lookupIndex.py                 # windowLookup / appLookup 재구성
        ├── switchFlusher.py               # 디바운스 flush 스케줄러
        └── scripts.py                     # ScriptsMixin (@script 4개 + 보조 헬퍼)
```

### 런타임 사용자 데이터 (패키지 외부, 재설치 시 유지)

`%APPDATA%\nvda\multiTaskingWindowNotifier\` 하위에 생성됨(`windowInfo.config_addon_dir()`가 반환). 배포 패키지에는 포함되지 않으며 사용자 실행 중 자동 생성/갱신.

```
%APPDATA%\nvda\multiTaskingWindowNotifier\
├── app.json           # 앱·창 목록 + 메타(switchCount 등). 구형 app.list는 로드 시 마이그레이션
├── tabClasses.json    # 앱별 editor/overlay wcn. 없으면 기본값으로 자동 생성
├── app.list           # (구형, 있을 때만) 마이그레이션 대상
└── app.list.bak       # (구형 마이그레이션 완료 후 보존본)
```

## 기술 스택 & 핵심 모듈
- **NVDA API**
  - `globalPluginHandler.GlobalPlugin`: 전역 플러그인 기반 클래스
  - `api`: 포커스 객체(getForegroundObject, getFocusObject) 조회
  - `ui`: 사용자 메시지 출력(ui.message, ui.browseableMessage)
  - `tones`: 비프음 재생(tones.beep)
  - `scriptHandler.script`: 단축키 등록 데코레이터
  - `addonHandler`: 번역 초기화
- **이벤트 후킹**
  - `event_gainFocus` 단일 경로. 3분기(Phase B):
    1. `obj.wcn == "Windows.UI.Input.InputSite.WindowClass"` → Alt+Tab 오버레이. `obj.name`이 탭 제목.
    2. `tabClasses.is_overlay_class(appId, fgWcn)` → 앱별 오버레이(예: Notepad++ MRU `fgWcn='#32770'`). `obj.name`이 탭 제목.
    3. `tabClasses.is_editor_class(appId, obj.wcn)` → 에디터 자식 컨트롤(예: 메모장 `RichEditD2DPT`, Notepad++ `Scintilla`). `foreground.name`이 탭 제목.
  - 각 분기의 raw title은 `normalize_title`을 거쳐 꼬리 " - 앱명" 서픽스를 제거한 뒤 매칭. appId가 복합키 1등이라 title에 앱명 중복 저장하지 않는다.
  - 같은 키 0.3초 내 재매칭은 `_MATCH_DEDUP_SEC` 가드로 한 번만.
- **파일 저장소**
  - `store` 서브패키지(Phase 3에서 분해): 앱 목록 + 메타 JSON I/O. `store.core._states` 모듈 캐시로 상태 유지, `store.record_switch`/`store.flush`로 디바운스 저장. `store.core._load_state`에서 title normalize + v7 재배정 자동 마이그레이션 수행. I/O는 `store.io`, 비프 할당은 `store.assign`, 버전 전환은 `store.migrations.*`가 담당.
  - `tabClasses` 모듈: 앱별 editor/overlay wcn 세트. `load()`가 DEFAULT와 합집합 병합, `is_*_class`는 캐시 set 조회(고빈도), `learn_editor`는 등록 성공 훅에서 best-effort 호출.

## 데이터 포맷

**저장 위치**: `%APPDATA%\nvda\multiTaskingWindowNotifier\` (Phase 5에서 이전). 과거에는 애드온 패키지 디렉토리(`%APPDATA%\nvda\addons\multiTaskingWindowNotifier\globalPlugins\multiTaskingWindowNotifier\`) 내부에 저장했으나 재설치 시 트리 교체로 데이터가 소실되는 문제가 있어 외부로 분리. portable NVDA에서는 `globalVars.appArgs.configPath`가 자동으로 portable 경로로 전환된다.

### app.json (v7, 온음계 테이블로 전환)
```json
{
  "version": 7,
  "appBeepMap": {"chrome": 0, "notepad": 1},
  "items": [
    {"key": "chrome", "scope": "app",
     "appId": "chrome", "title": "",
     "registeredAt": "2026-04-18T06:00:00",
     "switchCount": 0, "lastSeenAt": null},
    {"key": "notepad|제목 없음", "scope": "window",
     "appId": "notepad", "title": "제목 없음",
     "tabBeepIdx": 0,
     "registeredAt": "2026-04-17T20:00:00",
     "switchCount": 0, "lastSeenAt": null}
  ]
}
```
- **인코딩**: UTF-8 (ensure_ascii=False)
- **원자적 저장**: `.tmp` → `os.replace` 패턴
- **최대 항목**: 128개 (MAX_ITEMS). v4부터 BEEP_TABLE_SIZE(v7부터 35)와 디커플.
- **scope 필드** (v3 신설)
  - `"window"` — `appId|title` 복합키. 정확 매치 시 2음(a→b) 재생.
  - `"app"` — `appId` 단독 키. 같은 appId의 어떤 창/탭이든 fallback으로 a 단음.
- **appBeepMap** (v4 신설, top-level): `{appId: BEEP_TABLE idx}`. 같은 appId의 모든 scope=window entry가 앱 비프(a)로 공유. scope=app entry가 없어도 자동 할당되어 모든 등록 appId가 base 음을 보유.
- **tabBeepIdx** (v4 신설, scope=window entry 전용): 같은 appId 내에서 고유한 탭 비프(b) 인덱스. v7 이론 조합 앱 35 × 탭 35 = 1225.
- **할당 알고리즘** (v6 전환): `_assign_next_idx` — 등록 순서 기반 순차. appBeepMap은 앱 등록 순서대로 BEEP_USABLE_START부터 0, 1, 2, ... 한 슬롯씩 상승(v7 기준 도→레→미 …). tabBeepIdx는 appId별 독립 카운터로 각 앱마다 0부터. 중간 gap은 재사용하지 않고 항상 max+1. 포화 시 구간 내 wrap + log.warning.
- **메타 필드**
  - `key` / `appId` / `title` — scope=app은 title이 빈 문자열
  - `registeredAt` / `switchCount` / `lastSeenAt` — 등록/사용 메타
- **title 정규화** (Phase B): 등록 시점(`windowInfo.get_current_window_info`)과 로드 시점(`store.core._load_state`) 모두 `normalize_title`을 거쳐 꼬리 " - 앱명" 한 덩이 제거.
- **v6 → v7 자동 마이그레이션**: 반음 64음 테이블(v6)에서 C major 온음계 35음(v7)으로 교체되며 인덱스 의미 자체가 달라진다. 로드 시 기존 appBeepMap/tabBeepIdx를 전부 버리고 순차 재배정 후 `version=7`로 저장. 1회성, 사용자는 주파수 재학습 필요.
- **v5 이하 자동 마이그레이션**: 거리 최대화 방식(v4/v5)도 동일 경로로 한 번에 v7까지 끌어올려 재배정.
- **v3 이하 자동 마이그레이션**: appBeepMap/tabBeepIdx 필드가 부재하면 동일 재배정 경로로 v7 할당 채움.
- **v2 → v3 → v7 자동 마이그레이션**: scope 필드 누락 시 `"window"`로 보정 후 v7 할당까지 연쇄 진행.

### tabClasses.json (v1, Phase B 신설)
```json
{
  "version": 1,
  "apps": {
    "notepad":    {"editor": ["RichEditD2DPT"], "overlay": []},
    "notepad++":  {"editor": ["Scintilla"],     "overlay": ["#32770"]}
  }
}
```
- **editor**: 탭 전환 확정 후 focus가 오는 자식 컨트롤 `windowClassName`. 이 wcn이 focus면 `foreground.name`을 탭 제목으로 매칭.
- **overlay**: 탭 선택 오버레이 상위창의 `windowClassName` (즉 `api.getForegroundObject().windowClassName`). 이 fgWcn이면 `obj.name`을 탭 제목으로 매칭.
- **기본값 병합**: 코드 내 `DEFAULT_TAB_CLASSES`와 합집합으로 병합. 사용자가 실수로 지워도 자동 복원.
- **자동 학습**: `_do_add` 성공 후 `focus.wcn != fg.wcn`이면 해당 appId의 `editor`에 추가(best-effort).
- **overlay 학습**: 이번 Phase 밖. 새 앱은 진단 로그로 fgWcn을 확인해 수동 편집.

### 하위호환: app.list
- 구형 텍스트 포맷(한 줄당 `appId|title` 또는 `title`만).
- `app.json`이 없고 `app.list`가 있으면 `store.load()`가 자동 마이그레이션.
- 마이그레이션 완료 시 원본은 `app.list.bak`으로 이름 변경해 보존.

### 디바운스 저장 규약 (`__init__.py`)
- `event_gainFocus` 매칭 성공마다 메모리 `switchCount++`.
- `_FLUSH_EVERY_N=10` 전환 또는 `_FLUSH_INTERVAL_SEC=30` 경과 시 `flush()` 호출.
- `terminate()`에서 강제 flush해 재로드/종료 시 손실 방지.

## 핵심 로직
### 앱 식별
- `getAppId(obj)`: `appModuleHandler.getAppModuleForNVDAObject(obj).appName` 경유. 실패 시 `windowClassName`, 그마저 비면 `"unknown"`.
- `makeKey(appId, title)`: `appId|title` 형식의 복합키 생성
- `splitKey(entry)`: 복합키 파싱, 구형 포맷 호환
- `normalize_title(name)`: 꼬리 " - 앱명" 한 덩이 제거. Alt+Tab obj.name, editor fg.name, MRU obj.name이 같은 형태로 떨어지게 함.

### 비프음 테이블 / 재생 (v4 2차원, v7 온음계 전환)
- `BEEP_TABLE`: 35개 주파수 (C3 130Hz ~ B7 3951Hz, C major 온음계 7음 × 5옥타브). `BEEP_TABLE_SIZE` 상수로 노출. v7 이전은 반음 64음이었으나 인접 슬롯 변별이 약하다는 피드백으로 온음계로 교체 — 1번과 2번이 "도→레" 전음 간격으로 분리돼 명확히 구분된다.
- `play_beep(app_idx, tab_idx=None, scope, duration, gap_ms)` — 2차원 비프.
  - scope=app 또는 tab_idx=None: `tones.beep(BEEP_TABLE[app_idx], duration)` 단음 1회.
  - scope=window + tab_idx 지정: a 재생 → `core.callLater(gap_ms, tones.beep, b, duration)` 2음.
  - `_schedule_second_beep` 폴백 순서: core.callLater → wx.CallLater → 동기 호출.
- `_resolve_beep_pair(matched_key, scope, appId)`:
  - real_app_id = matched_key에서 splitKey로 추출 (Alt+Tab 오버레이 title 역매핑 호환).
  - app_idx = appBeepMap[real_app_id] (자동 할당 보장). tab_idx = entry.tabBeepIdx (scope=window만).
  - miss 시 0으로 폴백 + log.warning.
- duration / gap_ms는 `config.conf` 설정 (기본 50 / 100). gap_ms는 15→60→100ms로 두 차례 상향 — 60ms에서도 두 음이 한 덩어리로 뭉쳐 들린다는 피드백 후 재조정. 좌/우 채널 볼륨 옵션은 v7 이후 제거(항상 50/50로 운용 → tones SDK 기본값과 동치).

### 등록된 단축키
- **NVDA+Shift+T**: 현재 창/앱 추가 (다이얼로그로 scope 선택)
- **NVDA+Shift+D**: 현재 창/앱 삭제 (정확 매치만, 창>앱 우선)
- **NVDA+Shift+R**: 목록 파일 새로고침
- **NVDA+Shift+I**: 등록 목록 다이얼로그 (다중 선택, Delete 키, 앱 일괄 삭제 확인)

## 코딩 패턴
- **에러 처리**: try-except로 파일 I/O 오류 처리, ui.message로 사용자에게 알림
- **경로 처리**: `os.path.join` 사용, `os.makedirs(exist_ok=True)`로 디렉터리 생성
- **인코딩**: UTF-8 고정
- **번역**: `addonHandler.initTranslation()` + `_(문자열)` 패턴
- **메모리 우선**: 창 전환(event_gainFocus)에서는 파일 I/O 없이 메모리 목록만 참조
- **스크립트 데코레이터**: `@script(description=..., category=..., gesture=...)`로 단축키 등록

## 개발 시 주의사항
- NVDA 추가 기능은 전역에서 실행되므로 예외 처리 필수
- `event_gainFocus`는 모든 포커스 전환마다 호출되므로 성능 고려 (파일 I/O 금지)
- `nextHandler()` 호출 필수 (이벤트 체인 유지)
- 최대 항목 수(64) 제한 준수

## 기능 아이디어
### 1. 즉시 실행 기능 ⚡
- **목적**: Alt+Tab 없이 등록된 창으로 바로 이동
- **방법**: 단축키로 목록 표시 → 번호/문자 입력 → 해당 창으로 즉시 전환
- **예시**: NVDA+Shift+G → "1~9, A~Z" 중 선택 → 창 활성화
- **효과**: Alt+Tab 반복 탐색 없이 원하는 창으로 직접 점프

### 2. 자주 쓰는 창 우선순위 ⭐
- **목적**: 자주 전환하는 창을 빠르게 접근
- **방법**: 전환 횟수 자동 추적, 상위 5~10개 창에 고정 단축키 할당 (NVDA+Shift+1~9)
- **효과**: 가장 많이 쓰는 창은 한 번에 이동

### 3. 창 그룹/프로필 📁
- **목적**: 상황별 창 세트 관리
- **방법**: 업무용/개발용/개인용 프로필 분리, 단축키로 프로필 전환
- **예시**: 업무용 (메일, 문서, 메신저), 개발용 (에디터, 브라우저, 터미널)
- **효과**: 업무/개인 구분으로 집중력 향상
- **상태**: 보류 (__init__.py:6 메모 참조)

### 4. 스마트 창 제안 🤖
- **목적**: 패턴 학습으로 자동 등록
- **방법**: 5회 이상 전환한 창 자동 감지, "이 창을 목록에 추가할까요?" 음성 제안
- **효과**: 수동 등록 부담 감소

### 5. 창 필터링/검색 🔍
- **목적**: 많은 창 중 빠른 찾기
- **방법**: 목록 표시 시 초성/키워드 입력으로 필터링
- **예시**: "ㅁㅁ" 입력 → "메모장", "메일" 필터
- **효과**: 64개 제한 내에서도 효율적 탐색

### 6. 비프음 커스터마이징 🎵
- **목적**: 개인 취향/청력 맞춤
- **방법**: 음높이 범위, 재생 시간, 좌우 밸런스 조정
- **현재**: 130Hz~4978Hz, 기본 50ms / 좌우30 (Phase 1에서 `config.conf`로 조정 가능. 테이블 자체는 고정)
- **효과**: 더 명확한 구분, 청각 피로 감소

### 7. 창 닫기 알림 ⚠️
- **목적**: 등록된 창이 닫혔을 때 알림
- **방법**: 등록된 창 종료 시 비프음 + 음성 알림, 목록에서 자동 제거 옵션
- **효과**: 목록 정리 자동화

### 8. 임시 추가 모드 ⏱️
- **목적**: 일시적으로만 추가
- **방법**: "30분만 추가" 옵션, 시간 경과 후 자동 제거
- **효과**: 작업별 임시 창 관리 (회의, 프로젝트 등)

### 9. 창 전환 통계 📊
- **목적**: 사용 패턴 분석
- **방법**: 오늘/주간 가장 많이 쓴 창, 평균 전환 횟수, 비생산적 창 경고
- **효과**: 업무 효율성 개선
- **상태**: 보류 (__init__.py:7 메모 참조)

### 10. 동일 앱 다중 창 구분 🪟 (구현 완료)
- **목적**: 같은 프로그램의 여러 창/탭 구분
- **방법**:
  - 등록 단위가 2계층 — "앱 전체"(SCOPE_APP)와 "특정 창/탭"(SCOPE_WINDOW). 매칭 우선순위 창>앱.
  - 비프 톤은 같은 appId 창들끼리 같은 base 주파수를 공유하고 등록 순서만큼 반음씩 위로 변주(`beepPlayer.play_beep`).
  - 탭 전환은 `event_gainFocus` 단일 경로. Phase B에서 3분기(Alt+Tab 오버레이 / 앱별 오버레이 / 에디터 자식 컨트롤)로 확장 + 모든 title은 `normalize_title` 통과.
- **단축키 변화**:
  - NVDA+Shift+T: 다이얼로그로 "이 창만/이 앱 전체" 선택. scope=window 등록 성공 시 focus 자식 컨트롤의 wcn을 `tabClasses.json`의 editor에 자동 학습.
  - NVDA+Shift+D: 정확 매치(창 키 또는 앱 키)만 삭제 — 다른 앱의 동일 title 창 오삭제 방지
  - NVDA+Shift+I: 다중 선택 + Delete 키, 앱 항목 일괄 삭제 시 같은 appId 창 동반 삭제 확인
- **데이터 포맷**: `app.json` v3 + `tabClasses.json` v1. app.json title은 Phase B에서 정규화된 형태로 저장(기존 데이터는 load 시 자동 마이그레이션).

### 11. Ctrl+Tab 탭 전환 시 탭별 비프 🎹 (Phase B 구현 완료)
- **목적**: Alt+Tab뿐 아니라 Ctrl+Tab으로 앱 내부 탭을 전환할 때도 등록된 탭마다 다른 비프.
- **동작**:
  - 메모장/Notepad++에서 Ctrl+Tab → 확정된 탭에서 editor 분기로 비프.
  - Notepad++ MRU 오버레이 탐색 중에도 overlay 분기로 각 탭마다 비프.
  - 한 번도 안 써본 앱은 NVDA+Shift+T로 에디터 영역에서 등록하면 editor wcn 자동 학습 → 이후 동작.
- **전제**: title이 정규화된 형태(앱명 서픽스 없이)로 저장되어 있어야 Alt+Tab/editor/overlay 3경로가 같은 키로 매칭됨.
