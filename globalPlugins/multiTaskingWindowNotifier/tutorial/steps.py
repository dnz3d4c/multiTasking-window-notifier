# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""튜토리얼 6단계 빌더.

각 step은 `(step_id, builder)` 튜플로 STEPS 리스트에 등록된다. 빌더는
`(panel: wx.Panel, context: dict) -> None` 시그니처로 주어진 panel에 UI
요소를 얹고 sizer를 설정한다. panel 생성/파괴는 dialog.TutorialDialog가
전담해 빌더는 "무엇을 그릴지"에만 집중한다.

context 주입 필드 (dialog 또는 open_tutorial에서 설정):
    - app_list: list[str]      등록된 entry 키 리스트 (Step 5)
    - get_meta: callable       entry → meta dict (Step 5)
    - finish: callable(kind)   "completed" | "skipped" | "try_now" 요청 (Step 6)

낭독 설계:
    - focusable 자식(ListBox/Button)이 첫 번째로 오게 배치 — dialog._show_step이
      title 낭독 후 focusable 첫 자식에 SetFocus를 걸어 "제목 → 컨트롤" 순서로
      들리게 한다. 설명 StaticText를 먼저 얹고 ListBox를 뒤에 얹으면 focusable
      첫 자식은 ListBox라 포커스가 ListBox로 감 — 설명 낭독은 Tab/화살표로 탐색.
"""

import wx

from .. import beepPlayer, settings
from ..constants import SCOPE_WINDOW
from ..listDialog import format_display_text
from ..presets import PRESETS, CLASSIC_PRESET_ID
from .windowEnum import enum_visible_top_windows

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


def _add_lines(sizer, parent, lines, spacing: int = 6):
    """StaticText 여러 줄을 sizer에 추가. 공통 패턴."""
    for line in lines:
        sizer.Add(wx.StaticText(parent, label=line), flag=wx.BOTTOM, border=spacing)


# -------- Step 1: Welcome --------

def build_step_welcome(panel, context):
    sizer = wx.BoxSizer(wx.VERTICAL)
    _add_lines(sizer, panel, [
        _("창 전환 알림 애드온에 오신 걸 환영해요."),
        _("Alt+Tab으로 창을 전환할 때 창마다 다른 비프음이 울려 빠르게 구분할 수 있어요."),
        _("다음 단계로 넘기면서 핵심 사용법을 익혀봐요."),
        _("이 튜토리얼은 NVDA 설정 > 창 전환 알림 패널에서 언제든 다시 볼 수 있어요."),
    ])
    panel.SetSizer(sizer)


# -------- Step 2: Preview beep --------

def build_step_preview_beep(panel, context):
    """'미리듣기' 버튼으로 현재 프리셋의 2음을 재생.

    settings 모듈에서 현재 beepPreset/beepDuration/beepGapMs를 직접 읽어
    설정 패널의 "미리듣기(&P)" 버튼과 동일 경로로 재생한다. 사용자는
    튜토리얼 안에서 자기 애드온이 실제로 내는 소리를 확인한다.
    """
    sizer = wx.BoxSizer(wx.VERTICAL)

    # 현재 선택된 프리셋 이름 안내. 미지 id면 classic 폴백.
    preset_id = settings.get("beepPreset")
    preset = PRESETS.get(preset_id) or PRESETS[CLASSIC_PRESET_ID]
    preset_name = _(preset["nameLabel"])

    _add_lines(sizer, panel, [
        _("등록된 창마다 서로 다른 비프음이 울려요."),
        _("'미리듣기' 버튼을 눌러 지금 설정된 비프 소리를 들어볼 수 있어요."),
        _("현재 프리셋: {name}").format(name=preset_name),
    ])

    # focusable 첫 자식이 되도록 버튼을 마지막에 추가. dialog._show_step이
    # 이 버튼에 SetFocus를 걸어 "제목 → 미리듣기 버튼" 순으로 낭독.
    # Translators: 현재 프리셋을 현장 재생하는 버튼. 액셀러레이터는 &L —
    # dialog 하단의 "이전(&P)"과 충돌하지 않도록 의도적으로 P가 아닌 L(들어보기).
    preview_btn = wx.Button(panel, label=_("들어보기(&L)"))

    def _on_preview(_event):
        duration = settings.get("beepDuration")
        gap_ms = settings.get("beepGapMs")
        beepPlayer.play_preview(preset_id, duration, gap_ms)

    preview_btn.Bind(wx.EVT_BUTTON, _on_preview)
    sizer.Add(preview_btn, flag=wx.TOP, border=6)
    panel.SetSizer(sizer)


# -------- Step 3: Window list --------

def build_step_window_list(panel, context):
    """현재 열린 top-level visible 창 목록을 ListBox로 표시.

    튜토리얼 다이얼로그 자신의 hwnd는 panel.GetTopLevelParent()로 얻어 필터.
    빌더에 별도 context 전달 없이 panel 자체에서 계산.
    """
    sizer = wx.BoxSizer(wx.VERTICAL)

    # 안내부. focusable 첫 자식이 아래 ListBox가 되도록 StaticText를 먼저 얹는다.
    _add_lines(sizer, panel, [
        _("지금 이 컴퓨터에 열려 있는 창 목록이에요."),
        _("튜토리얼을 닫은 뒤 이 중 원하는 창으로 Alt+Tab 이동해서 NVDA+Shift+T로 등록해 보세요."),
    ])

    # 자기 자신(튜토리얼 다이얼로그) hwnd 제외. TopLevelParent가 dialog.
    try:
        self_hwnd = int(panel.GetTopLevelParent().GetHandle())
    except Exception:
        self_hwnd = 0

    entries = enum_visible_top_windows(limit=50, exclude_hwnds={self_hwnd})

    if not entries:
        _add_lines(sizer, panel, [
            _("(창 목록을 불러오지 못했어요.)"),
        ])
        panel.SetSizer(sizer)
        return

    # Translators: 창 목록 ListBox 라벨.
    list_label = wx.StaticText(panel, label=_("열려 있는 창 ({n}개):").format(n=len(entries)))
    sizer.Add(list_label, flag=wx.TOP, border=6)

    listbox = wx.ListBox(
        panel,
        choices=[e["title"] for e in entries],
        style=wx.LB_SINGLE | wx.LB_HSCROLL,
        size=(560, 180),
    )
    sizer.Add(listbox, flag=wx.EXPAND | wx.TOP, border=2, proportion=1)
    panel.SetSizer(sizer)


# -------- Step 4: Shortcuts --------

def build_step_shortcuts(panel, context):
    sizer = wx.BoxSizer(wx.VERTICAL)
    _add_lines(sizer, panel, [
        _("등록·삭제·목록 보기는 단축키로 빠르게 할 수 있어요."),
        _("NVDA+Shift+T: 지금 포커스된 창이나 앱을 목록에 추가"),
        _("NVDA+Shift+D: 지금 포커스된 창이나 앱을 목록에서 삭제"),
        _("NVDA+Shift+I: 등록된 목록을 다이얼로그로 열기 (삭제·편집·순서 변경 가능)"),
        _("NVDA+Shift+R: 목록 파일을 디스크에서 다시 불러오기"),
        _("단축키가 불편하면 NVDA > 환경 설정 > 입력 제스처에서 원하는 키로 바꿀 수 있어요."),
    ])
    panel.SetSizer(sizer)


# -------- Step 5: Registered list --------

def build_step_registered_list(panel, context):
    """사용자가 등록한 창/앱 목록을 읽기 전용 ListBox로 표시.

    listDialog.format_display_text를 재활용해 "[앱]/[창] appId | title (대체: ...)"
    포맷으로 렌더. 삭제/편집/이동은 제공하지 않음 — 튜토리얼 목적은 "내가
    등록한 게 어떻게 저장돼 있는지 훑어보기". 편집은 NVDA+Shift+I로 안내.
    """
    sizer = wx.BoxSizer(wx.VERTICAL)

    app_list = context.get("app_list") or []
    get_meta = context.get("get_meta") or (lambda e: {})

    if not app_list:
        _add_lines(sizer, panel, [
            _("아직 등록된 항목이 없어요."),
            _("NVDA+Shift+T로 창을 추가해보고 이 단계로 다시 와서 확인할 수 있어요."),
        ])
        panel.SetSizer(sizer)
        return

    _add_lines(sizer, panel, [
        _("지금까지 등록한 창과 앱 목록이에요."),
        _("삭제·편집·순서 변경은 튜토리얼 밖에서 NVDA+Shift+I로 열어서 할 수 있어요."),
    ])

    # format_display_text는 wx 독립 순수 함수 — 단위 테스트도 가능한 형태로 재활용.
    def _line(entry):
        meta = get_meta(entry) or {}
        return format_display_text(
            entry,
            meta.get("scope", SCOPE_WINDOW),
            aliases=meta.get("aliases") or [],
        )

    # Translators: 등록된 목록 ListBox 라벨.
    list_label = wx.StaticText(panel, label=_("등록된 항목 ({n}개):").format(n=len(app_list)))
    sizer.Add(list_label, flag=wx.TOP, border=6)

    listbox = wx.ListBox(
        panel,
        choices=[_line(e) for e in app_list],
        style=wx.LB_SINGLE | wx.LB_HSCROLL,
        size=(560, 180),
    )
    sizer.Add(listbox, flag=wx.EXPAND | wx.TOP, border=2, proportion=1)
    panel.SetSizer(sizer)


# -------- Step 6: Try it --------

def build_step_try_it(panel, context):
    """마지막 단계. '닫고 지금 해보기' 버튼 제공.

    "완료" 버튼(dialog 하단)은 조용히 종료. "닫고 지금 해보기" 버튼은
    context["finish"]("try_now")로 종료 요청 — open_tutorial의 _on_finish가
    try_now 경로에서만 ui.message로 Alt+Tab 안내를 쏜다.
    """
    sizer = wx.BoxSizer(wx.VERTICAL)

    _add_lines(sizer, panel, [
        _("튜토리얼을 닫고 바로 등록을 시도해볼 수 있어요."),
        _("'닫고 지금 해보기'를 누르면 튜토리얼이 닫히고 안내가 나와요."),
        _("또는 '완료' 버튼으로 조용히 끝낼 수 있어요 — 언제든 설정 패널에서 다시 열 수 있어요."),
    ])

    # Translators: Step 6의 즉시 실습 버튼.
    try_btn = wx.Button(panel, label=_("닫고 지금 해보기(&T)"))

    def _on_try(_event):
        finish = context.get("finish")
        if callable(finish):
            finish("try_now")

    try_btn.Bind(wx.EVT_BUTTON, _on_try)
    sizer.Add(try_btn, flag=wx.TOP, border=6)
    panel.SetSizer(sizer)


STEPS = [
    ("welcome", build_step_welcome),
    ("preview_beep", build_step_preview_beep),
    ("window_list", build_step_window_list),
    ("shortcuts", build_step_shortcuts),
    ("registered_list", build_step_registered_list),
    ("try_it", build_step_try_it),
]
