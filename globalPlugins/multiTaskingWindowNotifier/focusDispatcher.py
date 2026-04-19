# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""event_gainFocus 3분기 판정 + 진단 로그.

**이벤트 책임 분리** (3-way):
    - 이 모듈(focusDispatcher) — "같은 앱 내 탭/자식 컨트롤 전환" 전담.
      foreground hwnd가 안 바뀌는 케이스(Alt+Tab 후보 미리듣기 / 앱별 MRU /
      에디터 자식 hwnd 구분)만 처리.
    - foregroundWatcher — "앱 간 전환" 전담. SCOPE_APP 매칭의 표준 진입로.
    - nameChangeWatcher — "foreground 본체 title 변경" 전담 (Ctrl+Tab으로
      title bar만 갈리는 Firefox/Notepad++ 등).

대부분의 Ctrl+Tab 확정 전환은 event_nameChange가 foreground title 변경으로
감지한다. 이 디스패처는 nameChange가 못 잡거나 의미가 없는 3가지 경로를 다룬다:

    1) Alt+Tab 오버레이 — obj.wcn이 `ALT_TAB_OVERLAY_WCN` AND fg.wcn이
       `ALT_TAB_HOST_FG_WCN`. obj.wcn(InputSite)은 UWP 공용이라 단독으로는
       Win+B 숨김 아이콘·시스템 트레이·알림 센터까지 같이 걸린다. Xaml Shell
       호스트 fgWcn과 AND로 묶어 진짜 Alt+Tab/Win+Tab 오버레이만 진입.
       obj 자신이 "선택 후보 창"의 name을 들고 있음. 단, 후보의 obj.appId는
       오버레이 호스트(항상 'explorer') 값이라 실제 앱이 아니다 — 아래 매칭용
       match_appId를 빈 문자열로 내려 Matcher가 app_lookup 조회를 스킵하게
       한다 (title 정확 매치 + title-only 역매핑까지만 허용).
    2) 앱별 오버레이 (예: Notepad++ MRU) — fgWcn이 appId의 overlay 목록에 있음.
       obj가 리스트 항목.
    3) 에디터 자식 컨트롤 — `is_editor_class(appId, wcn) AND wcn != fg_wcn`.
       메모장 "제목 없음" 여러 탭처럼 title이 안 바뀌어 nameChange로 구분
       불가한 앱 전용. `wcn != fg_wcn` 게이트가 자식==최상위 wcn인 앱
       (Firefox 계열)의 과도 매칭을 자동 차단한다.

GlobalPlugin.event_gainFocus는 이 모듈의 `dispatch(plugin, obj)` 한 줄 호출로
비워진다. try/except/finally + nextHandler 보장은 이벤트 훅 진입점(__init__.py)
레이어 책임으로 유지.
"""

from __future__ import annotations

import api
from logHandler import log

from . import settings
from . import tabClasses
from .appIdentity import getAppId, normalize_title
from .constants import ALT_TAB_HOST_FG_WCN, ALT_TAB_OVERLAY_WCN


def dispatch(plugin, obj) -> None:
    """obj가 3분기 중 하나에 해당하면 raw_title/tab_sig/appId 뽑아 matcher로 위임."""
    if settings.get("debugLogging"):
        _log_focus_diag(obj)

    if obj is None:
        return

    wcn = getattr(obj, "windowClassName", "")
    appId = getAppId(obj)
    fg = api.getForegroundObject()
    fg_wcn = getattr(fg, "windowClassName", "") if fg is not None else ""

    match_source = _determine_match_source(obj, wcn, appId, fg, fg_wcn)
    if match_source is None:
        return
    raw_title, tab_sig, match_appId = match_source
    title = normalize_title(raw_title)
    if not title:
        return
    plugin._match_and_beep(match_appId, title, tab_sig=tab_sig)


def _log_focus_diag(obj) -> None:
    """debugLogging=True 진단 로그. 본 로직 침범 방지를 위해 전용 try/except로 격리.

    Ctrl+Tab 등에서 비프가 안 나는 원인을 실측으로 특정하기 위한 기록.
    NVDA 로그에 한 줄/이벤트로 남는다. settings.get("debugLogging")이 True일
    때만 dispatch가 호출하므로 off 상태에선 함수 호출 자체 없음.
    """
    try:
        wcn = getattr(obj, "windowClassName", "") if obj is not None else ""
        obj_name = (getattr(obj, "name", "") or "") if obj is not None else ""
        role = getattr(obj, "role", "") if obj is not None else ""
        parent = getattr(obj, "parent", None) if obj is not None else None
        parent_wcn = getattr(parent, "windowClassName", "") if parent is not None else ""
        fg = api.getForegroundObject()
        fg_wcn = getattr(fg, "windowClassName", "") if fg is not None else ""
        fg_name = (getattr(fg, "name", "") or "") if fg is not None else ""
        try:
            obj_app = getAppId(obj) if obj is not None else ""
        except Exception:
            obj_app = "<err>"
        log.info(
            f"mtwn: DBG gF wcn={wcn!r} name={obj_name!r} role={role!r} "
            f"parentWcn={parent_wcn!r} fgWcn={fg_wcn!r} fgName={fg_name!r} "
            f"appId={obj_app!r}"
        )
    except Exception:
        log.exception("mtwn: debug log failed")


def _determine_match_source(obj, wcn, appId, fg, fg_wcn):
    """3분기 판정. 매칭 대상이면 (raw_title, tab_sig, match_appId), 아니면 None.

    match_appId는 Matcher에 넘길 **신뢰 가능한** appId. Alt+Tab 분기에서는
    obj.appId가 오버레이 호스트(='explorer')라 무의미하므로 빈 문자열로 내려
    app_lookup 조회를 스킵시킨다. 나머지 분기는 원래 appId 그대로.
    """
    # Alt+Tab: obj.wcn(InputSite)은 UWP 공용이라 fg.wcn(Xaml Shell 호스트)과
    # AND로 묶어야 Win+B/트레이/알림센터 등 "같은 껍데기를 쓰는 목록형 UI"를 배제.
    in_alt_tab     = (wcn == ALT_TAB_OVERLAY_WCN
                      and fg_wcn == ALT_TAB_HOST_FG_WCN)
    in_app_overlay = tabClasses.is_overlay_class(appId, fg_wcn)
    in_tab_editor  = (tabClasses.is_editor_class(appId, wcn)
                      and wcn != fg_wcn)

    if not (in_alt_tab or in_app_overlay or in_tab_editor):
        return None

    # 매칭 소스: alt_tab/overlay는 obj.name(후보·리스트 항목 자체),
    # editor는 fg.name(= 활성 탭 제목 포함한 창 title bar).
    if in_tab_editor:
        src = fg or obj
    else:
        src = obj

    raw_title = (getattr(src, "name", "") or "").strip()
    if not raw_title:
        return None

    # tab_sig: editor 분기는 **항상 obj(자식)**의 hwnd. fg.windowHandle로 쓰면
    # 메모장 같은 "제목 없음" 여러 탭이 같은 최상위 hwnd를 공유해 구분 불가.
    # 나머지 분기는 title 소스와 같은 obj의 hwnd.
    sig_obj = obj if in_tab_editor else src
    try:
        tab_sig = int(getattr(sig_obj, "windowHandle", 0) or 0)
    except Exception:
        tab_sig = 0

    # Alt+Tab 분기: obj.appId='explorer'는 오버레이 호스트. 후보의 실제 앱이
    # 아니므로 빈 문자열로 넘겨 Matcher가 app_lookup을 스킵하게 한다.
    # (title 정확 매치 + title-only 역매핑까지만 허용)
    match_appId = "" if in_alt_tab else appId
    return raw_title, tab_sig, match_appId
