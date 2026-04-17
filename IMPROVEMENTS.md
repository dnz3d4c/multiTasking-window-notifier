# multiTaskingWindowNotifier 개선 포인트

NVDA API 레퍼런스를 기반으로 분석한 개선 사항입니다.

## 📌 1. 우선순위: 높음 (기능성 & 안정성)

### 1.1 설정 시스템 추가 (config 모듈 활용)
**현재**: 비프음 설정이 하드코딩됨 (130Hz~4978Hz, 100ms, 좌우 30)
**개선**:
```python
import config

# config/__init__.py에 설정 스키마 정의
confspec = {
    "beepDuration": "integer(default=100, min=50, max=500)",
    "beepVolumeLeft": "integer(default=30, min=0, max=100)",
    "beepVolumeRight": "integer(default=30, min=0, max=100)",
    "maxItems": "integer(default=64, min=1, max=100)",
}
config.conf.spec["multiTaskingWindowNotifier"] = confspec

# 사용
duration = config.conf["multiTaskingWindowNotifier"]["beepDuration"]
tones.beep(BEEP_TABLE[idx], duration, left, right)
```
**참조**: `레퍼런스 5.1 config (설정)` - 설정 읽기/쓰기, 저장

---

### 1.2 GUI 설정 패널 추가 (guiHelper 활용)
**현재**: 설정 변경이 불가능 (파일 수정만 가능)
**개선**: NVDA 설정에 전용 패널 추가
```python
from gui import settingsDialogs, guiHelper
import wx

class MultiTaskingSettingsPanel(settingsDialogs.SettingsPanel):
    title = "창 전환 알림"

    def makeSettings(self, settingsSizer):
        sHelper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)

        # 비프음 길이 조정
        self.durationSpin = sHelper.addLabeledControl(
            "비프음 길이 (ms):",
            wx.SpinCtrl,
            min=50, max=500,
            initial=config.conf["multiTaskingWindowNotifier"]["beepDuration"]
        )

        # 최대 항목 수
        self.maxItemsSpin = sHelper.addLabeledControl(
            "최대 항목:",
            wx.SpinCtrl,
            min=1, max=100,
            initial=config.conf["multiTaskingWindowNotifier"]["maxItems"]
        )

    def onSave(self):
        config.conf["multiTaskingWindowNotifier"]["beepDuration"] = \
            self.durationSpin.GetValue()
        config.conf["multiTaskingWindowNotifier"]["maxItems"] = \
            self.maxItemsSpin.GetValue()
```
**참조**: `레퍼런스 2.1~2.2 guiHelper, settingsDialogs`

---

### 1.3 로깅 추가 (logging 모듈)
**현재**: 디버깅이 어려움 (에러 발생 시 추적 불가)
**개선**:
```python
import logging
log = logging.getLogger(__name__)

# AppListStore.load
try:
    with open(path, "r", encoding="utf-8") as f:
        items = [line.strip() for line in f if line.strip()]
    log.info(f"앱 목록 로드 완료: {len(items)}개")
except FileNotFoundError:
    log.warning(f"app.list 파일이 없습니다: {path}")
    items = []
except Exception as e:
    log.error(f"앱 목록 로드 실패: {e}", exc_info=True)
    ui.message(f"앱 목록을 여는 중 문제가 생겼어요: {e}")
    items = []
```
**참조**: `레퍼런스 12.1 디버깅 팁 - NVDA 로그 확인`

---

### 1.4 windowClassName 조건 제거 또는 설정화
**현재**: `"Windows.UI.Input.InputSite.WindowClass"`에서만 동작
**문제**: 대부분의 일반 앱에서 작동하지 않음
**개선**:
```python
# 옵션 1: 조건 제거 (모든 창에서 동작)
def event_gainFocus(self, obj, nextHandler):
    o = api.getFocusObject()
    if o:
        title = (getattr(o, "name", "") or "").strip()
        if title:
            # 비프음 재생 로직
            ...
    nextHandler()

# 옵션 2: 설정으로 제어
if config.conf["multiTaskingWindowNotifier"]["enableAllWindows"] or \
   getattr(o, "windowClassName", "") == "Windows.UI.Input.InputSite.WindowClass":
    # 비프음 재생
```
**이유**: Alt+Tab으로 전환 가능한 대부분의 창은 다른 windowClassName을 가짐

---

## 📌 2. 우선순위: 중간 (사용성 개선)

### 2.1 브라우저블 메시지로 목록 표시 (ui.browseableMessage)
**현재**: wxPython 다이얼로그 사용
**개선**: HTML 형식의 브라우저블 메시지 활용
```python
@script(description="등록된 창 목록 보기", gesture="kb:NVDA+shift+i")
def script_showAllEntries(self, gesture=None):
    if not self.appList:
        ui.message("등록된 창이 없어요.")
        return

    # HTML 생성
    html_lines = ["<h1>등록된 창 목록</h1>", f"<p>총 {len(self.appList)}개</p>", "<ul>"]
    for entry in sorted(self.appList):
        appId, title = _splitKey(entry)
        html_lines.append(f"<li><b>{appId or '앱 미지정'}</b> | {title}</li>")
    html_lines.append("</ul>")

    html = "\n".join(html_lines)
    ui.browseableMessage(html, title="등록된 창 목록", isHtml=True)
```
**장점**:
- 스크린 리더 친화적 (브라우즈 모드 사용 가능)
- wxPython GUI 대비 간단
- 복사/검색 가능
**참조**: `레퍼런스 1.4 UI - browseableMessage`

---

### 2.2 음성 우선순위 지정 (speech.Spri)
**현재**: ui.message의 기본 우선순위 사용
**개선**:
```python
from speech import Spri

# 즉시 알려야 하는 경우
ui.message("이미 목록에 있어요.", speechPriority=Spri.NOW)

# 일반적인 경우
ui.message("추가했어요", speechPriority=Spri.NEXT)
```
**참조**: `레퍼런스 1.3 Speech - 우선순위`

---

### 2.3 단축키 충돌 가능성 체크
**현재**: NVDA+Shift+T/D/R/I 사용
**문제**: 다른 애드온과 충돌 가능
**개선**:
- 카테고리를 한글로 통일: `"창 전환 알림"`
- 제스처를 사용자가 변경 가능하도록 주석 추가
```python
@script(
    description="현재 창 추가",
    category="창 전환 알림",
    gesture="kb:NVDA+shift+t"  # 사용자 정의 가능
)
```
**참조**: `레퍼런스 3.2 scriptHandler - 스크립트 데코레이터`

---

### 2.4 다이얼로그 개선 (guiHelper 활용)
**현재**: 수동으로 wxPython 레이아웃 구성
**개선**:
```python
from gui import guiHelper

class AppListDialog(wx.Dialog):
    def _create_ui(self):
        mainSizer = wx.BoxSizer(wx.VERTICAL)
        sHelper = guiHelper.BoxSizerHelper(self, wx.VERTICAL)

        # 자동 간격 처리
        countLabel = wx.StaticText(self, label=f"총 {len(self.appList)}개")
        sHelper.addItem(countLabel)

        self.listBox = sHelper.addLabeledControl(
            "등록된 창:",
            wx.ListBox,
            choices=display_items,
            style=wx.LB_SINGLE | wx.LB_HSCROLL,
            size=(500, 300)
        )

        # 버튼 그룹
        bHelper = guiHelper.ButtonHelper(wx.HORIZONTAL)
        okBtn = bHelper.addButton(self, id=wx.ID_OK, label="확인")
        okBtn.SetDefault()
        sHelper.addItem(bHelper)

        mainSizer.Add(
            sHelper.sizer,
            border=guiHelper.BORDER_FOR_DIALOGS,
            flag=wx.ALL
        )
        self.SetSizer(mainSizer)
        mainSizer.Fit(self)
```
**참조**: `레퍼런스 2.1 guiHelper - BoxSizerHelper`

---

## 📌 3. 우선순위: 낮음 (최적화 & 고급 기능)

### 3.1 appModuleHandler 활용
**현재**: `obj.appModule.appName`으로 직접 접근
**개선**: appModuleHandler 사용
```python
import appModuleHandler

def _getAppId(obj) -> str:
    try:
        appModule = appModuleHandler.getAppModuleForNVDAObject(obj)
        appId = appModule.appName if appModule else ""
    except Exception:
        appId = ""

    if not appId:
        appId = getattr(obj, "windowClassName", "") or "unknown"
    return appId
```
**참조**: `레퍼런스 8.1 appModuleHandler`

---

### 3.2 비프음 테이블 커스터마이징 (tones 모듈)
**현재**: 64개 고정 주파수
**개선**: 사용자 정의 범위
```python
def generate_beep_table(start_hz, end_hz, count):
    """등비수열로 비프음 테이블 생성"""
    ratio = (end_hz / start_hz) ** (1 / (count - 1))
    return [int(start_hz * (ratio ** i)) for i in range(count)]

# 설정에서 읽기
start_hz = config.conf["multiTaskingWindowNotifier"]["beepStartHz"]
end_hz = config.conf["multiTaskingWindowNotifier"]["beepEndHz"]
BEEP_TABLE = generate_beep_table(start_hz, end_hz, MAX_ITEMS)
```
**참조**: `레퍼런스 6.3 tones`

---

### 3.3 이벤트 필터링 최적화
**현재**: 모든 gainFocus 이벤트를 처리
**개선**: requestEvents 또는 shouldAcceptEvent 활용 (고급)
```python
# globalPlugin __init__에서
import eventHandler

# 특정 프로세스의 이벤트만 수신 (선택적)
eventHandler.requestEvents(
    "gainFocus",
    processId=None,  # 모든 프로세스
    windowClassName="Windows.UI.Input.InputSite.WindowClass"
)
```
**참조**: `레퍼런스 4.1 eventHandler - requestEvents`

---

### 3.4 창 전환 통계 기능 (보류 아이디어 #9 구현)
```python
import json
from datetime import datetime

class WindowStats:
    def __init__(self, stats_file):
        self.stats_file = stats_file
        self.stats = self.load()

    def load(self):
        try:
            with open(self.stats_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {"daily": {}, "weekly": {}}

    def record_switch(self, key):
        today = datetime.now().strftime("%Y-%m-%d")
        if today not in self.stats["daily"]:
            self.stats["daily"][today] = {}
        self.stats["daily"][today][key] = \
            self.stats["daily"][today].get(key, 0) + 1

    def get_top_windows(self, n=5):
        today = datetime.now().strftime("%Y-%m-%d")
        if today not in self.stats["daily"]:
            return []
        items = sorted(
            self.stats["daily"][today].items(),
            key=lambda x: x[1],
            reverse=True
        )
        return items[:n]

# GlobalPlugin에서 사용
def __init__(self):
    super().__init__()
    # ...
    stats_file = os.path.join(self.appDir, "stats.json")
    self.stats = WindowStats(stats_file)

def event_gainFocus(self, obj, nextHandler):
    # ...
    if idx is not None:
        self.stats.record_switch(key)
    nextHandler()
```

---

## 📌 4. 권장 개선 순서

1. **1.4 windowClassName 조건 제거** (즉시 효과)
2. **1.1 설정 시스템 추가** (확장성)
3. **1.3 로깅 추가** (디버깅)
4. **1.2 GUI 설정 패널** (사용성)
5. **2.1 브라우저블 메시지** (접근성)
6. **2.4 다이얼로그 개선** (코드 품질)
7. 나머지는 필요에 따라

---

## 📌 5. 참조 문서

- **공식 개발자 가이드**: https://www.nvaccess.org/files/nvda/documentation/developerGuide.html
- **현재 프로젝트 문서**: `CLAUDE.md`
