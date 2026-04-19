# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""event_foreground 기반 앱 간 전환 감지.

NVDA는 최상위 foreground 윈도우가 실제로 바뀐 순간 `event_foreground`를 1회
발화한다. 내부적으로 `api.setForegroundObject(obj)` 호출 직후 같은 obj를
인자로 전달하므로, 이 훅 안에서는 `api.getForegroundObject() == obj`가 보장
된다(굳이 비교할 필요 없음).

**책임 분리** (3-way):
    - 이 모듈(foregroundWatcher) — "앱 간 전환" 전담. SCOPE_APP 매칭의 표준
      진입로. 같은 앱 내부의 메뉴/버튼 클릭처럼 foreground가 바뀌지 않는
      포커스 이동에는 NVDA가 발화하지 않으므로, focusDispatcher의 폭주성
      재매칭을 자연스럽게 우회한다.
    - nameChangeWatcher — "foreground 창 본체의 title 변경" 전담. Ctrl+Tab
      탭 전환으로 title bar만 갈리는 경우.
    - focusDispatcher — "같은 앱 내 탭/자식 컨트롤 전환" 전담(3분기).

**title="" 허용 이유**:
    obj가 막 띄워진 직후 등 일시적으로 name이 비어있을 수 있다. 이때도
    appId만 있으면 matcher가 `app_lookup` 조회로 SCOPE_APP fallback에
    자연스럽게 진입해 앱 단음 비프를 울려준다. 굳이 여기서 빈 title을
    early-return으로 차단하면 SCOPE_APP 알림을 잃는다.

    단 appId와 title 둘 다 비면(거의 발생 안 함) 매칭할 게 없으므로 컷.

예외 처리:
    내부에서 throw된 예외는 호출 측(__init__.py의 event_foreground)에서
    try/except로 흡수한다. 이 모듈은 의미 있는 복구 경로가 없으니 그대로
    bubble up.
"""

from __future__ import annotations

from logHandler import log

from . import settings
from .appIdentity import getAppId, normalize_title


def handle(plugin, obj) -> None:
    """foreground 전환 시 appId/title을 추출해 matcher로 위임.

    Args:
        plugin: GlobalPlugin 인스턴스. _match_and_beep을 호출한다.
        obj: 새 foreground NVDAObject. NVDA가 setForegroundObject 직후
            전달하므로 api.getForegroundObject()와 동일.
    """
    if obj is None:
        return
    appId = getAppId(obj)
    # getAppId는 보통 'unknown' fallback을 두기 때문에 빈 문자열로 떨어지는
    # 일이 거의 없지만, 그래도 빈 값이면 매칭 키 자체가 없으므로 컷.
    # title만 비고 appId가 있으면 SCOPE_APP fallback(matcher의 app_lookup)
    # 으로 자연 진입하므로 그대로 통과시킨다.
    if not appId:
        return
    raw_title = (getattr(obj, "name", "") or "").strip()
    title = normalize_title(raw_title)
    # tab_sig: foreground 창의 hwnd. 같은 (appId, title) 조합이라도 다른
    # hwnd면 다른 시그니처로 처리되어 dedup 가드와 자연스럽게 맞물린다.
    try:
        tab_sig = int(getattr(obj, "windowHandle", 0) or 0)
    except Exception:
        tab_sig = 0
    if settings.get("debugLogging"):
        log.info(
            f"mtwn: DBG fg appId={appId!r} title={title!r} "
            f"tab_sig={tab_sig}"
        )
    plugin._match_and_beep(appId, title, tab_sig=tab_sig)
