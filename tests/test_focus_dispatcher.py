# -*- coding: utf-8 -*-
"""focusDispatcher.dispatch 3분기 라우팅 단위 테스트.

dispatch는 event_gainFocus의 분기 판정 전용. 실제 매칭/비프는
plugin._match_and_beep로 위임되므로, 여기서는 "어떤 title/tab_sig로
위임이 호출되는가"만 검증한다.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

from globalPlugins.multiTaskingWindowNotifier import focusDispatcher
from globalPlugins.multiTaskingWindowNotifier.constants import ALT_TAB_OVERLAY_WCN


def _make_obj(wcn="", name="", hwnd=0x1000, appName=""):
    """NVDAObject 스텁. windowHandle/appModule.appName까지 포함."""
    obj = MagicMock()
    obj.windowClassName = wcn
    obj.name = name
    obj.windowHandle = hwnd
    obj.appModule = MagicMock()
    obj.appModule.appName = appName
    return obj


@pytest.fixture
def captured_match(monkeypatch):
    """plugin._match_and_beep 호출 인자를 캡처하는 fake plugin + (appId, title, tab_sig) 리스트."""
    calls = []
    plugin = MagicMock()
    plugin._match_and_beep = lambda appId, title, tab_sig=0: calls.append(
        (appId, title, tab_sig)
    )
    return plugin, calls


@pytest.fixture
def mock_api(monkeypatch):
    """api.getForegroundObject 반환을 테스트별 fg 객체로 교체 가능한 헬퍼."""
    state = {"fg": None}

    def _set_fg(fg):
        state["fg"] = fg

    monkeypatch.setattr(focusDispatcher.api, "getForegroundObject", lambda: state["fg"])
    return _set_fg


@pytest.fixture
def tab_classes_noop(monkeypatch):
    """기본은 overlay/editor 둘 다 False. 테스트가 필요할 때만 override."""
    monkeypatch.setattr(focusDispatcher.tabClasses, "is_overlay_class", lambda appId, wcn: False)
    monkeypatch.setattr(focusDispatcher.tabClasses, "is_editor_class", lambda appId, wcn: False)


@pytest.fixture
def debug_off(monkeypatch):
    """settings.get('debugLogging') → False 고정. 진단 로그 경로가 테스트에 노이즈 안 주도록."""
    monkeypatch.setattr(focusDispatcher.settings, "get", lambda key: False)


def test_dispatch_none_obj_is_noop(captured_match, mock_api, tab_classes_noop, debug_off):
    """obj=None이면 매칭 위임 없이 즉시 return."""
    plugin, calls = captured_match
    mock_api(None)

    focusDispatcher.dispatch(plugin, None)

    assert calls == []


def test_alt_tab_overlay_uses_obj_name(captured_match, mock_api, tab_classes_noop, debug_off):
    """wcn==ALT_TAB_OVERLAY_WCN이면 obj.name을 raw title로 사용."""
    plugin, calls = captured_match
    obj = _make_obj(wcn=ALT_TAB_OVERLAY_WCN, name="YouTube - Chrome", hwnd=0xAAA, appName="chrome")
    fg = _make_obj(wcn="Chrome_WidgetWin_1", name="Chrome", hwnd=0xBBB, appName="chrome")
    mock_api(fg)

    focusDispatcher.dispatch(plugin, obj)

    # normalize_title은 꼬리 " - Chrome"을 제거 (appId=chrome).
    assert len(calls) == 1
    appId, title, tab_sig = calls[0]
    assert appId == "chrome"
    assert title == "YouTube"
    assert tab_sig == 0xAAA  # alt_tab 분기는 obj.windowHandle


def test_app_overlay_uses_obj_name(captured_match, mock_api, monkeypatch, debug_off):
    """앱별 overlay (Notepad++ MRU 등): fg_wcn이 overlay 목록이면 obj.name 사용."""
    plugin, calls = captured_match
    obj = _make_obj(wcn="SysListView32", name="main.cpp", hwnd=0xC001, appName="notepad++")
    fg = _make_obj(wcn="#32770", name="MRU", hwnd=0xC000, appName="notepad++")
    mock_api(fg)

    monkeypatch.setattr(
        focusDispatcher.tabClasses,
        "is_overlay_class",
        lambda appId, wcn: appId == "notepad++" and wcn == "#32770",
    )
    monkeypatch.setattr(focusDispatcher.tabClasses, "is_editor_class", lambda a, w: False)

    focusDispatcher.dispatch(plugin, obj)

    assert len(calls) == 1
    appId, title, tab_sig = calls[0]
    assert appId == "notepad++"
    assert title == "main.cpp"
    assert tab_sig == 0xC001  # overlay도 obj.windowHandle


def test_editor_branch_uses_fg_name(captured_match, mock_api, monkeypatch, debug_off):
    """editor 자식 컨트롤 분기: fg.name을 raw title로 쓰고 tab_sig는 obj(자식) hwnd.

    같은 최상위 창이 여러 "제목 없음" 탭을 가질 때 자식 hwnd로 탭 구분이 돼야 함 —
    매칭 회귀 방지의 핵심 불변.
    """
    plugin, calls = captured_match
    obj = _make_obj(wcn="RichEditD2DPT", name="", hwnd=0xE001, appName="notepad")
    fg = _make_obj(wcn="Notepad", name="제목 없음 - 메모장", hwnd=0xF001, appName="notepad")
    mock_api(fg)

    monkeypatch.setattr(focusDispatcher.tabClasses, "is_overlay_class", lambda a, w: False)
    monkeypatch.setattr(
        focusDispatcher.tabClasses,
        "is_editor_class",
        lambda appId, wcn: appId == "notepad" and wcn == "RichEditD2DPT",
    )

    focusDispatcher.dispatch(plugin, obj)

    assert len(calls) == 1
    appId, title, tab_sig = calls[0]
    assert appId == "notepad"
    assert title == "제목 없음"
    # editor 분기의 tab_sig는 obj(자식) hwnd. fg.windowHandle 쓰면 여러 탭 구분 불가.
    assert tab_sig == 0xE001


def test_editor_branch_skipped_when_child_wcn_equals_fg_wcn(
    captured_match, mock_api, monkeypatch, debug_off
):
    """Firefox 같이 자식 wcn과 최상위 wcn이 같은 앱은 editor 분기 자동 차단.

    `wcn != fg_wcn` 게이트가 이 폭발 방지용 — 없으면 모든 focus 전환이
    editor 분기로 빠져 과도 매칭.
    """
    plugin, calls = captured_match
    obj = _make_obj(wcn="MozillaWindowClass", name="x", hwnd=0xF100, appName="firefox")
    fg = _make_obj(wcn="MozillaWindowClass", name="Some Page - Firefox", hwnd=0xF100, appName="firefox")
    mock_api(fg)

    monkeypatch.setattr(focusDispatcher.tabClasses, "is_overlay_class", lambda a, w: False)
    # is_editor_class가 True를 돌려줘도 wcn==fg_wcn이면 분기 진입 불가.
    monkeypatch.setattr(focusDispatcher.tabClasses, "is_editor_class", lambda a, w: True)

    focusDispatcher.dispatch(plugin, obj)

    assert calls == []


def test_no_branch_matches_is_silent(captured_match, mock_api, tab_classes_noop, debug_off):
    """3분기 모두 미해당이면 매칭 위임 없이 조용히 return."""
    plugin, calls = captured_match
    obj = _make_obj(wcn="Button", name="Some Button", hwnd=0xB001, appName="explorer")
    fg = _make_obj(wcn="CabinetWClass", name="탐색기", hwnd=0xB000, appName="explorer")
    mock_api(fg)

    focusDispatcher.dispatch(plugin, obj)

    assert calls == []


def test_empty_raw_title_is_skipped(captured_match, mock_api, monkeypatch, debug_off):
    """raw title이 공백/빈 문자열이면 매칭 위임 없음."""
    plugin, calls = captured_match
    obj = _make_obj(wcn=ALT_TAB_OVERLAY_WCN, name="   ", hwnd=0xA001, appName="chrome")
    fg = _make_obj(wcn="Chrome_WidgetWin_1", name="Chrome", hwnd=0xA000, appName="chrome")
    mock_api(fg)

    focusDispatcher.dispatch(plugin, obj)

    assert calls == []


def test_whitespace_only_name_is_skipped(captured_match, mock_api, monkeypatch, debug_off):
    """raw title이 공백만이면 strip 후 빈 문자열 → 매칭 위임 전 skip."""
    plugin, calls = captured_match
    obj = _make_obj(wcn=ALT_TAB_OVERLAY_WCN, name="\t  \n", hwnd=0xA001, appName="chrome")
    fg = _make_obj(wcn="Chrome_WidgetWin_1", name="Chrome", hwnd=0xA000, appName="chrome")
    mock_api(fg)

    focusDispatcher.dispatch(plugin, obj)

    assert calls == []
