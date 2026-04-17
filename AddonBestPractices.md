# NVDA 애드온 개발 실전 팁 & 베스트 프랙티스
> 출처: 실제 애드온 개발자들의 경험과 내부 분석
> - Golden Cursor: https://github.com/nvdaaddons/devguide/wiki/gcaddoninternals
> - StationPlaylist: https://github.com/ChrisDuffley/stationPlaylist/wiki/spladdoninternals
> - SysTray List: https://github.com/nvdaaddons/devguide/wiki/stladdoninternals

---

## 아키텍처 & 코드 조직

### 레이어 커맨드 패턴 (StationPlaylist)
**문제**: 컨텍스트별로 다른 명령 세트 필요
**해결**: 이중 레이어 시스템
- SPL Assistant (앱 모듈) - 상태 조회
- SPL Controller (전역 플러그인) - 원격 명령 실행

**구현**:
```python
# 동적 제스처 바인딩/제거
def activate_layer(self):
    self.bindGestures(self.layer_gestures)

def deactivate_layer(self):
    self.clearGestureBindings()

# getScript() 오버라이드로 컨텍스트 인식
def getScript(self, gesture):
    if self.layer_active:
        return self.layer_scripts.get(gesture)
    return super().getScript(gesture)
```

### 코드 구조화 전략 (StationPlaylist)
**조직 원칙**:
1. 오버레이 섹션
2. 기본 메서드
3. 시간 관련 명령
4. 기타 명령
5. 레이어 명령

**효과**: 버그 위치 파악 용이, 기능 배치 명확

### 패키지 스타일 구조 (SysTray List)
```
addon/
├── globalPlugins/
│   └── myAddon/
│       ├── __init__.py      # 진입점
│       ├── helpers.py        # 보조 함수
│       ├── dialogs.py        # UI 클래스
│       └── _internal.py      # 내부 로직
```

**원칙**: 책임 경계 명확히 분리

---

## 실전 구현 패턴

### 1. Windows API 통합 (Golden Cursor)
**패턴**: NVDA winUser 모듈을 통한 네이티브 호출 래핑

```python
from winUser import setCursorPos, getCursorPos

def move_mouse(x, y):
    setCursorPos(x, y)
    announce_position(x, y)
```

**장점**: 추상화로 API 변경 대응 용이

### 2. 스크립트 반복 감지 (SysTray List)
**패턴**: 한 키에 여러 기능 할당

```python
from scriptHandler import getLastScriptRepeatCount

@script(gesture="kb:nvda+f11")
def script_showIcons(self, gesture):
    count = getLastScriptRepeatCount()
    if count == 0:
        self.show_systray_icons()
    elif count == 1:
        self.show_taskbar_icons()
```

**활용**: 키 바인딩 절약, UX 개선

### 3. 버전별 UI 분기 (Golden Cursor)
**패턴**: NVDA 버전에 따라 UI 변경

```python
import versionInfo

if versionInfo.version_year >= 2018 and versionInfo.version_major >= 2:
    # 설정 패널 방식 (2018.2+)
    from gui import SettingsPanel
    class MySettings(SettingsPanel):
        pass
else:
    # 독립 다이얼로그 방식 (2018.1 이하)
    class MyDialog(wx.Dialog):
        pass
```

### 4. 중앙화된 API 래퍼 (StationPlaylist)
**패턴**: SendMessage 호출 추상화

```python
def studioAPI(command, arg=0):
    """Studio API 통신 래퍼"""
    hwnd = get_studio_window_handle()
    msg = WM_USER + 0x100
    return SendMessage(hwnd, msg, arg, command)

# 사용
track_count = studioAPI(SPL_CMD_GET_TRACK_COUNT)
```

**효과**: 보일러플레이트 감소, API 변경 집중 관리

### 5. 윈도우 핸들 체인 순회 (SysTray List)
**패턴**: FindWindowEx를 통한 계층 탐색

```python
from ctypes import windll

# Desktop → TrayWnd → NotifyWnd → Pager → Toolbar
desktop = windll.user32.GetDesktopWindow()
tray = windll.user32.FindWindowExW(desktop, 0, "shell_TrayWnd", None)
notify = windll.user32.FindWindowExW(tray, 0, "TrayNotifyWnd", None)
pager = windll.user32.FindWindowExW(notify, 0, "SysPager", None)
toolbar = windll.user32.FindWindowExW(pager, 0, "ToolbarWindow32", None)
```

**주의**: Windows 버전별 경로 차이 고려 필요

---

## 이벤트 처리 패턴

### 이벤트 기반 아키텍처 (StationPlaylist)
**패턴**: nameChange를 "심장박동"으로 활용

```python
def event_nameChange(self, obj, nextHandler):
    # 컨트롤 타입별 분기
    if obj.role == controlTypes.Role.STATUSBAR:
        self.handle_status_update(obj)
    elif obj.role == controlTypes.Role.STATICTEXT:
        self.handle_alarm_notification(obj)

    nextHandler()
```

**장점**: 확장 가능, 모놀리식 조건문 방지

### 백그라운드 이벤트 모니터링 (StationPlaylist)
**패턴**: 특정 컨트롤만 추적

```python
from eventHandler import requestEvents

# TRequests 윈도우 클래스만 모니터링
requestEvents(eventName="nameChange", windowClassName="TRequests")
```

**효과**: 불필요한 처리 오버헤드 방지

---

## 성능 최적화

### 1. 윈도우 스레딩 (StationPlaylist)
**문제**: FindWindowW 호출이 UI 블록
**해결**: 별도 스레드에서 1초마다 조회

```python
import threading

def find_studio_window_thread():
    while running:
        hwnd = windll.user32.FindWindowW("TStudioMainForm", None)
        cache_handle(hwnd)
        time.sleep(1)

thread = threading.Thread(target=find_studio_window_thread)
thread.daemon = True
thread.start()
```

### 2. 지연 초기화 (StationPlaylist)
**패턴**: 필수가 아닌 초기화 연기

```python
_config = None

def get_config():
    global _config
    if _config is None:
        _config = load_config()
    return _config
```

**효과**: 시작 시간 단축

### 3. 캐시된 객체 내비게이션 (StationPlaylist)
**문제**: 객체 트리 반복 탐색 비용 높음
**해결**: 로컬 계산으로 대체

```python
# 나쁜 예: 객체 트리 탐색
clock_obj = api.getForegroundObject().firstChild.next.next
time_str = clock_obj.name

# 좋은 예: Python 표준 라이브러리
import time
time_str = time.strftime("%H:%M:%S")
```

---

## 설정 관리

### 프로필 풀링 with 검증 (StationPlaylist)
**패턴**: 기본 프로필 + 레이어 프로필

```python
from configobj import ConfigObj
from validate import Validator

# 1. 기본 프로필 로드
base = ConfigObj("normal.ini", configspec="spec.ini")
base.validate(Validator())

# 2. 브로드캐스트 프로필 레이어
broadcast = ConfigObj("broadcast.ini")
base.merge(broadcast)

# 3. 메모리에 캐시
SPLConfig.profiles["current"] = base
```

### 온라인 캐시 메커니즘 (StationPlaylist)
**패턴**: 변경 감지 후 선택적 쓰기

```python
def save_config(profile_name):
    current = SPLConfig.profiles[profile_name]
    cached = SPLConfig.cache[profile_name]

    # 변경된 프로필만 디스크에 저장
    if current != cached:
        current.write()
        SPLConfig.cache[profile_name] = current.copy()
```

**효과**: 디스크 I/O 감소

### 휘발성 설정 플래그 (StationPlaylist)
**패턴**: 명령줄 스위치로 동작 변경

```python
import globalVars

if "--spl-configvolatile" in globalVars.appArgs.configPath:
    # 설정 변경 허용하지만 저장 안 함
    VOLATILE_MODE = True
```

**활용**: 코드 수정 없이 테스트

---

## 객체 오버레이 전략

### 트랙 아이템 계층 (StationPlaylist)
**패턴**: 추상 베이스 → 특수화

```python
# 1. 추상 베이스
class SPLTrackItem(NVDAObject):
    def get_track_info(self):
        raise NotImplementedError

# 2. Studio 특화
class SPLStudioTrackItem(SPLTrackItem):
    def get_track_info(self):
        return self.name.split(" - ")

# 3. 플레이리스트 뷰어 특화
class StudioPlaylistViewerItem(SPLStudioTrackItem):
    def get_track_info(self):
        info = super().get_track_info()
        info.append(self.get_duration())
        return info
```

**장점**: 로직 재사용, 여러 앱 지원

### MRO를 활용한 명령 스코프 제한 (StationPlaylist)
**패턴**: None 할당으로 부모 클래스 위임

```python
class PlaylistViewerItem(SPLTrackItem):
    # 이 컨텍스트에서는 편집 불가
    script_editTrack = None

    # 다른 명령은 부모로부터 상속
```

**효과**: 잘못된 컨텍스트에서 명령 사용 방지

---

## 칼럼 내비게이션 (StationPlaylist)

### SysListView32 활용
**패턴**: 설명 파싱 대신 메시지 전달

```python
from ctypes import windll, create_string_buffer

def get_column_text(hwnd, row, col):
    # 1. 대상 프로세스에 버퍼 할당
    buffer = windll.kernel32.VirtualAllocEx(
        process_handle, 0, 512, MEM_COMMIT, PAGE_READWRITE
    )

    # 2. 칼럼 텍스트 길이 요청
    SendMessage(hwnd, LVM_GETITEMTEXT, row, buffer)

    # 3. 메모리 읽기
    result = create_string_buffer(512)
    windll.kernel32.ReadProcessMemory(process_handle, buffer, result, 512, 0)

    # 4. 할당 해제
    windll.kernel32.VirtualFreeEx(process_handle, buffer, 0, MEM_RELEASE)

    return result.value.decode()
```

**장점**: 앱 버전 독립적, 칼럼 재정렬 지원

---

## 일반적인 함정 & 해결책

| 문제 | 해결책 |
|------|--------|
| **객체 탐색이 앱 버전별로 깨짐** | API/메시지 전달 사용; 중간 결과 캐싱 |
| **레이어 명령이 에러 후에도 활성** | try/finally로 클린업("finish") 함수 호출 |
| **설정 저장 시 파일 손상** | ConfigObj로 검증 후 쓰기; 백업 캐시 유지 |
| **백그라운드 이벤트가 리소스 소모** | 특정 윈도우 클래스만 등록; 조건 빠르게 체크 |
| **다이얼로그 중 포커스 손실** | `queueHandler.queueFunction()`로 클린업 지연 |
| **Boolean 비교 `== False`** | Pythonic 방식: `if not something:` |
| **유지보수 중단 위험** | 승계 계획 수립; 커뮤니티 채택 고려 |

---

## 상태 관리

### 플래그 기반 기능 제어 (StationPlaylist)
**패턴**: Boolean 플래그로 단순화

```python
class AppModule:
    def __init__(self):
        self.verbose_announcements = False
        self.braille_timer_active = False
        self.layer_active = False

    def toggle_verbose(self):
        self.verbose_announcements = not self.verbose_announcements
```

**vs 상태 머신**: 간단한 경우 플래그가 더 명확

### 스레드 안전 알람 타이머 (StationPlaylist)
**패턴**: 모듈 레벨 참조로 제어

```python
microphone_alarm_timer = None

def start_microphone_alarm():
    global microphone_alarm_timer
    if microphone_alarm_timer:
        microphone_alarm_timer.cancel()

    microphone_alarm_timer = wx.Timer()
    microphone_alarm_timer.Start(60000)  # 60초

def stop_microphone_alarm():
    global microphone_alarm_timer
    if microphone_alarm_timer:
        microphone_alarm_timer.Stop()
        microphone_alarm_timer = None
```

**효과**: 리소스 누수 방지

---

## 확장 포인트 활용 (NVDA 2017.4+)

### 액션 핸들러 등록 (StationPlaylist)
**패턴**: 프로필 전환 시 동기화

```python
from extensionPoints import Action

# 확장 포인트 생성
profile_switched = Action()

# 핸들러 등록
def on_profile_switch():
    restart_metadata_streaming()
    update_alarm_settings()

profile_switched.register(on_profile_switch)

# 트리거
profile_switched.notify()
```

**장점**: 기능 분리하면서 동기화 유지

---

## 디버깅 기법

### 1. 최소 모드 인식 (StationPlaylist)
```python
import globalVars

if not globalVars.appArgs.minimal:
    ui.message("디버그: 현재 상태")
```

### 2. 상태 메시지 큐잉 (StationPlaylist)
```python
from queueHandler import queueFunction

def debug_announce(text):
    queueFunction(queueHandler.eventQueue, ui.message, text)
```

**이유**: 스크린 리더 상태 존중

### 3. 예외 특정화 (StationPlaylist)
```python
if studio_version < MIN_SUPPORTED_VERSION:
    raise RuntimeError(f"Studio {studio_version} not supported")
```

**효과**: NVDA 에러 핸들링이 적절히 처리

### 4. 점자 디스플레이 테스트 (StationPlaylist)
```python
import braille

def debug_braille(text):
    braille.handler.message(text)
```

---

## 독특한 패턴

### 1. 중첩 다이얼로그 프레젠테이션 (StationPlaylist)
**패턴**: 단일 클래스로 여러 변형 제공

```python
class SPLFindDialog(wx.Dialog):
    def __init__(self, parent, mode="track"):
        self.mode = mode
        if mode == "track":
            self.setup_track_finder()
        elif mode == "column":
            self.setup_column_search()
```

**효과**: 코드 중복 감소, 통일된 동작

### 2. 레이어 클린업을 위한 함수 래핑 (StationPlaylist)
**패턴**: functools.wraps 데코레이터

```python
from functools import wraps

def ensure_cleanup(finish_func):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            finally:
                finish_func()
        return wrapper
    return decorator

@ensure_cleanup(lambda: deactivate_layer())
def layer_command(self):
    # 명령 실행
    pass
```

**출처**: Toggle/ToggleX 애드온에서 차용

### 3. 설명적 기능 이름 (StationPlaylist)
**원칙**: 일반적 이름 대신 구체적 이름

- ❌ "cart mode"
- ✅ "Cart Explorer"

**효과**: 발견 가능성 및 사용자 이해도 향상

---

## 설정 파일 패턴

### INI 포맷 포터빌리티 (Golden Cursor)
**패턴**: 앱별 파일 명명

```
coordinates/
├── outlook.gc    # Outlook 좌표
├── chrome.gc     # Chrome 좌표
└── notepad.gc    # Notepad 좌표
```

**내용 예시**:
```ini
[position1]
name=Send Button
x=120
y=450

[position2]
name=Inbox
x=50
y=200
```

**장점**: 시스템 간 이식 가능

---

## 설계 철학 (StationPlaylist)

### 4가지 원칙
1. **일관성** (Consistency): 통일된 인터페이스
2. **확장성** (Extensibility): 모듈식 서브컴포넌트
3. **관심사 분리** (Separation of concerns): 적절한 컨텍스트에서 기능 접근
4. **문서화 명확성** (Documentation clarity): 설계 결정 설명

---

## 체크리스트

### 코드 작성 전
- [ ] 비슷한 기능의 기존 애드온 조사
- [ ] NVDA 버전 호환성 범위 결정
- [ ] 모듈 구조 설계 (단일 vs 패키지)
- [ ] 설정 저장 방식 계획

### 구현 중
- [ ] API 호출은 래퍼로 추상화
- [ ] 이벤트 핸들러에서 nextHandler() 호출
- [ ] 예외 처리 명시적으로
- [ ] 성능 영향 큰 작업은 스레드 분리
- [ ] 설정은 검증 후 저장

### 배포 전
- [ ] 다양한 NVDA 버전에서 테스트
- [ ] 최소 모드에서 동작 확인
- [ ] 에러 메시지 사용자 친화적으로
- [ ] 문서화 (README, 사용 설명)
- [ ] 라이선스 명시

---

## 추가 학습 자료

### 실제 애드온 소스 분석 추천
1. **Golden Cursor** - Windows API 통합, 좌표 관리
2. **StationPlaylist** - 복잡한 상태 관리, 레이어 시스템
3. **SysTray List** - 윈도우 핸들 탐색, 간결한 구조
4. **Add-on Updater** - 네트워크 통신, 버전 관리
5. **Place Markers** - 북마크 저장, 파일 I/O

### 커뮤니티 리소스
- **NVDA Add-ons 메일링 리스트**: 질문 및 토론
- **GitHub Issues**: 버그 리포트 패턴 학습
- **NVDA API 메일링 리스트**: API 변경 공지
