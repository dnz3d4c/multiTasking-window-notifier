# NVDA API 레퍼런스 가이드

**참고 위치**: `C:/project/ext/nvda/nvda/NVDAAddons/source/`

---

## 📌 1. 핵심 모듈 (Core Modules)

### 1.1 GlobalPlugin (전역 플러그인)
**파일**: `globalPluginHandler.py`

전역 플러그인은 모든 애플리케이션에서 동작하는 기능을 구현할 때 사용합니다.

**기본 클래스**:
```python
class GlobalPlugin(baseObject.ScriptableObject):
    """NVDA 전역 플러그인 베이스 클래스"""

    def __init__(self):
        super().__init__()
        # 초기화 코드

    def terminate(self):
        """플러그인 종료 시 호출"""
        pass

    def chooseNVDAObjectOverlayClasses(self, obj, clsList):
        """NVDAObject 오버레이 클래스 선택"""
        pass

    # 이벤트 핸들러
    def event_gainFocus(self, obj, nextHandler):
        """포커스 획득 이벤트"""
        nextHandler()  # 다음 핸들러 호출

    def event_nameChange(self, obj, nextHandler):
        """이름 변경 이벤트"""
        nextHandler()

    # 스크립트 (단축키 바인딩)
    def script_myCustomCommand(self, gesture):
        """설명: 커스텀 명령어"""
        ui.message("실행됨!")

    # 단축키 바인딩
    __gestures = {
        "kb:NVDA+shift+f12": "myCustomCommand",
    }
```

**주요 메서드**:
- `terminate()`: 플러그인 종료 시 호출
- `event_*()`: 모든 NVDAObject 이벤트 수신 가능
- `script_*()`: 커스텀 단축키 구현
- `chooseNVDAObjectOverlayClasses()`: 객체 클래스 커스터마이징

---

### 1.2 NVDAObjects (객체 시스템)
**파일**: `NVDAObjects/__init__.py`

NVDA의 모든 UI 요소는 NVDAObject로 표현됩니다.

**주요 하위 패키지**:
- `NVDAObjects/IAccessible/`: IAccessible/MSAA 기반 객체
  - `wx.py`: wxPython 위젯 지원 ⭐ **SpeedWork 관련**
  - `winword.py`: MS Word
  - `excel.py`: MS Excel
- `NVDAObjects/UIA/`: UI Automation 기반 객체
  - `chromium.py`: Chrome/Edge
  - `winConsoleUIA.py`: Windows 터미널
- `NVDAObjects/window/`: Win32 윈도우 객체
  - `edit.py`: 일반 에디트 컨트롤
  - `scintilla.py`: Scintilla 에디터

**NVDAObject 기본 구조**:
```python
class NVDAObject(documentBase.TextContainerObject, baseObject.ScriptableObject):
    """
    모든 UI 위젯의 기본 클래스
    """

    # 필수 속성
    processID: int  # 프로세스 ID
    name: str       # 객체 이름
    role: int       # 역할 (버튼, 에디트 등)
    value: str      # 값

    # 계층 구조
    parent: 'NVDAObject'
    firstChild: 'NVDAObject'
    next: 'NVDAObject'
    previous: 'NVDAObject'

    # 상태
    states: set  # 포커스, 선택, 비활성 등

    # 위치
    location: tuple  # (left, top, width, height)
```

**wxPython 객체 처리** (`NVDAObjects/IAccessible/wx.py`):
- SpeedWork는 wxPython 기반이므로 이 파일이 핵심!
- ListBox, TextCtrl 등 wx 위젯의 접근성 처리

---

### 1.3 Speech (음성 출력)
**파일**: `speech/speech.py`

**주요 함수**:
```python
# 메시지 출력 (가장 많이 사용)
import speech
speech.speakMessage("복사 완료!", priority=speech.Spri.NOW)

# 텍스트 출력
speech.speakText("긴 텍스트...")

# 철자 읽기
speech.speakSpelling("NVDA", locale=None, useCharacterDescriptions=False)

# 음성 취소
speech.cancelSpeech()

# 음성 모드 설정
speech.setSpeechMode(speech.SpeechMode.talk)  # 말하기
speech.setSpeechMode(speech.SpeechMode.off)   # 끄기
```

**우선순위**:
- `Spri.NOW`: 즉시 출력 (현재 음성 중단)
- `Spri.NEXT`: 다음 출력
- `Spri.NORMAL`: 일반 우선순위

---

### 1.4 UI (사용자 인터페이스)
**파일**: `ui.py`

**주요 함수**:
```python
import ui

# 메시지 출력 (음성 + 점자)
ui.message("작업 완료")

# 브라우저 가능한 메시지 (긴 텍스트)
ui.browseableMessage("긴 로그...", title="제목")

# 리뷰 커서로 메시지 출력
ui.reviewMessage("리뷰할 텍스트")
```

---

### 1.5 API (핵심 API)
**파일**: `api.py`

**주요 함수**:
```python
import api

# 포커스 객체 가져오기
focusObj = api.getFocusObject()
print(focusObj.name, focusObj.role)

# 네비게이터 객체
navObj = api.getNavigatorObject()

# 데스크톱 객체
desktopObj = api.getDesktopObject()

# 포커스 설정
api.setFocusObject(someObj)

# 마우스 객체
mouseObj = api.getMouseObject()
```

---

## 📌 2. GUI 모듈 (gui/)

### 2.1 guiHelper (GUI 헬퍼)
**파일**: `gui/guiHelper.py`

wxPython GUI 생성을 간편하게 만들어주는 유틸리티입니다.

**BoxSizerHelper 사용 예시**:
```python
import wx
from gui import guiHelper

class MyDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title="설정")

        mainSizer = wx.BoxSizer(wx.VERTICAL)
        sHelper = guiHelper.BoxSizerHelper(self, wx.VERTICAL)

        # 레이블 + 텍스트 컨트롤
        self.nameText = sHelper.addLabeledControl("이름:", wx.TextCtrl)

        # 레이블 + 체크박스
        self.enableCheck = sHelper.addLabeledControl(
            "활성화",
            wx.CheckBox
        )

        # 리스트 컨트롤
        self.listCtrl = sHelper.addLabeledControl(
            "항목:",
            wx.ListCtrl,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL
        )

        # 버튼 그룹
        bHelper = guiHelper.ButtonHelper(wx.HORIZONTAL)
        okButton = bHelper.addButton(self, id=wx.ID_OK, label="확인")
        cancelButton = bHelper.addButton(self, id=wx.ID_CANCEL, label="취소")
        sHelper.addItem(bHelper)

        mainSizer.Add(
            sHelper.sizer,
            border=guiHelper.BORDER_FOR_DIALOGS,
            flag=wx.ALL
        )
        self.SetSizer(mainSizer)
        mainSizer.Fit(self)
```

**주요 상수**:
- `BORDER_FOR_DIALOGS = 10`: 다이얼로그 테두리
- `SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS = 10`: 수직 간격
- `SPACE_BETWEEN_BUTTONS_HORIZONTAL = 7`: 버튼 수평 간격

---

### 2.2 settingsDialogs (설정 다이얼로그)
**파일**: `gui/settingsDialogs.py`

NVDA 설정 패널을 만들 때 사용합니다.

```python
from gui import settingsDialogs, guiHelper
import wx

class MySettingsPanel(settingsDialogs.SettingsPanel):
    title = "내 설정"

    def makeSettings(self, settingsSizer):
        sHelper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)

        self.myCheckBox = sHelper.addItem(
            wx.CheckBox(self, label="기능 활성화")
        )
        self.myCheckBox.SetValue(config.conf["myAddon"]["enabled"])

    def onSave(self):
        config.conf["myAddon"]["enabled"] = self.myCheckBox.GetValue()
```

---

### 2.3 nvdaControls (NVDA 커스텀 컨트롤)
**파일**: `gui/nvdaControls.py`

NVDA 전용 wx 컨트롤 모음:
- `AutoWidthColumnListCtrl`: 자동 너비 조절 리스트
- `SelectOnFocusSpinCtrl`: 포커스 시 선택되는 스핀 컨트롤

---

## 📌 3. 입력 처리

### 3.1 inputCore (입력 코어)
**파일**: `inputCore.py`

**Gesture (제스처) 바인딩**:
```python
# 키보드 제스처
"kb:NVDA+shift+f12"          # NVDA + Shift + F12
"kb:control+alt+delete"       # Ctrl + Alt + Del
"kb:leftArrow"                # 왼쪽 화살표

# 브라우저 제스처
"br(freedomScientific):leftWizWheelDown"  # 점자 디스플레이

# 터치 제스처
"ts:2finger_flickRight"       # 2손가락 오른쪽 플릭
```

---

### 3.2 scriptHandler (스크립트 핸들러)
**파일**: `scriptHandler.py`

**스크립트 데코레이터**:
```python
from scriptHandler import script

class MyPlugin(globalPluginHandler.GlobalPlugin):

    @script(
        description="항목 복사",
        category="SpeedWork",
        gesture="kb:NVDA+shift+c"
    )
    def script_copyItem(self, gesture):
        ui.message("복사됨!")
```

---

## 📌 4. 이벤트 시스템

### 4.1 eventHandler (이벤트 핸들러)
**파일**: `eventHandler.py`

**주요 이벤트**:
- `gainFocus`: 포커스 획득
- `loseFocus`: 포커스 상실
- `nameChange`: 이름 변경
- `valueChange`: 값 변경
- `stateChange`: 상태 변경
- `foreground`: 포그라운드 윈도우 변경
- `caret`: 캐럿(커서) 이동

**이벤트 수신 예시**:
```python
class GlobalPlugin(globalPluginHandler.GlobalPlugin):

    def event_gainFocus(self, obj, nextHandler):
        """포커스 이벤트"""
        if obj.role == controlTypes.Role.LISTITEM:
            ui.message(f"선택됨: {obj.name}")
        nextHandler()  # 다음 핸들러 호출 필수!

    def event_valueChange(self, obj, nextHandler):
        """값 변경 이벤트"""
        if obj.windowClassName == "wxWindowNR":
            # SpeedWork의 wx 위젯
            pass
        nextHandler()
```

---

## 📌 5. 데이터 및 설정

### 5.1 config (설정)
**파일**: `config.py` (추정)

```python
import config

# 설정 읽기
enabled = config.conf["myAddon"]["enabled"]

# 설정 쓰기
config.conf["myAddon"]["option"] = "value"

# 설정 저장
config.conf.save()
```

---

### 5.2 addonHandler (애드온 핸들러)
**파일**: `addonHandler/__init__.py`

```python
import addonHandler

# 애드온 초기화
addonHandler.initTranslation()

# 번역 함수
_ = addonHandler.translation.gettext
ui.message(_("Hello"))  # 다국어 지원
```

---

## 📌 6. 유틸리티

### 6.1 controlTypes (컨트롤 타입)
**파일**: `controlTypes.py` (추정)

```python
from controlTypes import Role, State

# 역할
Role.BUTTON
Role.EDITABLETEXT
Role.LISTITEM
Role.CHECKBOX
Role.DIALOG

# 상태
State.FOCUSED
State.SELECTED
State.CHECKED
State.READONLY
```

---

### 6.2 textInfos (텍스트 정보)
**파일**: `textInfos/__init__.py` (추정)

텍스트 컨트롤의 내용을 읽고 조작합니다.

```python
# 포커스 객체의 텍스트 가져오기
obj = api.getFocusObject()
info = obj.makeTextInfo(textInfos.POSITION_CARET)  # 캐럿 위치
text = info.text

# 전체 텍스트
info = obj.makeTextInfo(textInfos.POSITION_ALL)
allText = info.text
```

---

## 📌 7. SpeedWork 관련 핵심 파일

### 7.1 wxPython 접근성
**파일**: `NVDAObjects/IAccessible/wx.py`

SpeedWork는 wxPython 기반이므로 이 파일이 가장 중요합니다!

**주요 클래스**:
- `Dialog`: wx.Dialog 처리
- `ListCtrl`: wx.ListCtrl 처리
- `ListBox`: wx.ListBox 처리 ⭐ **SpeedWork의 list_groups, list_items**
- `TextCtrl`: wx.TextCtrl 처리

---

## 📌 8. 추가 기능 구조

### 8.1 기본 디렉토리 구조
```
globalPlugins/
└── speedwork.py           # 전역 플러그인

또는

appModules/
└── speedwork.py           # 애플리케이션 모듈
```

### 8.2 manifest.ini (필수)
```ini
name = SpeedWork
summary = SpeedWork 접근성 향상
description = SpeedWork 애플리케이션의 NVDA 접근성을 개선합니다.
author = Your Name
url = https://example.com
version = 1.0.0
minimumNVDAVersion = 2023.1
lastTestedNVDAVersion = 2024.1
```

---

## 📌 9. 실전 예제

### 9.1 SpeedWork용 GlobalPlugin 뼈대
```python
import globalPluginHandler
import api
import ui
import controlTypes
from scriptHandler import script

class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    """SpeedWork 접근성 향상 플러그인"""

    def __init__(self):
        super().__init__()

    def terminate(self):
        super().terminate()

    def event_gainFocus(self, obj, nextHandler):
        """포커스 이벤트"""
        # SpeedWork 윈도우인지 확인
        if self._isSpeedWorkWindow(obj):
            # SpeedWork 특화 처리
            if obj.role == controlTypes.Role.LISTITEM:
                ui.message(f"항목: {obj.name}")
        nextHandler()

    def _isSpeedWorkWindow(self, obj):
        """SpeedWork 윈도우 판별"""
        while obj:
            if hasattr(obj, 'windowClassName'):
                if 'speedwork' in obj.windowClassName.lower():
                    return True
            obj = obj.parent
        return False

    @script(
        description="SpeedWork 상태 확인",
        category="SpeedWork",
        gesture="kb:NVDA+shift+s"
    )
    def script_checkStatus(self, gesture):
        """NVDA+Shift+S: 상태 확인"""
        obj = api.getFocusObject()
        ui.message(f"포커스: {obj.name}, 역할: {obj.role}")
```

---

## 📌 10. 디버깅 팁

### 10.1 NVDA 로그 확인
```python
import logging
log = logging.getLogger(__name__)

log.info("정보 로그")
log.warning("경고 로그")
log.error("오류 로그")
log.debug("디버그 로그")
```

### 10.2 Python 콘솔
- `NVDA+Control+Z`: Python 콘솔 열기
- 실시간으로 객체 정보 확인 가능

```python
>>> focus = api.getFocusObject()
>>> focus.name
'항목 이름'
>>> focus.role
Role.LISTITEM
>>> focus.windowClassName
'wxWindowNR'
```

---

## 📌 11. 참고 자료

**공식 문서**:
- NVDA 개발자 가이드: https://www.nvaccess.org/files/nvda/documentation/developerGuide.html
- NVDA API 문서: (소스 코드 내 docstring)

**주요 학습 순서**:
1. `globalPluginHandler.py` - 플러그인 기본 구조
2. `ui.py` + `speech/speech.py` - 음성 출력
3. `api.py` - 객체 접근
4. `NVDAObjects/__init__.py` - 객체 시스템
5. `NVDAObjects/IAccessible/wx.py` - wxPython 지원
6. `gui/guiHelper.py` - GUI 생성
7. `scriptHandler.py` + `inputCore.py` - 단축키

---

**이 문서는 NVDA 애드온 개발 시 빠른 참조를 위해 작성되었습니다.**
**실제 구현 세부사항은 소스 코드를 직접 참조하세요.**
