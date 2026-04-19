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


def test_empty_fg_name_is_skipped(captured_match, mock_api, debug_off):
    """fg.name이 비어있으면 skip (조기 컷 통과 후 fg 제목 없음 단계).

    조기 컷은 hwnd 비교이므로 obj/fg가 같은 창(hwnd 동일)이라도 통과하지만,
    그 이후 fg.name이 empty면 매칭 위임 전에 skip. obj.name 자체는 더 이상
    읽지 않음 (fg.name만이 탭 제목의 진실된 소스).
    """
    plugin, calls = captured_match
    fg = _make_obj(name="", hwnd=0xA100, appName="chrome")
    mock_api(fg)

    nameChangeWatcher.handle(plugin, fg)

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


def test_invalid_window_handle_is_cut(captured_match, mock_api, debug_off):
    """windowHandle 접근이 실패하면 안전하게 조기 컷 (창 본체 판정 불가).

    이전 구현은 tab_sig=0 폴백으로 매칭까지 진행했지만, hwnd 비교 기반 조기
    컷에서는 판정 불가 → 보수적으로 return. 실환경에서 NVDAObject의
    windowHandle이 예외를 던지는 건 극히 드물며, 그 상태로 매칭을 진행해봐야
    tab_sig=0이 되어 sig_guard가 무의미해진다.
    """
    plugin, calls = captured_match
    fg = MagicMock()
    fg.name = "Some Title - App"
    fg.appModule = MagicMock()
    fg.appModule.appName = "someapp"
    # windowHandle 접근 시 예외를 던지는 케이스 모사 (property 예외)
    type(fg).windowHandle = property(lambda self: (_ for _ in ()).throw(RuntimeError("handle gone")))
    mock_api(fg)

    nameChangeWatcher.handle(plugin, fg)

    assert calls == []


def test_menu_item_obj_is_cut_before_name_compare(captured_match, mock_api, debug_off):
    """Firefox 북마크 메뉴 항목처럼 obj != fg인 이벤트는 조기 컷.

    obj.name과 fg.name이 우연히 같은 문자열이어도 identity 비교가 먼저라서
    matcher까지 가지 않는다. 실사용에서 메뉴/DOM 자식 이벤트가 여기 걸려
    DBG 로그 노이즈도 생략된다.
    """
    plugin, calls = captured_match
    fg = _make_obj(name="YouTube - Mozilla Firefox", hwnd=0x1000, appName="firefox")
    # obj는 fg와 다른 객체지만 우연히 name이 동일 (엣지케이스)
    menu_item = _make_obj(name="YouTube - Mozilla Firefox", hwnd=0x1001, appName="firefox")
    mock_api(fg)

    nameChangeWatcher.handle(plugin, menu_item)

    assert calls == []  # 조기 컷으로 matcher 미호출


def test_fg_identity_allows_match(captured_match, mock_api, debug_off):
    """obj가 fg와 동일 객체면 조기 컷을 통과해 매칭까지 진행된다 (핵심 회귀 방지)."""
    plugin, calls = captured_match
    fg = _make_obj(name="document.txt - Notepad++", hwnd=0xC200, appName="notepad++")
    mock_api(fg)

    nameChangeWatcher.handle(plugin, fg)

    assert len(calls) == 1
    appId, _, tab_sig = calls[0]
    assert appId == "notepad++"
    assert tab_sig == 0xC200
