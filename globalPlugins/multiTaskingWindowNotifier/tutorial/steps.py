# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""튜토리얼 6단계 빌더.

각 step은 `(step_id, builder)` 튜플로 STEPS 리스트에 등록된다. 빌더는
`(panel: wx.Panel, context: dict) -> None` 시그니처로 주어진 panel에 UI
요소를 얹고 sizer를 설정한다. panel 생성/파괴는 dialog.TutorialDialog가
전담해 빌더는 "무엇을 그릴지"에만 집중한다.

Phase 2 범위: welcome, shortcuts 본문 채움 + 나머지 4개는 placeholder.
Phase 3에서 preview_beep, window_list, registered_list, try_it 본문 확장.

context 주입 필드:
    - app_list: list[str]      등록된 entry 키 리스트 (Step 5)
    - get_meta: callable       entry → meta dict (Step 5)
    - self_hwnd: int           튜토리얼 창 자신의 hwnd (Step 3에서 제외)
    - finish: callable(kind)   "completed" | "skipped" | "try_now" 요청
"""

import wx

# 번역 초기화(선택). NVDA 외 환경에서 _를 정의해두는 폴백.
try:
    import addonHandler
    addonHandler.initTranslation()
    _  # noqa: F401
except Exception:
    def _(s):
        return s


# Translators: 각 단계 상단에 붙는 이름 라벨. 진행률과 결합돼 "튜토리얼 — 1/6단계: 환영합니다" 형식으로 낭독된다.
TITLES = {
    "welcome": _("환영합니다"),
    "preview_beep": _("비프음 들어보기"),
    "window_list": _("지금 열려 있는 창"),
    "shortcuts": _("창을 등록하는 법"),
    "registered_list": _("이미 등록된 목록 확인"),
    "try_it": _("실제로 해보기"),
}


def _add_lines(panel, lines):
    """StaticText 여러 줄을 세로로 쌓고 panel에 SetSizer. 공통 패턴."""
    sizer = wx.BoxSizer(wx.VERTICAL)
    for line in lines:
        sizer.Add(wx.StaticText(panel, label=line), flag=wx.BOTTOM, border=6)
    panel.SetSizer(sizer)


# -------- Step 1: Welcome --------

def build_step_welcome(panel, context):
    _add_lines(panel, [
        _("창 전환 알림 애드온에 오신 걸 환영해요."),
        _("Alt+Tab으로 창을 전환할 때 창마다 다른 비프음이 울려 빠르게 구분할 수 있어요."),
        _("다음 단계로 넘기면서 핵심 사용법을 익혀봐요."),
        _("이 튜토리얼은 NVDA 설정 > 창 전환 알림 패널에서 언제든 다시 볼 수 있어요."),
    ])


# -------- Step 2: Preview beep (Phase 3 예정) --------

def build_step_preview_beep(panel, context):
    # Phase 3에서 beepPlayer.play_preview 재활용한 "미리듣기" 버튼 추가.
    _add_lines(panel, [
        _("등록된 창마다 서로 다른 비프음이 울려요."),
        _("이 단계는 다음 업데이트에서 미리듣기 버튼으로 확장될 예정이에요."),
    ])


# -------- Step 3: Window list (Phase 3 예정) --------

def build_step_window_list(panel, context):
    # Phase 3에서 EnumWindows 결과 ListBox 추가.
    _add_lines(panel, [
        _("지금 열려 있는 창 목록을 이 단계에서 볼 수 있어요."),
        _("현재는 준비 중이며, 다음 업데이트에서 창 목록이 표시돼요."),
    ])


# -------- Step 4: Shortcuts --------

def build_step_shortcuts(panel, context):
    _add_lines(panel, [
        _("등록·삭제·목록 보기는 단축키로 빠르게 할 수 있어요."),
        _("NVDA+Shift+T: 지금 포커스된 창이나 앱을 목록에 추가"),
        _("NVDA+Shift+D: 지금 포커스된 창이나 앱을 목록에서 삭제"),
        _("NVDA+Shift+I: 등록된 목록을 다이얼로그로 열기 (삭제·편집·순서 변경 가능)"),
        _("NVDA+Shift+R: 목록 파일을 디스크에서 다시 불러오기"),
        _("단축키가 불편하면 NVDA > 환경 설정 > 입력 제스처에서 원하는 키로 바꿀 수 있어요."),
    ])


# -------- Step 5: Registered list (Phase 3 예정) --------

def build_step_registered_list(panel, context):
    # Phase 3에서 context["app_list"] + context["get_meta"]로 ListBox 채움.
    _add_lines(panel, [
        _("지금까지 등록한 창과 앱 목록을 이 단계에서 훑어볼 수 있어요."),
        _("현재는 준비 중이며, 다음 업데이트에서 등록 목록이 표시돼요."),
    ])


# -------- Step 6: Try it (Phase 3 예정) --------

def build_step_try_it(panel, context):
    # Phase 3에서 "닫고 지금 해보기(&T)" 버튼 추가 → context["finish"]("try_now").
    _add_lines(panel, [
        _("튜토리얼을 닫고 바로 등록을 시도해볼 수 있어요."),
        _("Alt+Tab으로 원하는 앱(메모장, 브라우저 등)으로 이동한 뒤 NVDA+Shift+T를 누르면 돼요."),
        _("이 단계의 '닫고 지금 해보기' 버튼은 다음 업데이트에서 추가돼요."),
        _("지금은 '완료' 버튼을 눌러 튜토리얼을 끝낼 수 있어요."),
    ])


STEPS = [
    ("welcome", build_step_welcome),
    ("preview_beep", build_step_preview_beep),
    ("window_list", build_step_window_list),
    ("shortcuts", build_step_shortcuts),
    ("registered_list", build_step_registered_list),
    ("try_it", build_step_try_it),
]
