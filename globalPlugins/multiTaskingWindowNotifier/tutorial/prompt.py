# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""첫 실행 안내 + 확인 다이얼로그.

NVDA 부팅 시점에 `GlobalPlugin.__init__`이 호출되면 본 모듈의
`maybe_show_first_run_prompt(plugin)`가 `core.postNvdaStartup` 액션 포인트에
콜백을 등록한다. NVDA가 welcome/startup을 모두 처리한 뒤 1회성으로 발화.

설계:
    - tutorialShown 플래그가 True면 즉시 return.
    - `core.postNvdaStartup.register(_on_nvda_ready)` — welcome 종료 후
      NVDA 이벤트 큐에 콜백 적재.
    - `_on_nvda_ready`는 queueHandler 컨텍스트에서 실행되므로 `wx.CallAfter`로
      한 틱 양보한 뒤 `_show_prompt` 실행.
    - `wx.MessageDialog(YES_NO)` 1회. YES → `open_tutorial`. 나머지 → 조용히 종료.
    - `mark_tutorial_shown`은 MessageDialog 생성 **성공 직후·ShowModal 진입
      직전**에 호출. 생성 자체가 실패(wx 리소스 부족 등)하면 플래그를 쓰지
      않아 다음 부팅에서 재시도 가능.

왜 `core.callLater`가 아닌 `postNvdaStartup`인가:
    `NVDA/source/core.py:1190` docstring이 공식 금기를 명시 —
    "callLater should never be used to execute code that brings up a
    modal UI as it will cause NVDA's core to block". callLater 자체는
    비동기(`wx.CallLater` 래핑)지만, 콜백에서 `ShowModal`을 호출하면
    welcome dialog의 중첩 modal 이벤트 루프와 엉켜 NVDA core 큐가
    정체된다. `postNvdaStartup`은 welcome 종료 후 발화가 보장되는 NVDA
    공식 액션 포인트(`core.py:53, 1056-1067`).

CLAUDE.md 불변 원칙 6: UI 안내 선제 추가 금지 — 본 모듈은 "첫 실행 1회의
사용자 선택권 제공"이라는 명시 목적이 있어 예외. `mark_tutorial_shown`으로
1회성이 보장되며 반복 낭독 리스크 없음.
"""

import wx
import gui
from logHandler import log

from .state import is_tutorial_shown, mark_tutorial_shown

# 번역 초기화(선택).
try:
    import addonHandler
    addonHandler.initTranslation()
    _  # noqa: F401
except Exception:
    def _(s):
        return s


# 모듈 수준 핸들러 참조. postNvdaStartup.register/unregister는 같은 함수 객체
# 식별로 동작하므로 보관해뒀다가 terminate 시점에 해제한다.
_registered_handler = None


def maybe_show_first_run_prompt(plugin) -> None:
    """첫 실행 사용자에게 튜토리얼 시청 여부를 물어본다.

    이미 노출됐으면(tutorialShown=True) 조용히 no-op. 아직이면
    `core.postNvdaStartup`에 콜백을 등록. welcome dialog가 종료된 뒤 NVDA
    이벤트 큐에서 콜백이 발화한다.

    중복 등록 방어: `_registered_handler`가 이미 세팅돼 있으면 skip. 애드온
    재로드 경로에서 `unregister_first_run_prompt`가 누락됐을 때의 구 인스턴스
    참조 누수를 방어한다. 정상 흐름에서는 terminate가 반드시 unregister를 호출.

    Args:
        plugin: GlobalPlugin 인스턴스. 예외 경로에서 log.exception을 위한
            식별용으로만 받음 — 실제로는 참조하지 않아 None도 허용.
    """
    if is_tutorial_shown():
        return

    global _registered_handler
    if _registered_handler is not None:
        # 같은 프로세스에서 두 번 호출됐거나, 이전 terminate가 unregister에
        # 실패한 경우. 중복 register 방지 목적으로 조용히 반환.
        return

    try:
        import core
        core.postNvdaStartup.register(_on_nvda_ready)
        _registered_handler = _on_nvda_ready
    except Exception:
        # 등록 실패도 본체 이벤트 훅을 막지 않도록 흡수.
        log.exception("mtwn: tutorial prompt register failed")
        _registered_handler = None


def unregister_first_run_prompt() -> None:
    """GlobalPlugin.terminate에서 호출. 애드온 재로드 시 구 인스턴스 누수 차단.

    등록된 적이 없으면 no-op. unregister 자체 예외는 다른 terminate 단계를
    막지 않도록 흡수한다.
    """
    global _registered_handler
    if _registered_handler is None:
        return
    try:
        import core
        core.postNvdaStartup.unregister(_registered_handler)
    except Exception:
        log.exception("mtwn: tutorial prompt unregister failed")
    finally:
        _registered_handler = None


def _on_nvda_ready() -> None:
    """`core.postNvdaStartup` 발화 시점 콜백.

    queueHandler 컨텍스트(이벤트 큐)에서 실행되므로 wx 모달은 한 틱 양보한 뒤
    올리는 것이 표준 — `wx.CallAfter`로 `_show_prompt`를 예약한다.

    등록 이후 사용자가 설정 패널에서 튜토리얼을 먼저 열었을 수도 있어
    `is_tutorial_shown` 재확인으로 중복 노출 방지.
    """
    if is_tutorial_shown():
        return
    wx.CallAfter(_show_prompt)


def _show_prompt() -> None:
    """실제로 확인 다이얼로그를 띄운다.

    `mark_tutorial_shown`은 MessageDialog 생성 성공 **직후**·ShowModal 진입
    **직전**에 호출. 생성 자체가 실패하면 플래그를 쓰지 않아 다음 부팅에서
    재시도 가능.
    """
    # 최종 체크: register → wx.CallAfter 사이에 사용자가 설정 패널에서
    # 튜토리얼을 먼저 열어 완료했을 수도 있음. 조용히 종료.
    if is_tutorial_shown():
        return

    result = None
    try:
        gui.mainFrame.prePopup()
        # Translators: 첫 실행 시 튜토리얼 시청 여부를 묻는 확인 다이얼로그의 본문.
        prompt_body = _(
            "창 전환 알림 애드온을 처음 실행했어요.\n"
            "핵심 사용법을 안내하는 튜토리얼을 지금 보시겠어요?\n"
            "예를 누르면 튜토리얼이 시작돼요.\n"
            "아니오를 눌러도 NVDA 설정 > 창 전환 알림에서 언제든 다시 볼 수 있어요."
        )
        # Translators: 첫 실행 안내 다이얼로그의 제목.
        prompt_title = _("창 전환 알림 — 첫 사용 안내")
        try:
            dlg = wx.MessageDialog(
                gui.mainFrame,
                prompt_body,
                prompt_title,
                style=wx.YES_NO | wx.ICON_QUESTION,
            )
        except Exception:
            # MessageDialog 리소스 생성 실패 — 플래그 안 쓰고 재시도 여지 남김.
            log.exception("mtwn: tutorial prompt MessageDialog create failed")
            return
        # 생성 성공 후 플래그 고정. 이후 경로 어디서 예외가 터지든 반복 안내 차단.
        try:
            mark_tutorial_shown()
        except Exception:
            log.exception("mtwn: tutorial prompt mark_tutorial_shown failed")
        try:
            result = dlg.ShowModal()
        finally:
            dlg.Destroy()
    except Exception:
        log.exception("mtwn: tutorial prompt dialog failed")
        return
    finally:
        try:
            gui.mainFrame.postPopup()
        except Exception:
            log.exception("mtwn: tutorial prompt postPopup failed")

    if result == wx.ID_YES:
        # open_tutorial은 prePopup/postPopup을 자체로 래핑하므로 중첩 안전.
        # MessageDialog Destroy 직후 이벤트 루프에 한 틱 양보하려 CallAfter 사용.
        from . import open_tutorial
        wx.CallAfter(open_tutorial, gui.mainFrame, "first_run")
