# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""튜토리얼 단계 빌더 (현재 7단계).

각 step은 `(step_id, builder)` 튜플로 STEPS 리스트에 등록된다. 빌더는
`(panel: wx.Panel, context: dict) -> None` 시그니처로 주어진 panel에 UI
요소를 얹고 sizer를 설정한다. panel 생성/파괴는 dialog.TutorialDialog가
전담해 빌더는 "무엇을 그릴지"에만 집중한다.

context 주입 필드 (dialog 또는 open_tutorial에서 설정):
    - app_list: list[str]      등록된 entry 키 리스트 (registered_list 단계)
    - get_meta: callable       entry → meta dict (registered_list 단계)
    - finish: callable(kind)   "completed" | "skipped" | "try_now" 요청 (try_it 단계)

낭독 설계:
    설명 텍스트는 readonly multiline TextCtrl로 렌더(_add_description). TextCtrl이
    AcceptsFocus=True라 각 빌더에서 첫 자식으로 얹으면 dialog._show_step의
    "첫 focusable 자식 SetFocus" 로직이 자동으로 설명에 포커스를 건다. 사용자는
    위/아래 화살표로 줄 단위 낭독, Tab으로 후속 ListBox/버튼으로 이동한다.
    별도 ui.message로 본문을 쏘지 않는다 — NVDA의 포커스 낭독으로 충분.

빌더 계약:
    각 빌더는 _add_description을 최상단에서 한 번 호출해야 한다. dialog가
    panel.GetChildren() 순서(= sizer Add 순서)에서 첫 focusable 자식을
    찾는데, 설명 TextCtrl보다 앞에 Button/ListBox가 오면 포커스가 그쪽으로
    가서 설명 낭독이 다시 우회된다. Step 3/5의 빈 상태 분기도 동일 — 설명만
    남을 때도 _add_description을 먼저 얹는다.
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


# Translators: 각 단계 상단에 붙는 이름 라벨. 진행률과 결합돼 "튜토리얼 — 1/7단계: 환영합니다" 형식으로 낭독된다.
TITLES = {
    "welcome": _("환영합니다"),
    "preview_beep": _("비프음 들어보기"),
    "window_list": _("지금 열려 있는 창"),
    "scope_intro": _("창 등록과 앱 등록의 차이"),
    "shortcuts": _("창을 등록하는 법"),
    "registered_list": _("이미 등록된 목록 확인"),
    "try_it": _("실제로 해보기"),
}


def _add_description(sizer, parent, lines, *, proportion=0):
    """설명 텍스트를 readonly multiline TextCtrl로 렌더.

    숨긴 StaticText를 연관 라벨로 두어 Windows UIA가 accessible name으로
    노출하게 한다. NVDA 본체(gui/addonStoreGui/controls/details.py)가 같은
    관용을 쓰며 wx.Accessible을 TextCtrl에 적용하면 컨트롤 접근성이 전부
    리셋된다는 공식 주석이 있어 피한다.

    proportion=0: 뒤에 ListBox/버튼이 오는 단계(2/3/5/6).
    proportion=1: 설명이 본문 전체인 단계(1/4).
    """
    # Translators: 튜토리얼 설명 편집창의 숨긴 접근성 라벨.
    label = wx.StaticText(parent, label=_("튜토리얼 설명"))
    label.Hide()
    sizer.Add(label)

    text = "\n".join(lines)
    ctrl = wx.TextCtrl(
        parent,
        value=text,
        style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2,
    )
    # MinSize 120: Step 4 6줄 본문이 기본 렌더에서 잘리지 않게. 상한은
    # dialog._contentPanel.SetMinSize((560, 300))이 방어.
    ctrl.SetMinSize((560, 120))
    # value=로 초기값 주입 시 wx가 커서를 마지막 문자 위치로 둬서
    # NVDA가 첫 포커스에서 마지막 줄을 읽는 증상이 난다. 0으로 리셋.
    ctrl.SetInsertionPoint(0)
    sizer.Add(
        ctrl,
        flag=wx.EXPAND | wx.BOTTOM,
        border=6,
        proportion=proportion,
    )
    return ctrl


# -------- Step 1: Welcome --------

def build_step_welcome(panel, context):
    sizer = wx.BoxSizer(wx.VERTICAL)
    _add_description(sizer, panel, [
        _("창 전환 알림 애드온에 오신 걸 환영해요."),
        _("NVDA의 음성 낭독을 기다리지 않아도, 창마다 미리 정해둔 비프음으로"),
        _("어떤 창인지 즉시 알 수 있어요."),
        _("등록한 창에만 비프음이 울려요."),
        _("등록하지 않은 창은 평소처럼 NVDA가 제목을 낭독해요."),
        _("위·아래 화살표 키로 이 안내문을 다시 들을 수 있어요."),
        _("Tab 키로 버튼이나 목록으로 이동할 수 있어요."),
    ], proportion=1)
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

    _add_description(sizer, panel, [
        _("등록된 창마다 서로 다른 비프음이 울려요."),
        _("비프는 두 음으로 이루어져요."),
        _("첫 음은 '어떤 앱'인지, 두 번째 음은 '그 앱 안의 어떤 창'인지 알려줘요."),
        _("Tab 키로 '미리듣기' 버튼으로 이동한 뒤 Enter 키로 재생할 수 있어요."),
        _("현재 프리셋: {name}").format(name=preset_name),
    ])

    # 라벨 단어는 settingsPanel의 "미리듣기(&P)"와 일치(어휘 SSOT). 단 액셀러레이터는
    # 의도적 분리 — dialog 하단의 "이전(&P)"과 같은 top-level 모달에 있어 동일 평면
    # 액셀러레이터 충돌 회피를 위해 &L 사용. 사용자는 Alt+L로 트리거 가능.
    # Translators: 현재 프리셋을 재생하는 버튼.
    preview_btn = wx.Button(panel, label=_("미리듣기(&L)"))

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

    _add_description(sizer, panel, [
        _("지금 이 컴퓨터에 열려 있는 창 목록이에요."),
        _("Tab 키로 창 목록으로 이동한 뒤 위·아래 화살표 키로 항목을 훑어볼 수 있어요."),
        _("튜토리얼을 닫은 뒤 이 중 원하는 창으로 Alt+Tab으로 이동한 다음"),
        _("NVDA+Shift+T를 눌러 등록할 수 있어요."),
    ])

    # 자기 자신(튜토리얼 다이얼로그) hwnd 제외. TopLevelParent가 dialog.
    try:
        self_hwnd = int(panel.GetTopLevelParent().GetHandle())
    except Exception:
        self_hwnd = 0

    entries = enum_visible_top_windows(limit=50, exclude_hwnds={self_hwnd})

    if not entries:
        _add_description(sizer, panel, [
            _("(창 목록을 불러오지 못했어요.)"),
        ], proportion=1)
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


# -------- Step 4: Scope intro (window vs app) --------

def build_step_scope_intro(panel, context):
    """창 등록과 앱 등록의 차이를 사전에 안내.

    이 단계는 Step 5(단축키 안내)와 Step 7(실습)에서 사용자가 NVDA+Shift+T를
    눌렀을 때 만나는 'scope 선택 다이얼로그'(scripts.py:138-178)를 미리 예고하는
    역할. 사실 일치 검증은 plan 파일의 'Phase 2 시작 전 사실 확인' 항목 참조.
    """
    sizer = wx.BoxSizer(wx.VERTICAL)
    # 빈 줄은 _("") 대신 ""로 직접 표기. 표준 gettext 명세상 gettext("")는 PO 파일의
    # 헤더 메타데이터(Project-Id-Version 등)를 반환하므로, 그대로 _add_description의
    # "\n".join(lines)에 박히면 다이얼로그가 깨진다. ""는 번역 대상이 아닌 단순 시각
    # 그룹 구분자 — 의미 그룹("창 등록"/"앱 등록"/"등록 절차") 사이의 호흡 분리용.
    _add_description(sizer, panel, [
        _("이 애드온은 등록 단위가 두 가지예요."),
        "",
        _("창 등록"),
        _("같은 브라우저라도 YouTube 탭과 GitHub 탭에 서로 다른 비프음을 줘요."),
        _("탭이나 창 단위로 세밀하게 구분하고 싶을 때 골라요."),
        "",
        _("앱 등록"),
        _("같은 앱의 어느 창이든 같은 비프음으로 통일해요."),
        _("창 제목이 자주 바뀌는 메신저 같은 앱에 적합해요."),
        "",
        _("NVDA+Shift+T를 누르면 둘 중 어느 쪽으로 등록할지 먼저 물어봐요."),
        _("그다음 '대체 제목' 입력창이 떠요."),
        _("Alt+Tab에서 다르게 들리는 이름이 있을 때만 입력하고, 없으면 빈 값으로 확인하면 돼요."),
    ], proportion=1)
    panel.SetSizer(sizer)


# -------- Step 5: Shortcuts --------

def build_step_shortcuts(panel, context):
    sizer = wx.BoxSizer(wx.VERTICAL)
    _add_description(sizer, panel, [
        _("등록, 삭제, 목록 보기는 단축키로 빠르게 할 수 있어요."),
        _("NVDA+Shift+T: 지금 보고 있는 창이나 앱을 목록에 추가"),
        _("NVDA+Shift+D: 지금 보고 있는 창이나 앱을 목록에서 삭제"),
        _("NVDA+Shift+I: 등록된 목록 다이얼로그 열기 (삭제, 편집, 순서 변경 가능)"),
        _("NVDA+Shift+R: 목록을 저장 파일에서 다시 읽기"),
        _("단축키가 불편하면 NVDA 메뉴 > 환경 설정 > 입력 제스처에서 원하는 키로 바꿀 수 있어요."),
    ], proportion=1)
    panel.SetSizer(sizer)


# -------- Step 6: Registered list --------

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
        _add_description(sizer, panel, [
            _("아직 등록된 항목이 없어요."),
            _("NVDA+Shift+T로 창을 추가하면 이 목록에 나타나요."),
            _("등록 후에는 NVDA+Shift+I로 언제든 목록 다이얼로그를 다시 열 수 있어요."),
        ], proportion=1)
        panel.SetSizer(sizer)
        return

    _add_description(sizer, panel, [
        _("지금까지 등록한 창과 앱 목록이에요."),
        _("목록 항목 앞의 '[창]' 또는 '[앱]'은 등록 단위를 뜻해요."),
        _("삭제, 편집, 순서 변경은 튜토리얼 밖에서 NVDA+Shift+I로 다시 열어 할 수 있어요."),
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


# -------- Step 7: Try it --------

def build_step_try_it(panel, context):
    """마지막 단계. '닫고 지금 해보기' 버튼 제공.

    "완료" 버튼(dialog 하단)은 조용히 종료. "닫고 지금 해보기" 버튼은
    context["finish"]("try_now")로 종료 요청 — open_tutorial의 _on_finish가
    try_now 경로에서만 ui.message로 Alt+Tab 안내를 쏜다.
    """
    sizer = wx.BoxSizer(wx.VERTICAL)

    _add_description(sizer, panel, [
        _("마지막 단계예요. 두 가지 방법으로 끝낼 수 있어요."),
        _("'닫고 지금 해보기' 버튼을 누르면 튜토리얼이 닫히고 다음 행동 안내가 음성으로 나와요."),
        _("다이얼로그 아래쪽의 '완료' 버튼을 누르면 추가 안내 없이 닫혀요."),
        _("두 경우 모두 NVDA 설정 > 창 전환 알림에서 언제든 다시 열 수 있어요."),
    ])

    # Translators: Step 7의 즉시 실습 버튼.
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
    ("scope_intro", build_step_scope_intro),
    ("shortcuts", build_step_shortcuts),
    ("registered_list", build_step_registered_list),
    ("try_it", build_step_try_it),
]
