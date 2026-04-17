# NVDA Add-on Development Guide
> 출처:
> - https://github.com/nvdaaddons/devguide/wiki/NVDA-Add-on-Development-Guide
> - https://download.nvaccess.org/documentation/developerGuide.html

## 핵심 모듈 API

### API 모듈 (api.py)
객체 및 포커스 관리

- `api.getFocusObject()` - 현재 포커스된 컨트롤 가져오기
- `api.getNavigatorObject()` - 내비게이터 객체 가져오기 (포커스와 다를 수 있음)
- `api.getForegroundObject()` - 포어그라운드 창의 부모 객체 반환
- `api.setFocusObject(obj)` / `api.setNavigatorObject(obj)` - NVDA가 인식하는 포커스 변경
- `api.getDesktopObject()` - 최상위 셸 객체 반환
- `api.copyToClip(text, notify_optional)` - 클립보드 작업

### UI 모듈 (ui.py)
사용자 메시지 출력

- `ui.message(text, priority_optional, braille_optional)` - 음성/점자 출력
- `ui.browseableMessage(text, title, isHTML, sanitize, copyButton, closeButton)` - 브라우저블 창 표시

### 음성 관리 (speech)
오디오 출력 제어

- `speech.cancelSpeech()` - 현재 음성 중지

### 톤 모듈 (tones.py)
오디오 피드백

- `tones.beep(frequency_hz, duration_ms, left_vol_opt, right_vol_opt)` - 비프음 생성

---

## 스크립트 정의 패턴

### 기본 제스처 바인딩
```python
__gestures__ = {
    "kb:NVDA+A": "doBeep",
    "kb:control+NVDA+1": "sayHello"
}
```

### 스크립트 데코레이터 방식
```python
from scriptHandler import script

@script(
    gesture="kb:NVDA+A",
    description="Input help text",
    category="Category Name",
    speakOnDemand=True
)
def script_doBeep(self, gesture):
    # 구현 내용
```

**데코레이터 인자:**
- `description` - 입력 도움말 텍스트
- `gesture` - 단일 제스처 문자열
- `gestures` - 제스처 리스트
- `category` - 카테고리 이름
- `speakOnDemand` - 요청 시 음성 출력 플래그

---

## 이벤트 처리

### 표준 이벤트 시그니처
```python
def event_eventName(self, obj, nextHandler):
    # 이벤트 처리 로직
    nextHandler()  # 필수: NVDA의 기본 처리로 전달
```

### 주요 이벤트
- `event_gainFocus(self, obj, nextHandler)` - 객체가 포커스 받음
- `event_nameChange(self, obj, nextHandler)` - 객체 이름 변경됨
- `event_NVDAObject_init(self, obj)` - 객체 초기화 훅 (앱 모듈 전용)

**중요**: 반드시 `nextHandler()`를 호출해 이벤트 체인 유지

---

## 객체 조작

### 객체 속성
- `obj.name` - 컨트롤 레이블
- `obj.value` - 현재 상태/내용
- `obj.role` - 컨트롤 타입 (controlTypes.Role enum)
- `obj.states` - 적용 가능한 상태 집합
- `obj.appModule` - 부모 애플리케이션 모듈
- `obj.windowClassName` - 윈도우 클래스 식별자
- `obj.childCount` - 자식 객체 수

### 내비게이션
- `obj.parent` - 부모 객체
- `obj.firstChild` / `obj.lastChild` - 첫/마지막 자식
- `obj.next` / `obj.previous` - 형제 탐색
- `obj.children[index]` - 인덱스로 자식 접근
- `obj.getChild(index)` - 대체 자식 가져오기

---

## 오버레이 클래스 및 역할 수정

### 속성 오버라이드 패턴
```python
def event_NVDAObject_init(self, obj):
    if obj.windowClassName == "TargetClass":
        obj.role = controlTypes.Role.WINDOW
```

### 커스텀 객체 클래스 패턴
```python
from NVDAObjects.IAccessible import IAccessible

class CustomObject(IAccessible):
    @script(gesture="kb:F10")
    def script_customAction(self, gesture):
        pass

def chooseNVDAObjectOverlayClasses(self, obj, clsList):
    if obj.windowClassName == "SpecialWindow":
        clsList.insert(0, CustomObject)
```

---

## 모듈 임포트 및 핸들러 클래스

### 전역 플러그인 기반
```python
import globalPluginHandler

class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    pass
```

### 앱 모듈 기반
```python
import appModuleHandler

class AppModule(appModuleHandler.AppModule):
    pass
```

### 키보드 입력
```python
import keyboardHandler

keyboardHandler.KeyboardInputGesture.fromName("applications").send()
```

### 설정 접근
```python
import config

if not config.conf["presentation"]["reportDynamicContentChanges"]:
    # 조건부 로직
```

---

## 컨트롤 타입 (2021.2 이후)

`controlTypes.Role.*` 및 `controlTypes.State.*` enum 사용:

### Role 예시
- `controlTypes.Role.EDITABLETEXT` - 편집 가능한 텍스트
- `controlTypes.Role.SLIDER` - 슬라이더
- `controlTypes.Role.WINDOW` - 창
- `controlTypes.Role.BUTTON` - 버튼

### State 예시
- `controlTypes.State.CHECKABLE` - 체크 가능
- `controlTypes.State.CHECKED` - 체크됨
- `controlTypes.State.FOCUSED` - 포커스됨

---

## 확장 포인트

`extensionPoints` 모듈에 위치:

- `Action` - 이벤트 발생 시 알림
- `Decider` - 조건부 처리 로직
- `AccumulatingDecider` - 누적 결정 수집
- `Filter` - 텍스트/콘텐츠 수정

---

## 추가 기능 메타데이터 및 번역

### 애드온 핸들러 유틸리티
- `addonHandler.initTranslation()` - 국제화 설정
- `addonHandler.getCodeAddon()` - 현재 애드온 인스턴스 가져오기
- `addonHandler.isCLIParamKnown` - 커스텀 명령줄 파라미터 처리

---

## 스크립트 조회 우선순위

명령 해석 순서:
1. **전역 플러그인** (Global plugins)
2. **앱 모듈** (App modules - 현재 애플리케이션)
3. **NVDA 객체** (NVDA objects - 특정 컨트롤)
4. **전역 명령** (Global commands - NVDA 기본값)

상위 우선순위 핸들러가 하위를 오버라이드

---

## 로깅

```python
from logHandler import Log

log = Log()
log.info("정보 메시지")
log.warning("경고 메시지")
log.error("에러 메시지")
```

---

## 주요 개발 제약사항

- **Python 버전**: 3.13+ 필요 (3.11은 하위 호환 테스트용)
- **NVDA 버전**: 2025.1+ 기준 (명시되지 않는 한)
- **64비트 전환**: 진행 중, 알파 스냅샷은 64비트 빌드 사용
- **Windows Store NVDA**: 애드온 로드 불가, 데스크톱 버전 사용 필수
- **개발 스크래치패드**: 사용자 설정에서 커스텀 모듈 로드하려면 활성화 필요

---

## GUI 개발

### wxPython 다이얼로그 패턴
```python
import wx
import gui

class MyDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title="제목")
        # UI 구성

# 표시 방법
def show_dialog():
    gui.mainFrame.prePopup()
    dlg = MyDialog(gui.mainFrame)
    dlg.ShowModal()
    dlg.Destroy()
    gui.mainFrame.postPopup()

wx.CallAfter(show_dialog)
```

**중요**:
- `gui.mainFrame`을 부모로 사용
- `prePopup()` / `postPopup()` 호출 필수
- `wx.CallAfter`로 GUI 스레드 안전성 보장

---

## 실전 팁

### 제스처 키 포맷
- **소문자 사용**: `"kb:nvda+shift+t"` (대문자 NVDA 아님)
- **수정자 순서**: control > shift > alt > nvda
- **예시**: `"kb:control+shift+nvda+a"`

### 에러 처리
```python
try:
    # 위험한 작업
    obj.someMethod()
except AttributeError as e:
    log.debug(f"속성 접근 실패: {e}")
except Exception as e:
    log.warning(f"예기치 않은 오류: {e}")
```

### 성능 고려사항
- `event_gainFocus`는 매우 빈번하게 호출됨 → 파일 I/O 금지
- 목록 검색은 딕셔너리 사용 (O(1))
- `desktop.children` 순회는 느릴 수 있음 → 캐싱 고려

---

## NVDA 내부 구조 (Internals)

### 모듈 구조 및 조직

**핵심 패키지:**
- `appModuleHandler` - 애플리케이션별 모듈 관리
- `globalPluginHandler` - 시스템 전역 플러그인 처리
- `NVDAObjects` - 여러 접근성 API에 걸쳐 GUI 컨트롤 추상화
- `scriptHandler` - 제스처를 실행 가능한 명령에 바인딩
- `extensionPoints` - 플러그인-코어 간 통신 훅 제공

**디렉터리 계층:**
- 앱 모듈: `appModules/` 하위 디렉터리
- 전역 플러그인: `globalPlugins/`
- 애드온: zip 아카이브 내 동일한 구조 사용

### NVDA 객체 모델

**표준 속성:**
- `name` - 컨트롤 레이블
- `role` - 컨트롤 타입
- `states` - 상태 집합
- `value` - 현재 값
- `description` - 설명
- `location` - 화면 위치

**내비게이션 속성:**
- `parent`, `next`, `previous`, `firstChild`, `lastChild` - 전체 트리
- `simpleParent`, `simpleNext`, `simplePrevious` 등 - 기본 검토 모드용 단순화 버전

### 이벤트 시스템 아키텍처

**이벤트 전파 체인:**
1. 전역 플러그인 (Global Plugins)
2. 활성 앱 모듈 (Active App Module)
3. 트리 인터셉터 (Tree Interceptor)
4. NVDA 객체 자체 (NVDAObject)

**이벤트 메서드 시그니처:**
- 객체 레벨: `event_name(self)` - `self`만 받음
- 상위 레벨: `event_name(self, obj, nextHandler)` - 전파 제어용

**주요 이벤트:**
- `foreground` - 포어그라운드 변경
- `gainFocus` - 포커스 획득
- `nameChange` - 이름 변경
- `valueChange` - 값 변경
- `stateChange` - 상태 변경
- `caret` - 캐럿 이동
- `locationChange` - 위치 변경

### 플러그인/애드온 로딩 메커니즘

**플러그인 타입:**
- **앱 모듈**: 애플리케이션별, 실행 파일명으로 명명 (예: `notepad.py`)
- **전역 플러그인**: 시스템 전역 기능

**로딩 컨텍스트:**
- 개발 중: `scratchpad/` 디렉터리에서 로드
- 배포 후: 애드온 패키지에서 로드
- 런타임 발견: NVDA가 자동으로 모듈 탐색
- 언로드: 애플리케이션 종료 또는 NVDA 종료 시 앱 모듈 언로드

**호스티드 애플리케이션:**
- 호스트 실행 파일 내부 앱 (예: Java via `javaw.exe`, Windows 앱 via `wwahost.exe`)
- 앱 모듈 이름: `AppModule.appName`에서 얻은 호스티드 앱 식별자와 일치해야 함

### 확장 포인트 시스템

**5가지 확장 포인트 타입:**
- `Action` - 알림 메커니즘
- `Filter` - 데이터 변환
- `Decider` - 조건부 실행 (첫 `False`에서 중지)
- `AccumulatingDecider` - 모든 핸들러 실행, 하나라도 `False`면 실패
- `Chain` - 반복 가능한 핸들러 등록

**주요 확장 포인트:**
- `config.post_configProfileSwitch` - 프로필 변경
- `core.postNvdaStartup` - 시작 완료
- `speech.filter_speechSequence` - 음성 출력 수정
- `bdDetect.scanForDevices` - 점자 디스플레이 장치 감지
- `addonHandler.isCLIParamKnown` - 커스텀 명령줄 인자

### 커스텀 NVDA 객체 클래스

**오버라이드 방법:**
```python
def chooseNVDAObjectOverlayClasses(self, obj, clsList):
    if obj.windowClassName == "Edit":
        clsList.insert(0, CustomEditClass)
```

**상속 기반:**
- `NVDAObjects.window.Window` - 윈도우 레벨 접근
- `NVDAObjects.IAccessible.IAccessible` - MSAA 속성

### 제스처 식별자 포맷

**형식:** `source(device):modifiers+keys`

**예시:**
- `kb:NVDA+shift+v` - 키보드
- `br(freedomScientific):leftWizWheelUp` - 점자 디스플레이
- `ts:tap` - 터치스크린
- `bk:space` - 점자 키보드

**입력 소스:**
- `kb` - 키보드
- `br` - 점자 디스플레이
- `ts` - 터치스크린
- `bk` - 점자 키보드

**조회 우선순위:**
사용자 맵 → 로케일 맵 → 드라이버 맵 → 전역 플러그인 → 앱 모듈 → 트리 인터셉터 → 포커스 객체 → 내장 명령

### 설치/제거 훅

**파일:** 애드온 루트에 `installTasks.py` 배치

```python
def onInstall():
    # 설치 시 실행
    pass

def onUninstall():
    # 제거 시 실행
    pass
```

### 디버깅 도구

**Python 콘솔 (NVDA+Ctrl+Z):**
- 스냅샷 변수: `focus`, `nav`, `caretPos`
- 탭 완성 지원
- 인터랙티브 디버깅

**원격 콘솔:**
- TCP 포트 6832 via
- 소스 빌드용 고급 시나리오

### Add-on API 호환성

- **API 범위**: 언더스코어(`_`)로 시작하지 않는 모든 NVDA 내부 기호
- **변경 주기**: 최대 연 1회, `.1` 릴리스에서만 (예: `2022.1`)
- **하위 호환성**: 주요 버전 간 유지
- **폐기 공지**: NVDA API 메일링 리스트 및 변경 문서

### 호스트 애플리케이션 모듈

Java 또는 Windows Store 앱처럼 호스트 프로세스 내부에서 실행되는 앱의 경우:
- `AppModule.appName`에서 실제 앱 식별자 확인
- 앱 모듈 파일명을 해당 식별자로 명명

### 심볼 사전 (Symbol Dictionaries)

**파일:** `symbols.dic`

**포맷:**
```
식별자(또는 정규식 패턴) → 대체 텍스트 [레벨] [보존 플래그]
```

발음 규칙 커스터마이징 가능

### 로케일 지원

- **로케일별 매니페스트**: `locale/<lang>/manifest.ini`
- **Gettext 메시지 카탈로그**: `.po` 파일
- **번역 초기화**: `addonHandler.initTranslation()` 호출

---

## 추가 참고 자료

### 공식 링크
- **NVDA GitHub**: https://github.com/nvaccess/nvda
- **Developer Guide**: https://download.nvaccess.org/documentation/developerGuide.html
- **Design Overview**: https://github.com/nvaccess/nvda/wiki/DesignOverview
- **NV Access 다운로드**: https://www.nvaccess.org/download/
- **개발 스냅샷**: https://www.nvaccess.org/files/nvda/snapshots/

### 개발 도구
- **Python**: https://www.python.org/downloads/
- **SCons 빌드 도구**: http://www.scons.org/
- **Addon 템플릿**: https://github.com/nvdaaddons/AddonTemplate/archive/master.zip
- **GNU Gettext (Windows)**: http://gnuwin32.sourceforge.net/downlinks/gettext.php
- **Gettext 인스톨러**: https://mlocati.github.io/articles/gettext-iconv-windows.html
