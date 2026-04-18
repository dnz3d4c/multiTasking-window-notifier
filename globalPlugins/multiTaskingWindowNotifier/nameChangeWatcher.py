# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""event_nameChange 기반 탭 확정 전환 감지.

Ctrl+Tab / Ctrl+Shift+Tab 등으로 탭이 확정 전환되면 대부분 앱에서 최상위
창의 title bar가 바뀐다. Firefox / Notepad++가 여기에 해당. 메모장처럼
"제목 없음" 여러 탭을 동시에 쓰면 title이 안 바뀌어 이 훅으로는 구분 불가
— 그 케이스는 focusDispatcher의 editor 분기가 자식 hwnd로 구분.

자식 요소(웹 DOM, 동적 레이블 등)의 name 변경은 `obj.name != fg.name`
비교로 걸러진다. NVDA는 같은 창의 자식 객체에도 nameChange를 쏘지만
fg.name과는 보통 다른 값을 갖기 때문.
"""

from __future__ import annotations

import api
from logHandler import log

from . import settings
from .appIdentity import getAppId, normalize_title


def handle(plugin, obj) -> None:
    """obj.name이 foreground title과 일치할 때만 matcher로 위임."""
    if obj is None:
        return
    fg = api.getForegroundObject()
    if fg is None:
        return
    fg_name = (getattr(fg, "name", "") or "").strip()
    obj_name = (getattr(obj, "name", "") or "").strip()
    debug = settings.get("debugLogging")
    if not obj_name or obj_name != fg_name:
        if debug:
            log.info(
                f"mtwn: DBG nameChange skip obj_name={obj_name!r} "
                f"fg_name={fg_name!r}"
            )
        return
    appId = getAppId(obj)
    title = normalize_title(obj_name)
    if not title:
        if debug:
            log.info(
                f"mtwn: DBG nameChange skip-normalize obj_name={obj_name!r}"
            )
        return
    try:
        tab_sig = int(getattr(obj, "windowHandle", 0) or 0)
    except Exception:
        tab_sig = 0
    if debug:
        log.info(
            f"mtwn: DBG nameChange appId={appId!r} title={title!r} "
            f"tab_sig={tab_sig}"
        )
    plugin._match_and_beep(appId, title, tab_sig=tab_sig)
