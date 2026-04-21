# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""이벤트 훅 라우터 — 3-way 책임 분리 구현.

NVDA가 쏘는 3개 훅을 각각 다른 상황으로 처리한다. __init__.py의 훅 메서드는
try/except/finally + nextHandler() 체인만 유지하고 본문은 여기로 위임.

책임 분리 매트릭스:

| NVDA 이벤트       | 엔트리              | 담당 범위 |
|---                |---                  |---        |
| event_foreground  | handle_foreground   | 앱 간 전환(foreground hwnd 변경). SCOPE_APP 매칭 표준 진입로. |
| event_nameChange  | handle_name_change  | foreground 본체 title 변경(Ctrl+Tab 등). hwnd 동일, title bar만 갈림. |
| event_gainFocus   | dispatch_focus      | 같은 앱 내 탭/자식 컨트롤 전환 3분기(Alt+Tab 오버레이 / 앱별 overlay / editor 자식 hwnd). |

세 진입점 모두 stateless. dedup 상태는 matcher(Matcher.last_event_sig)가 소유.

공통 관례: raw → normalize_title → empty 처리.
- handle_foreground는 empty title **통과** (appId만으로 SCOPE_APP fallback 매칭 유도)
- handle_name_change / dispatch_focus는 empty 컷

프라이빗 헬퍼(`_log_focus_diag`, `_determine_match_source`)는 dispatch_focus 전용
— Alt+Tab/오버레이/editor 3분기 상수·필드에 종속이라 다른 훅과 공유 금지.
"""

from __future__ import annotations

import api
from logHandler import log

from . import settings
from . import tabClasses
from .appIdentity import getAppId, normalize_title
from .constants import ALT_TAB_HOST_FG_WCN, ALT_TAB_OVERLAY_WCN


# ================================================================
# 1. event_foreground — 앱 간 전환
# ================================================================


def handle_foreground(plugin, obj) -> None:
    """foreground 전환 시 appId/title 추출 후 matcher 위임.

    NVDA는 최상위 foreground 윈도우가 바뀐 순간 1회 발화. 내부적으로
    `api.setForegroundObject(obj)` 직후 같은 obj를 넘기므로 훅 안에서는
    `api.getForegroundObject() == obj` 보장(굳이 비교할 필요 없음).

    title="" 허용 이유: obj가 막 띄워진 직후 등 일시적으로 name이 비어있을 수
    있다. 이때도 appId만 있으면 matcher가 app_lookup 조회로 SCOPE_APP fallback에
    자연스럽게 진입해 앱 단음 비프를 울려준다. 빈 title을 early-return으로
    차단하면 SCOPE_APP 알림을 잃는다. appId도 비면(거의 발생 안 함) 매칭할
    키 자체가 없으므로 컷.

    예외는 호출 측(__init__.py의 event_foreground)에서 try/except로 흡수한다.
    이 함수 내부에 복구 경로는 두지 않는다.
    """
    if obj is None:
        return
    appId = getAppId(obj)
    if not appId:
        return
    raw_title = (getattr(obj, "name", "") or "").strip()
    title = normalize_title(raw_title)
    # tab_sig: foreground 창의 hwnd. 같은 (appId, title) 조합이라도 다른 hwnd면
    # 다른 시그니처로 처리되어 matcher의 dedup 가드와 자연스럽게 맞물린다.
    try:
        tab_sig = int(getattr(obj, "windowHandle", 0) or 0)
    except Exception:
        tab_sig = 0
    if settings.get("debugLogging"):
        log.info(
            f"mtwn: DBG fg appId={appId!r} title={title!r} tab_sig={tab_sig}"
        )
    plugin._match_and_beep(appId, title, tab_sig=tab_sig)


# ================================================================
# 2. event_nameChange — foreground 본체 title 변경 (Ctrl+Tab 등)
# ================================================================


def handle_name_change(plugin, obj) -> None:
    """foreground 창 본체의 name 변경일 때만 matcher 위임.

    Ctrl+Tab 등으로 탭이 확정 전환되면 대부분 앱에서 최상위 창의 title bar가
    바뀐다(Firefox/Notepad++ 등). 메모장처럼 "제목 없음" 여러 탭을 동시에 쓰면
    title이 안 바뀌어 이 훅으로는 구분 불가 — 그 케이스는 dispatch_focus의
    editor 분기가 자식 hwnd로 구분.

    조기 컷: NVDA의 event_nameChange는 글로벌 훅이라 메뉴 항목/DOM 자식/링크
    등 임의 accessible 객체의 name 변경까지 전달된다. `obj.windowHandle !=
    fg.windowHandle` 정수 비교로 "foreground 창 본체 변경"만 통과시켜 이하
    로직(문자열 비교/normalize/로그)이 아예 실행되지 않게 한다.

    `__eq__` 대신 windowHandle 직접 비교 이유: NVDAObject.__eq__는 보통
    Window._isEqual로 위임돼 결국 windowHandle을 비교하지만 첫 단계
    `type(self) is not type(other)` 체크가 있어 같은 hwnd에 wrapper 클래스
    (UIA/IA2 등)가 다르면 False가 될 위험. 정수 비교는 wrapper 차이를
    건너뛰고 의도(최상위 창 본체 변경)를 직접 표현.
    """
    if obj is None:
        return
    fg = api.getForegroundObject()
    if fg is None:
        return
    try:
        obj_hwnd = int(getattr(obj, "windowHandle", 0) or 0)
        fg_hwnd = int(getattr(fg, "windowHandle", 0) or 0)
    except Exception:
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
    tab_sig = obj_hwnd
    if debug:
        log.info(
            f"mtwn: DBG nameChange appId={appId!r} title={title!r} "
            f"tab_sig={tab_sig}"
        )
    plugin._match_and_beep(appId, title, tab_sig=tab_sig)


# ================================================================
# 3. event_gainFocus — 같은 앱 내 탭/자식 컨트롤 3분기
# ================================================================


def dispatch_focus(plugin, obj) -> None:
    """obj가 3분기 중 하나에 해당하면 raw_title/tab_sig/appId 뽑아 matcher로 위임.

    3분기:
        1) Alt+Tab 오버레이 — obj.wcn == ALT_TAB_OVERLAY_WCN AND fg.wcn ==
           ALT_TAB_HOST_FG_WCN. obj.wcn(InputSite)은 UWP 공용이라 단독으로는
           Win+B 숨김 아이콘·트레이·알림 센터까지 걸린다. Xaml Shell 호스트
           fgWcn과 AND로 묶어 진짜 Alt+Tab/Win+Tab만 진입. 후보의 obj.appId는
           오버레이 호스트(항상 'explorer')라 무의미 → match_appId=""로 내려
           matcher의 app_lookup 조회를 스킵(title 정확 매치 + title-only 역
           매핑까지만 허용).
        2) 앱별 오버레이 (예: Notepad++ MRU) — fgWcn이 appId의 overlay 목록에
           있음. obj가 리스트 항목.
        3) 에디터 자식 컨트롤 — `is_editor_class(appId, wcn) AND wcn != fg_wcn`.
           메모장 "제목 없음" 여러 탭처럼 title이 안 바뀌어 nameChange로 구분
           불가한 앱 전용. `wcn != fg_wcn` 게이트가 자식==최상위 wcn인 앱
           (Firefox 계열)의 과도 매칭을 자동 차단.
    """
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
    """debugLogging=True 진단 로그. dispatch_focus 전용.

    Ctrl+Tab 등에서 비프가 안 나는 원인을 실측으로 특정하기 위한 기록.
    wcn/name/role/parentWcn/fgWcn/fgName/appId 7필드로 3분기 판정 실측용.
    본 로직 침범 방지를 위해 전용 try/except로 격리.
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

    match_appId는 matcher에 넘길 **신뢰 가능한** appId. Alt+Tab 분기에서는
    obj.appId가 오버레이 호스트(='explorer')라 무의미하므로 빈 문자열로 내려
    app_lookup 조회를 스킵시킨다. 나머지 분기는 원래 appId 그대로.
    """
    # Alt+Tab: obj.wcn(InputSite)은 UWP 공용이라 fg.wcn(Xaml Shell 호스트)과 AND로
    # 묶어야 Win+B/트레이/알림센터 등 같은 껍데기를 쓰는 목록형 UI를 배제.
    in_alt_tab = (wcn == ALT_TAB_OVERLAY_WCN and fg_wcn == ALT_TAB_HOST_FG_WCN)
    in_app_overlay = tabClasses.is_overlay_class(appId, fg_wcn)
    in_tab_editor = (tabClasses.is_editor_class(appId, wcn) and wcn != fg_wcn)

    if not (in_alt_tab or in_app_overlay or in_tab_editor):
        return None

    # 매칭 소스: alt_tab/overlay는 obj.name(후보·리스트 항목), editor는 fg.name(활성
    # 탭 제목 포함 title bar).
    if in_tab_editor:
        src = fg or obj
    else:
        src = obj

    raw_title = (getattr(src, "name", "") or "").strip()
    if not raw_title:
        return None

    # tab_sig: editor 분기는 **항상 obj(자식)**의 hwnd. fg.windowHandle 쓰면
    # 메모장 "제목 없음" 여러 탭이 같은 최상위 hwnd를 공유해 구분 불가.
    # 나머지 분기는 title 소스와 같은 obj의 hwnd.
    sig_obj = obj if in_tab_editor else src
    try:
        tab_sig = int(getattr(sig_obj, "windowHandle", 0) or 0)
    except Exception:
        tab_sig = 0

    match_appId = "" if in_alt_tab else appId
    return raw_title, tab_sig, match_appId
