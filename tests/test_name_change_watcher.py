# -*- coding: utf-8 -*-
"""nameChangeWatcher.handle 단위 테스트.

Ctrl+Tab 확정 전환 시 foreground title이 바뀌는 시나리오(Firefox, Notepad++)
에서만 매칭 위임이 발생해야 한다. 자식 요소의 nameChange(obj.name != fg.name)는
스킵되어야 한다.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from globalPlugins.multiTaskingWindowNotifier import nameChangeWatcher


def _make_obj(name="", hwnd=0x1000, appName=""):
    obj = MagicMock()
    obj.name = name
    obj.windowHandle = hwnd
    obj.appModule = MagicMock()
    obj.appModule.appName = appName
    return obj


@pytest.fixture
def captured_match():
    """plugin._match_and_beep 캡처."""
    calls = []
    plugin = MagicMock()
    plugin._match_and_beep = lambda appId, title, tab_sig=0: calls.append(
        (appId, title, tab_sig)
    )
    return plugin, calls


@pytest.fixture
def mock_api(monkeypatch):
    state = {"fg": None}

    def _set_fg(fg):
        state["fg"] = fg

    monkeypatch.setattr(nameChangeWatcher.api, "getForegroundObject", lambda: state["fg"])
    return _set_fg


@pytest.fixture
def debug_off(monkeypatch):
    monkeypatch.setattr(nameChangeWatcher.settings, "get", lambda key: False)


def test_none_obj_is_noop(captured_match, mock_api, debug_off):
    """obj=None이면 매칭 위임 없이 즉시 return."""
    plugin, calls = captured_match
    mock_api(_make_obj(name="anything"))

    nameChangeWatcher.handle(plugin, None)

    assert calls == []


def test_none_foreground_is_noop(captured_match, mock_api, debug_off):
    """foreground가 없으면 매칭 위임 없음. 드물지만 부팅 직후 등 방어."""
    plugin, calls = captured_match
    mock_api(None)

    nameChangeWatcher.handle(plugin, _make_obj(name="something"))

    assert calls == []


def test_obj_name_matches_fg_name_triggers_match(captured_match, mock_api, debug_off):
    """최상위 창 자체의 name 변경 (Ctrl+Tab 탭 확정 전환)은 매칭 위임."""
    plugin, calls = captured_match
    fg = _make_obj(name="main.cpp - Notepad++", hwnd=0xC100, appName="notepad++")
    mock_api(fg)

    nameChangeWatcher.handle(plugin, fg)

    assert len(calls) == 1
    appId, title, tab_sig = calls[0]
    assert appId == "notepad++"
    # normalize_title이 꼬리 " - Notepad++"를 제거하는지와 무관하게, 위임 자체가
    # 일어났고 tab_sig가 obj.windowHandle이면 OK.
    assert title  # 빈 문자열 아님
    assert tab_sig == 0xC100


def test_obj_name_differs_from_fg_name_is_skipped(captured_match, mock_api, debug_off):
    """웹 DOM / 동적 레이블 등 자식 객체의 nameChange는 fg.name과 불일치 → skip."""
    plugin, calls = captured_match
    fg = _make_obj(name="Firefox - example.com", hwnd=0xF100, appName="firefox")
    child = _make_obj(name="Some Link Label", hwnd=0xF200, appName="firefox")
    mock_api(fg)

    nameChangeWatcher.handle(plugin, child)

    assert calls == []


def test_empty_obj_name_is_skipped(captured_match, mock_api, debug_off):
    """obj.name이 비어있으면 skip."""
    plugin, calls = captured_match
    fg = _make_obj(name="something", hwnd=0xA100, appName="chrome")
    obj = _make_obj(name="", hwnd=0xA100, appName="chrome")
    mock_api(fg)

    nameChangeWatcher.handle(plugin, obj)

    assert calls == []


def test_whitespace_only_name_is_skipped(captured_match, mock_api, debug_off):
    """obj.name이 공백만이면 strip 후 빈 문자열 → skip."""
    plugin, calls = captured_match
    fg = _make_obj(name="\t  \n", hwnd=0xA100, appName="chrome")
    mock_api(fg)

    nameChangeWatcher.handle(plugin, fg)

    assert calls == []


def test_tab_sig_uses_obj_hwnd(captured_match, mock_api, debug_off):
    """tab_sig는 obj.windowHandle 값. Ctrl+Tab 케이스에선 obj==fg이므로 둘 다 같은 값."""
    plugin, calls = captured_match
    fg = _make_obj(name="YouTube - Firefox", hwnd=0x7777, appName="firefox")
    mock_api(fg)

    nameChangeWatcher.handle(plugin, fg)

    assert len(calls) == 1
    _, _, tab_sig = calls[0]
    assert tab_sig == 0x7777


def test_invalid_window_handle_falls_back_to_zero(captured_match, mock_api, debug_off):
    """windowHandle 접근이 실패해도 tab_sig=0으로 위임 진행."""
    plugin, calls = captured_match
    fg = MagicMock()
    fg.name = "Some Title - App"
    fg.appModule = MagicMock()
    fg.appModule.appName = "someapp"
    # windowHandle 접근 시 예외를 던지는 케이스 모사 (property 예외)
    type(fg).windowHandle = property(lambda self: (_ for _ in ()).throw(RuntimeError("handle gone")))
    mock_api(fg)

    nameChangeWatcher.handle(plugin, fg)

    assert len(calls) == 1
    _, _, tab_sig = calls[0]
    assert tab_sig == 0
