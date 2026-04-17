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
3. 통과 시 `.claude/last-review.txt` 파일을 현재 시각으로 갱신 (Stop hook 마커)
   - Windows bash: `date > .claude/last-review.txt`
4. 기록 후에만 사용자에게 "완료" 응답

**리뷰 강도 판단 기준**
- "NVDA API 오용 / `nextHandler()` 누락 / 예외 미처리 / 접근성 회귀" → 반드시 수정 후 재통과
- "경미한 스타일 / 타이핑 개선 제안" → 사용자에게 보고하고 계속 진행 가능

**예외 (리뷰 생략 가능)**
- `CLAUDE.md`, `IMPROVEMENTS.md`, `AddonDevGuide.md`, `AddonBestPractices.md`, `docs/**/*.md` 등 **문서만** 수정한 경우
- `.claude/` 디렉터리 내 하네스 설정만 수정한 경우

**사용자가 명시적으로 "리뷰 생략"이라고 지시하면** `.claude/last-review.txt`를 touch해 Stop hook을 통과시킨다.

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

### 프로젝트 개선 포인트
**파일**: [IMPROVEMENTS.md](IMPROVEMENTS.md)
**내용**: NVDA API 레퍼런스 기반 현재 프로젝트 개선 사항
- **우선순위 높음**: 설정 시스템, GUI 패널, 로깅, windowClassName 조건
- **우선순위 중간**: 브라우저블 메시지, 음성 우선순위, 다이얼로그 개선
- **우선순위 낮음**: appModuleHandler, 비프음 커스터마이징, 통계 기능
- **권장 개선 순서 포함**

**언제 사용**:
- 기능 개선/추가 계획 시
- 코드 리팩토링 시
- 사용성/접근성 향상 시
## 기본 사양
- 언어: Python
- 주요 파일:
  - manifest.ini: 추가 기능의 역할, 기본 정보를 담은 파일
  - globalPlugins\multiTaskingWindowNotifier\__init__.py: GlobalPlugin 및 스크립트/이벤트 훅
  - globalPlugins\multiTaskingWindowNotifier\constants.py: ADDON_NAME, MAX_ITEMS, BEEP_TABLE 상수
  - globalPlugins\multiTaskingWindowNotifier\appIdentity.py: 앱 ID/창 복합키 생성·파싱 유틸
  - globalPlugins\multiTaskingWindowNotifier\appListStore.py: 앱 목록 + 메타데이터 JSON 저장소 (load/save/record_switch/flush/reload/get_meta/prune_stale)
  - globalPlugins\multiTaskingWindowNotifier\windowInfo.py: 포커스 창 정보 추출 및 설정 디렉터리 헬퍼
  - globalPlugins\multiTaskingWindowNotifier\beepPlayer.py: 창 인덱스·순서 기반 비프음 재생
  - globalPlugins\multiTaskingWindowNotifier\listDialog.py: 등록 창 목록 표시용 wx.Dialog
  - globalPlugins\multiTaskingWindowNotifier\settings.py: NVDA config 스키마 정의 및 register/get 헬퍼
  - globalPlugins\multiTaskingWindowNotifier\settingsPanel.py: NVDA 설정 대화상자의 "창 전환 알림" 패널 (SettingsPanel 구현)
  - globalPlugins\multiTaskingWindowNotifier\app.json: 등록된 앱·창 목록 + 메타(전환 카운트/마지막 사용 시각/등록일). 하위호환으로 `app.list`가 있으면 최초 로드 시 자동 마이그레이션 후 `app.list.bak`으로 백업
## *중요* 모듈 문서화 원칙
- **새 모듈 추가 시**: 위 "주요 파일" 목록에 파일명과 역할을 한 줄로 추가
- **형식**: `파일명.py: 간결한 역할 설명 (1줄, 핵심 기능만)`
- **예시**: `search_engine.py: 진행/시켜 검색 및 필터링 모듈`
- **자동화**: 모듈 생성 완료 후 반드시 이 섹션 업데이트

## 프로젝트 구조
```
multiTaskingWindowNotifier/
├── manifest.ini                           # 추가 기능 메타정보
└── globalPlugins/
    └── multiTaskingWindowNotifier/
        ├── __init__.py                    # GlobalPlugin + 스크립트/이벤트 훅
        ├── constants.py                   # ADDON_NAME, MAX_ITEMS, BEEP_TABLE
        ├── appIdentity.py                 # 앱 식별/복합키 유틸
        ├── appListStore.py                # 앱 목록 + 메타 JSON 저장소 (record_switch/flush 포함)
        ├── windowInfo.py                  # 창 정보·경로 헬퍼
        ├── beepPlayer.py                  # 비프음 재생 (wx.CallLater 기반 비동기)
        ├── listDialog.py                  # 목록 표시 wx.Dialog
        ├── settings.py                    # NVDA config 스키마 (confspec)
        ├── settingsPanel.py               # NVDA 설정 > 창 전환 알림 패널
        └── app.json                       # 앱·창 목록 + 메타(switchCount 등). 구형 app.list는 로드 시 마이그레이션
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
  - `event_gainFocus`: 창 포커스 전환 시 자동 실행
  - `windowClassName == "Windows.UI.Input.InputSite.WindowClass"` 조건에서만 비프 재생
- **파일 저장소**
  - `appListStore` 모듈: 앱 목록 + 메타 JSON I/O. 모듈 수준 캐시(`_states`)로 상태 유지, `record_switch`/`flush`로 디바운스 저장 지원.

## 데이터 포맷
### app.json (Phase 2 이후 기본)
```json
{
  "version": 2,
  "items": [
    {"key": "notepad|제목 없음 - 메모장",
     "appId": "notepad",
     "title": "제목 없음 - 메모장",
     "registeredAt": "2026-04-17T20:00:00",
     "switchCount": 0,
     "lastSeenAt": null}
  ]
}
```
- **인코딩**: UTF-8 (ensure_ascii=False)
- **원자적 저장**: `.tmp` → `os.replace` 패턴
- **최대 항목**: 64개 (MAX_ITEMS)
- **메타 필드**
  - `key` / `appId` / `title` — 복합키와 파생 정보
  - `registeredAt` — 최초 등록 시각 (ISO 8601, 초 단위)
  - `switchCount` — 해당 창으로 포커스 전환된 누적 횟수 (#2/#9 기반)
  - `lastSeenAt` — 마지막 전환 시각 (#7 창 닫기 알림 대비)

### 하위호환: app.list
- 구형 텍스트 포맷(한 줄당 `appId|title` 또는 `title`만).
- `app.json`이 없고 `app.list`가 있으면 `appListStore.load()`가 자동 마이그레이션.
- 마이그레이션 완료 시 원본은 `app.list.bak`으로 이름 변경해 보존.

### 디바운스 저장 규약 (`__init__.py`)
- `event_gainFocus` 매칭 성공마다 메모리 `switchCount++`.
- `_FLUSH_EVERY_N=10` 전환 또는 `_FLUSH_INTERVAL_SEC=30` 경과 시 `flush()` 호출.
- `terminate()`에서 강제 flush해 재로드/종료 시 손실 방지.

## 핵심 로직
### 앱 식별
- `_getAppId(obj)`: `obj.appModule.appName` 또는 `windowClassName` 사용
- `_makeKey(appId, title)`: `appId|title` 형식의 복합키 생성
- `_splitKey(entry)`: 복합키 파싱, 구형 포맷 호환

### 비프음 테이블
- `BEEP_TABLE`: 64개 주파수 (130Hz~4978Hz, 반음 단위)
- 목록 인덱스에 따라 서로 다른 음높이 재생
- 재생: `tones.beep(주파수, duration, left, right)` — 기본값 50ms / 좌30 / 우30 (Phase 1 이후 `config.conf`로 조정 가능)

### 등록된 단축키
- **NVDA+Shift+T**: 현재 창 추가
- **NVDA+Shift+D**: 현재 창 삭제
- **NVDA+Shift+R**: 목록 파일 새로고침
- **NVDA+Shift+I**: 등록된 모든 창 보기 (`listDialog.AppListDialog` — `wx.Dialog` 모달)

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

### 10. 동일 앱 다중 창 구분 🪟
- **목적**: 같은 프로그램의 여러 창 구분
- **방법**: 크롬 창1, 창2, 창3 각각 다른 비프음, 파일명 기반 구분
- **효과**: 동일 앱 다중 사용 시 효율 향상
