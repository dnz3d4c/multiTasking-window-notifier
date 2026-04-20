# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""event_nameChange 기반 탭 확정 전환 감지.

**이벤트 책임 분리** (3-way):
    - 이 모듈(nameChangeWatcher) — "foreground 본체 title 변경" 전담.
      foreground hwnd는 그대로인데 title bar만 갈리는 Ctrl+Tab 케이스 (Firefox,
      Notepad++ 등).
    - foregroundWatcher — "앱 간 전환" 전담. SCOPE_APP 매칭의 표준 진입로.
    - focusDispatcher — "같은 앱 내 탭/자식 컨트롤 전환" 전담 (3분기).

Ctrl+Tab / Ctrl+Shift+Tab 등으로 탭이 확정 전환되면 대부분 앱에서 최상위
창의 title bar가 바뀐다. Firefox / Notepad++가 여기에 해당. 메모장처럼
"제목 없음" 여러 탭을 동시에 쓰면 title이 안 바뀌어 이 훅으로는 구분 불가
— 그 케이스는 focusDispatcher의 editor 분기가 자식 hwnd로 구분.

**조기 컷**: NVDA의 `event_nameChange`는 글로벌 훅이라 메뉴 항목/DOM 자식/
링크 등 임의 accessible 객체의 name 변경 이벤트까지 전달된다. handle 진입
직후 `obj.windowHandle != fg.windowHandle` 정수 비교로 "foreground 창 본체의
name 변경"만 통과시켜, 이하 로직(문자열 비교/normalize/로그)이 아예 실행되지
않게 한다.

`__eq__` 대신 windowHandle을 직접 비교하는 이유: NVDAObject.__eq__는 보통
Window._isEqual로 위임돼 결국 windowHandle을 비교하지만, 첫 단계에서
`type(self) is not type(other)` 체크를 하므로 같은 hwnd에 대해 서로 다른
wrapper 클래스(UIA/IA2 등)가 붙은 경우 False가 반환될 위험이 있다. 정수
비교는 wrapper 타입 차이를 건너뛰고 의도(최상위 창 본체 변경)를 직접 표현.
"""

from __future__ import annotations

import api
from logHandler import log

from . import settings
from .appIdentity import getAppId, normalize_title


def handle(plugin, obj) -> None:
    """foreground 창 본체의 name 변경일 때만 matcher로 위임."""
    if obj is None:
        # NVDA 부팅/전환 과도기에 일시적 None. 정상 경로이므로 로그 없이 탈출.
        return
    fg = api.getForegroundObject()
    if fg is None:
        # foreground 미확정 초기 단계. 정상.
        return
    # 조기 컷: obj의 windowHandle이 foreground 창과 같아야 "창 본체 name 변경"
    # 으로 간주. 메뉴 항목/DOM 자식/링크 등은 hwnd가 달라 즉시 걸러지고 문자열
    # 비교/로그까지 가지 않는다. hwnd를 못 읽으면 0이 되어 거의 항상 다름.
    try:
        obj_hwnd = int(getattr(obj, "windowHandle", 0) or 0)
        fg_hwnd = int(getattr(fg, "windowHandle", 0) or 0)
    except Exception:
        # windowHandle이 non-int이거나 접근 중 예외. 이론상 거의 발생 안 하나
        # 재현 시 추적용 디버그 로그. ui.message는 내지 않음 — 정상 이벤트 중
        # 일부만 실패하는 조용한 케이스라 사용자 알림은 소음.
        log.debug("mtwn: nameChange hwnd coerce failed", exc_info=True)
        return
    if obj_hwnd == 0 or obj_hwnd != fg_hwnd:
        return
    fg_name = (getattr(fg, "name", "") or "").strip()
    debug = settings.get("debugLogging")
    if not fg_name:
        if debug:
            log.info("mtwn: DBG nameChange skip-empty-name")
        return
    appId = getAppId(obj)
    title = normalize_title(fg_name)
    if not title:
        if debug:
            log.info(
                f"mtwn: DBG nameChange skip-normalize fg_name={fg_name!r}"
            )
        return
    tab_sig = obj_hwnd  # 조기 컷에서 이미 추출
    if debug:
        log.info(
            f"mtwn: DBG nameChange appId={appId!r} title={title!r} "
            f"tab_sig={tab_sig}"
        )
    plugin._match_and_beep(appId, title, tab_sig=tab_sig)
