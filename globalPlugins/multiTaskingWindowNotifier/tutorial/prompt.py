# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""첫 실행 지연 안내 + 확인 다이얼로그.

NVDA 부팅 시점에 `GlobalPlugin.__init__`이 호출되면 본 모듈의
`maybe_show_first_run_prompt(plugin)`가 비동기로 예약된다.

설계:
    - tutorialShown 플래그가 True면 즉시 return.
    - core.callLater(3000ms)로 지연 — NVDA welcome dialog, startup 음성, OS
      알림 등이 몰리는 부팅 초기 3초를 피한다.
    - wx.MessageDialog(YES_NO | CANCEL) 1회. YES → open_tutorial. 나머지 →
      마감 플래그만 저장.
    - 어떤 경로로 종료되든 mark_tutorial_shown 호출해 반복 안내를 방지.

CLAUDE.md 불변 원칙 6: UI 안내 선제 추가 금지 — 본 모듈은 "첫 실행 1회의
사용자 선택권 제공"이라는 명시 목적이 있어 예외. mark_tutorial_shown으로
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


# 부팅 startup 음성/welcome dialog와 겹치지 않게 지연. 3000ms는 일반 환경
# 기준 충분한 여유 — welcome 설정이 켜진 사용자도 대부분 이 시점에 welcome
# dialog를 조작 중이라 확인 다이얼로그가 큐에 들어가면 welcome 종료 후 즉시
# 노출된다. 더 길게(5~8초) 늘리면 발견성이 떨어짐.
_DELAY_MS = 3000


def maybe_show_first_run_prompt(plugin) -> None:
    """첫 실행 사용자에게 튜토리얼 시청 여부를 물어본다.

    이미 노출됐으면(tutorialShown=True) 조용히 no-op. 아직이면
    core.callLater로 3초 뒤 확인 다이얼로그를 예약.

    Args:
        plugin: GlobalPlugin 인스턴스. 예외 경로에서 log.exception을 위한
            식별용으로만 받음 — 실제로는 참조하지 않아 None도 허용.
    """
    if is_tutorial_shown():
        return

    try:
        # core.callLater는 wx.App이 존재할 때만 안전(CLAUDE.md "재방어 금지"
        # 원칙). GlobalPlugin 시점엔 wx.App이 반드시 있어 별도 폴백 불필요.
        import core
        core.callLater(_DELAY_MS, _show_prompt)
    except Exception:
        # 스케줄 실패도 본체 이벤트 훅을 막지 않도록 흡수.
        log.exception("mtwn: tutorial prompt scheduling failed")


def _show_prompt() -> None:
    """지연 후 실제로 확인 다이얼로그를 띄운다.

    mark_tutorial_shown을 먼저 호출 — 사용자가 다이얼로그를 X로 닫거나
    모종의 이유로 _on_finish가 호출되지 않는 경로에서도 "다시는 묻지 않음"을
    보장. YES 선택 시 open_tutorial이 다시 mark를 호출해도 idempotent.
    """
    # 최종 체크: 지연 사이에 사용자가 설정 패널에서 "튜토리얼 보기"로 먼저
    # 열어 완료했을 수도 있음. 그 경우 여기서 조용히 종료.
    if is_tutorial_shown():
        return

    # 먼저 마감 — 이후 경로 어디서 예외가 터지든 반복 안내는 차단.
    try:
        mark_tutorial_shown()
    except Exception:
        log.exception("mtwn: tutorial prompt mark_tutorial_shown failed")

    try:
        gui.mainFrame.prePopup()
        # Translators: 첫 실행 시 튜토리얼 시청 여부를 묻는 확인 다이얼로그의 본문.
        prompt_body = _(
            "창 전환 알림 애드온에 처음 오셨네요.\n"
            "핵심 사용법을 안내하는 튜토리얼을 지금 보시겠어요?\n"
            "아니오를 선택해도 NVDA 설정 > 창 전환 알림 패널에서 언제든 다시 볼 수 있어요."
        )
        # Translators: 첫 실행 안내 다이얼로그의 제목.
        prompt_title = _("창 전환 알림 — 첫 사용 안내")
        # wx.YES_NO + X/Escape 모두 mark_tutorial_shown을 위에서 이미 처리했으므로
        # 반환값 분기는 YES(튜토리얼 열기) vs 나머지(조용히 종료) 둘로 충분.
        # 일부 플랫폼에서 X 버튼이 비활성화될 수 있지만 기능에는 영향 없음.
        dlg = wx.MessageDialog(
            gui.mainFrame,
            prompt_body,
            prompt_title,
            style=wx.YES_NO | wx.ICON_QUESTION,
        )
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
        # 바로 호출해도 되지만 MessageDialog Destroy 직후 이벤트 루프에 한
        # 틱 양보하기 위해 CallAfter로 예약.
        from . import open_tutorial
        wx.CallAfter(open_tutorial, gui.mainFrame, "first_run")
