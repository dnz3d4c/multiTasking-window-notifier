# -*- coding: utf-8 -*-
"""tutorial.windowEnum 의 NVDA object 트리 순회 검증.

실제 Windows DLL 호출은 배제하고, `api.getDesktopObject()`가 반환하는 desktop
mock의 `firstChild → .next` 체인을 테스트별로 구성해 필터 규칙(Role.WINDOW +
title 있음 + cloaked 아님 + exclude 아님 + 중복 아님)이 올바르게 걸러내는지
확인.

`isinstance(obj, Window)` 체크 통과를 위해 mock은 `spec=Window`로 생성.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock


def _make_fake_window(hwnd, title, role=None):
    """NVDAObjects.window.Window 스펙의 mock 생성.

    role을 넘기지 않으면 기본 `Role.WINDOW`(controlTypes 스텁의 캐시된 속성).
    """
    from NVDAObjects.window import Window
    import controlTypes

    obj = MagicMock(spec=Window)
    obj.windowHandle = hwnd
    obj.name = title
    obj.role = role if role is not None else controlTypes.Role.WINDOW
    obj.next = None  # 체인 연결은 _chain이 수행
    return obj


def _chain(objs):
    """리스트 순서대로 obj.next를 연결해 linked list 구성. 첫 노드 반환."""
    for i, obj in enumerate(objs):
        obj.next = objs[i + 1] if i + 1 < len(objs) else None
    return objs[0] if objs else None


@pytest.fixture
def patch_desktop(monkeypatch):
    """`api.getDesktopObject()` + `_is_cloaked`를 테스트용으로 교체."""
    from globalPlugins.multiTaskingWindowNotifier.tutorial import windowEnum

    def _apply(objs, cloaked_map=None):
        cloaked_map = cloaked_map or {}
        first = _chain(objs)
        desktop = MagicMock()
        desktop.firstChild = first
        # api는 conftest에서 MagicMock 모듈. 하위 함수도 MagicMock이라 return_value 세팅 가능.
        windowEnum.api.getDesktopObject = MagicMock(return_value=desktop)
        monkeypatch.setattr(
            windowEnum,
            "_is_cloaked",
            lambda h: cloaked_map.get(h, False),
        )

    return _apply


def test_returns_windows_from_desktop_tree(patch_desktop):
    from globalPlugins.multiTaskingWindowNotifier.tutorial import windowEnum

    objs = [
        _make_fake_window(101, "notepad"),
        _make_fake_window(102, "chrome"),
        _make_fake_window(103, "explorer"),
    ]
    patch_desktop(objs)

    result = windowEnum.enum_visible_top_windows()
    assert [r["title"] for r in result] == ["notepad", "chrome", "explorer"]
    assert [r["hwnd"] for r in result] == [101, 102, 103]


def test_filters_empty_titles(patch_desktop):
    from globalPlugins.multiTaskingWindowNotifier.tutorial import windowEnum

    objs = [
        _make_fake_window(101, "a"),
        _make_fake_window(102, ""),
        _make_fake_window(103, "c"),
    ]
    patch_desktop(objs)

    result = windowEnum.enum_visible_top_windows()
    assert [r["title"] for r in result] == ["a", "c"]


def test_filters_none_title(patch_desktop):
    """obj.name이 None인 창 (UIA/IA 경로에서 드물게 발생)."""
    from globalPlugins.multiTaskingWindowNotifier.tutorial import windowEnum

    objs = [
        _make_fake_window(101, "a"),
        _make_fake_window(102, None),
        _make_fake_window(103, "c"),
    ]
    patch_desktop(objs)

    result = windowEnum.enum_visible_top_windows()
    assert [r["title"] for r in result] == ["a", "c"]


def test_filters_cloaked_windows(patch_desktop):
    """Win10 가상 데스크톱 간 이동한 hidden 창은 제외."""
    from globalPlugins.multiTaskingWindowNotifier.tutorial import windowEnum

    objs = [
        _make_fake_window(101, "a"),
        _make_fake_window(102, "b"),
        _make_fake_window(103, "c"),
    ]
    patch_desktop(objs, cloaked_map={102: True})

    result = windowEnum.enum_visible_top_windows()
    assert [r["title"] for r in result] == ["a", "c"]


def test_filters_non_window_role(patch_desktop):
    """Role이 WINDOW가 아닌 Desktop overlay 등은 제외."""
    from globalPlugins.multiTaskingWindowNotifier.tutorial import windowEnum
    import controlTypes

    # MagicMock 속성 identity: Role.PANE != Role.WINDOW.
    objs = [
        _make_fake_window(101, "a"),
        _make_fake_window(102, "b", role=controlTypes.Role.PANE),
        _make_fake_window(103, "c"),
    ]
    patch_desktop(objs)

    result = windowEnum.enum_visible_top_windows()
    assert [r["title"] for r in result] == ["a", "c"]


def test_excludes_self_hwnd(patch_desktop):
    """튜토리얼 다이얼로그 자신의 hwnd는 exclude_hwnds로 걸러야 한다."""
    from globalPlugins.multiTaskingWindowNotifier.tutorial import windowEnum

    objs = [
        _make_fake_window(101, "a"),
        _make_fake_window(102, "tutorial-self"),
        _make_fake_window(103, "c"),
    ]
    patch_desktop(objs)

    result = windowEnum.enum_visible_top_windows(exclude_hwnds={102})
    assert [r["title"] for r in result] == ["a", "c"]


def test_limit_stops_enumeration(patch_desktop):
    """limit 도달 시 즉시 종료."""
    from globalPlugins.multiTaskingWindowNotifier.tutorial import windowEnum

    objs = [
        _make_fake_window(100 + i, chr(ord("a") + i)) for i in range(5)
    ]
    patch_desktop(objs)

    result = windowEnum.enum_visible_top_windows(limit=2)
    assert [r["title"] for r in result] == ["a", "b"]


def test_strips_whitespace_in_titles(patch_desktop):
    from globalPlugins.multiTaskingWindowNotifier.tutorial import windowEnum

    objs = [
        _make_fake_window(101, "  notepad  "),
        _make_fake_window(102, "\tchrome\n"),
    ]
    patch_desktop(objs)

    result = windowEnum.enum_visible_top_windows()
    assert [r["title"] for r in result] == ["notepad", "chrome"]


def test_whitespace_only_title_is_filtered(patch_desktop):
    """공백만 있는 제목은 빈 제목과 동급으로 제외."""
    from globalPlugins.multiTaskingWindowNotifier.tutorial import windowEnum

    objs = [
        _make_fake_window(101, "   "),
        _make_fake_window(102, "real"),
    ]
    patch_desktop(objs)

    result = windowEnum.enum_visible_top_windows()
    assert [r["title"] for r in result] == ["real"]


def test_returns_empty_when_desktop_unavailable(monkeypatch):
    """api.getDesktopObject()가 예외를 던져도 빈 리스트 반환."""
    from globalPlugins.multiTaskingWindowNotifier.tutorial import windowEnum

    windowEnum.api.getDesktopObject = MagicMock(side_effect=OSError("boom"))

    result = windowEnum.enum_visible_top_windows()
    assert result == []


def test_returns_empty_when_desktop_is_none(monkeypatch):
    """api.getDesktopObject()가 None 반환해도 안전하게 빈 리스트."""
    from globalPlugins.multiTaskingWindowNotifier.tutorial import windowEnum

    windowEnum.api.getDesktopObject = MagicMock(return_value=None)

    result = windowEnum.enum_visible_top_windows()
    assert result == []


def test_stops_when_next_raises(patch_desktop, monkeypatch):
    """obj.next 호출이 예외를 던지면 현재까지 수집된 결과만 반환."""
    from globalPlugins.multiTaskingWindowNotifier.tutorial import windowEnum

    good = _make_fake_window(101, "ok")
    broken = _make_fake_window(102, "broken")
    # .next 접근 자체가 예외 — PropertyMock 대신 descriptor trick.
    type(broken).next = property(
        fget=lambda self: (_ for _ in ()).throw(RuntimeError("next boom"))
    )
    good.next = broken

    desktop = MagicMock()
    desktop.firstChild = good
    windowEnum.api.getDesktopObject = MagicMock(return_value=desktop)
    monkeypatch.setattr(windowEnum, "_is_cloaked", lambda h: False)

    result = windowEnum.enum_visible_top_windows()
    # good은 포함, broken 처리 중 .next가 터져 루프 종료. broken 자체는 포함됨
    # (예외는 .next 접근 시점에 발생하므로 _maybe_extract_entry는 통과).
    assert [r["title"] for r in result] == ["ok", "broken"]


def test_excludes_duplicate_hwnds(patch_desktop):
    """같은 hwnd가 두 번 나와도 중복 제거."""
    from globalPlugins.multiTaskingWindowNotifier.tutorial import windowEnum

    objs = [
        _make_fake_window(101, "first"),
        _make_fake_window(101, "dup"),
        _make_fake_window(102, "second"),
    ]
    patch_desktop(objs)

    result = windowEnum.enum_visible_top_windows()
    assert [r["title"] for r in result] == ["first", "second"]
