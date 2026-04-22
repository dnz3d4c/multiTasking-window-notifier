# -*- coding: utf-8 -*-
"""tutorial.windowEnum의 필터 분기 검증.

실제 Windows DLL 호출은 배제하고, 모듈 속성 `_user32`와 `_is_cloaked`를
monkeypatch로 교체해 콜백 경로만 테스트. EnumWindows 콜백 시뮬레이터가
여러 hwnd를 전달하면 필터 규칙(visible + title 있음 + cloaked 아님 +
self-hwnd 아님)이 올바르게 걸러내는지 확인.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock


def _make_fake_user32(hwnds_to_emit, visible_map, title_map):
    """콜백 호출을 재현하는 fake user32 객체를 생성.

    Args:
        hwnds_to_emit: 콜백에 순서대로 전달할 hwnd 리스트.
        visible_map: {hwnd: bool} — IsWindowVisible 반환.
        title_map: {hwnd: str} — GetWindowTextW로 buf에 쓸 제목.
    """
    mock = MagicMock()

    def fake_enum(cb, lparam):
        for hwnd in hwnds_to_emit:
            cont = cb(hwnd, lparam)
            if cont is False:
                break
        return True

    def fake_get_text_length(hwnd):
        return len(title_map.get(hwnd, ""))

    def fake_get_text(hwnd, buf, n):
        title = title_map.get(hwnd, "")
        buf.value = title
        return len(title)

    mock.EnumWindows = fake_enum
    mock.IsWindowVisible = lambda h: visible_map.get(h, True)
    mock.GetWindowTextLengthW = fake_get_text_length
    mock.GetWindowTextW = fake_get_text
    return mock


@pytest.fixture
def patch_win_api(monkeypatch):
    """windowEnum 내부 WinAPI 진입점들을 테스트용으로 교체하는 헬퍼 fixture."""
    from globalPlugins.multiTaskingWindowNotifier.tutorial import windowEnum

    def _apply(hwnds, visible=None, titles=None, cloaked=None):
        visible = visible or {}
        titles = titles or {}
        cloaked = cloaked or {}
        fake = _make_fake_user32(hwnds, visible, titles)
        monkeypatch.setattr(windowEnum, "_user32", fake)
        monkeypatch.setattr(
            windowEnum,
            "_is_cloaked",
            lambda h: cloaked.get(h, False),
        )
        return fake

    return _apply


def test_returns_visible_windows_with_titles(patch_win_api):
    from globalPlugins.multiTaskingWindowNotifier.tutorial import windowEnum

    patch_win_api(
        hwnds=[101, 102, 103],
        visible={101: True, 102: True, 103: True},
        titles={101: "notepad", 102: "chrome", 103: "explorer"},
    )

    result = windowEnum.enum_visible_top_windows()
    titles = [r["title"] for r in result]
    assert titles == ["notepad", "chrome", "explorer"]


def test_filters_invisible_windows(patch_win_api):
    from globalPlugins.multiTaskingWindowNotifier.tutorial import windowEnum

    patch_win_api(
        hwnds=[101, 102, 103],
        visible={101: True, 102: False, 103: True},
        titles={101: "a", 102: "b", 103: "c"},
    )

    result = windowEnum.enum_visible_top_windows()
    titles = [r["title"] for r in result]
    assert titles == ["a", "c"]


def test_filters_empty_titles(patch_win_api):
    from globalPlugins.multiTaskingWindowNotifier.tutorial import windowEnum

    patch_win_api(
        hwnds=[101, 102, 103],
        visible={101: True, 102: True, 103: True},
        titles={101: "a", 102: "", 103: "c"},
    )

    result = windowEnum.enum_visible_top_windows()
    titles = [r["title"] for r in result]
    assert titles == ["a", "c"]


def test_filters_cloaked_windows(patch_win_api):
    """Win10 가상 데스크톱 간 이동한 hidden 창은 제외."""
    from globalPlugins.multiTaskingWindowNotifier.tutorial import windowEnum

    patch_win_api(
        hwnds=[101, 102, 103],
        visible={101: True, 102: True, 103: True},
        titles={101: "a", 102: "b", 103: "c"},
        cloaked={102: True},
    )

    result = windowEnum.enum_visible_top_windows()
    titles = [r["title"] for r in result]
    assert titles == ["a", "c"]


def test_excludes_self_hwnd(patch_win_api):
    """튜토리얼 다이얼로그 자신의 hwnd는 exclude_hwnds로 걸러야 한다."""
    from globalPlugins.multiTaskingWindowNotifier.tutorial import windowEnum

    patch_win_api(
        hwnds=[101, 102, 103],
        visible={101: True, 102: True, 103: True},
        titles={101: "a", 102: "tutorial-self", 103: "c"},
    )

    result = windowEnum.enum_visible_top_windows(exclude_hwnds={102})
    titles = [r["title"] for r in result]
    assert titles == ["a", "c"]


def test_limit_stops_enumeration(patch_win_api):
    """limit 도달 시 콜백이 False 반환하며 조기 종료."""
    from globalPlugins.multiTaskingWindowNotifier.tutorial import windowEnum

    patch_win_api(
        hwnds=[101, 102, 103, 104, 105],
        visible={h: True for h in [101, 102, 103, 104, 105]},
        titles={101: "a", 102: "b", 103: "c", 104: "d", 105: "e"},
    )

    result = windowEnum.enum_visible_top_windows(limit=2)
    titles = [r["title"] for r in result]
    assert titles == ["a", "b"]


def test_strips_whitespace_in_titles(patch_win_api):
    """GetWindowTextW가 반환한 제목의 앞뒤 공백 제거."""
    from globalPlugins.multiTaskingWindowNotifier.tutorial import windowEnum

    patch_win_api(
        hwnds=[101, 102],
        visible={101: True, 102: True},
        titles={101: "  notepad  ", 102: "\tchrome\n"},
    )

    result = windowEnum.enum_visible_top_windows()
    titles = [r["title"] for r in result]
    assert titles == ["notepad", "chrome"]


def test_whitespace_only_title_is_filtered(patch_win_api):
    """공백만 있는 제목은 빈 제목과 동급으로 제외."""
    from globalPlugins.multiTaskingWindowNotifier.tutorial import windowEnum

    patch_win_api(
        hwnds=[101, 102],
        visible={101: True, 102: True},
        titles={101: "   ", 102: "real"},
    )

    result = windowEnum.enum_visible_top_windows()
    titles = [r["title"] for r in result]
    assert titles == ["real"]


def test_returns_empty_list_when_enum_fails(monkeypatch):
    """EnumWindows 호출 자체가 예외를 던져도 빈 리스트 반환."""
    from globalPlugins.multiTaskingWindowNotifier.tutorial import windowEnum

    fake_user32 = MagicMock()
    fake_user32.EnumWindows = MagicMock(side_effect=OSError("boom"))
    monkeypatch.setattr(windowEnum, "_user32", fake_user32)

    result = windowEnum.enum_visible_top_windows()
    assert result == []
