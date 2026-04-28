# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""튜토리얼 서브패키지 공개 API.

진입점은 단일 함수 `open_tutorial(parent, source)`. 스크립트·설정 패널·
첫 실행 prompt 세 경로 모두 이 함수를 호출한다. 애드온 내부 의존(plugin
reference 등)은 본 패키지 내부에서 store 모듈로 디스크를 직접 읽어 해결,
호출자는 parent 창만 넘기면 된다.
"""

import os

import wx
import gui
import ui
import speech
from logHandler import log

from .. import store
from ..windowInfo import config_addon_dir
# `.dialog` 및 그 체인(`dialog` → `steps` → `windowEnum`)은 부팅 시점에 필요 없다.
# `GlobalPlugin.__init__` 동기 구간 단축을 위해 `open_tutorial` 내부에서 지연 import.
from .state import is_tutorial_shown, mark_tutorial_shown

# 번역 초기화(선택).
try:
    import addonHandler
    addonHandler.initTranslation()
    _  # noqa: F401
except Exception:
    def _(s):
        return s


__all__ = ["open_tutorial", "is_tutorial_shown", "mark_tutorial_shown"]


def open_tutorial(parent, source: str = "manual") -> None:
    """튜토리얼 다이얼로그를 모달로 연다.

    Args:
        parent: wx 부모 창. 일반적으로 gui.mainFrame.
        source: 진입 경로 로그용. "manual" / "settings" / "first_run" / "shortcut".
            NVDA 로그로 "어디서 튜토리얼이 열렸는지" 추적하는 진단 필드.

    내부적으로 디스크에서 appList와 meta를 로드해 context에 주입한다. 설정 패널
    경로처럼 plugin reference가 없는 호출자도 동일하게 사용 가능하게 하는 설계.
    """
    app_list_file = os.path.join(config_addon_dir(), "app.list")
    try:
        app_list = store.load(app_list_file)
    except Exception:
        log.exception("mtwn: tutorial open — store.load failed, starting with empty list")
        app_list = []

    def _get_meta(entry):
        try:
            return store.get_meta(app_list_file, entry) or {}
        except Exception:
            log.exception(f"mtwn: tutorial get_meta failed entry={entry!r}")
            return {}

    def _on_finish(kind: str) -> None:
        """종료 직후 후처리.

        "try_now"만 별도 안내 메시지 — 사용자가 실제 등록을 하러 가겠다고
        명시 선택한 결과 보고. "completed"/"skipped"는 조용히 종료해
        중복 낭독 피함 (CLAUDE.md 불변 원칙 6: UI 안내 선제 추가 금지).
        """
        log.info(f"mtwn: tutorial closed source={source!r} kind={kind!r}")
        if kind == "try_now":
            ui.message(
                _(
                    "Alt+Tab으로 원하는 창으로 이동한 뒤 NVDA+Shift+T를 누르세요. "
                    "창만 등록할지 앱 전체로 등록할지 묻는 다이얼로그가 먼저 떠요."
                ),
                speechPriority=speech.Spri.NEXT,
            )

    context = {
        "app_list": app_list,
        "get_meta": _get_meta,
        "app_list_file": app_list_file,
        # self_hwnd는 Phase 3에서 EnumWindows 필터용. 다이얼로그 생성 후에만 알 수 있어
        # 빌더가 필요 시 dialog.GetHandle()을 직접 받을 수 있도록 dialog가 context에 주입.
    }

    # 부팅 동기 구간 보호를 위해 `TutorialDialog` 및 그 체인은 여기서만 로드.
    # 첫 실행 안내 경로에서는 `prompt._show_prompt`가 `wx.CallAfter(open_tutorial, ...)`
    # 로 위임하므로 이 시점에도 메인 루프가 한 틱 양보된 뒤라 안전.
    from .dialog import TutorialDialog

    gui.mainFrame.prePopup()
    try:
        dialog = TutorialDialog(parent or gui.mainFrame, context, on_finish=_on_finish)
        try:
            dialog.ShowModal()
        finally:
            dialog.Destroy()
    finally:
        gui.mainFrame.postPopup()
