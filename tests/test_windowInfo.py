# -*- coding: utf-8 -*-
"""windowInfo.get_current_window_info 엣지.

포커스 객체가 없거나 name이 비어 있거나 dirty 마커만 있는 케이스에서 모두
(None, None, None, None) 4-tuple을 반환해 호출부(스크립트)가 단일 분기로
처리할 수 있게 한다. 정상 경로는 normalize_title이 적용된 title을 돌려준다.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

from globalPlugins.multiTaskingWindowNotifier import windowInfo


@pytest.fixture
def fake_fg(monkeypatch):
    """`api.getForegroundObject`를 임의 반환값으로 바꿔주는 헬퍼 fixture."""
    def _set(foreground):
        monkeypatch.setattr(sys.modules["api"], "getForegroundObject", lambda: foreground)
    return _set


def test_foreground_none_returns_all_none(fake_fg):
    fake_fg(None)
    assert windowInfo.get_current_window_info() == (None, None, None, None)


def test_empty_name_returns_all_none(fake_fg):
    foreground = MagicMock(name="foreground")
    foreground.name = ""
    fake_fg(foreground)
    assert windowInfo.get_current_window_info() == (None, None, None, None)


def test_dirty_marker_only_returns_all_none(fake_fg):
    """선두 마커(`*`)만 남아 normalize가 빈 문자열을 돌려주면 조기 반환."""
    foreground = MagicMock(name="foreground")
    foreground.name = "*"
    fake_fg(foreground)
    assert windowInfo.get_current_window_info() == (None, None, None, None)


def test_normal_title_normalized_and_composite_key(fake_fg, monkeypatch):
    """꼬리 앱명 서픽스가 제거된 title로 appId|title 복합키가 구성된다."""
    foreground = MagicMock(name="foreground")
    foreground.name = "제목 없음 - 메모장"
    foreground.windowClassName = "Notepad"
    fake_fg(foreground)

    # getAppId가 appModuleHandler 경유 → 스텁 appModule을 붙여준다.
    app_module = types.SimpleNamespace(appName="notepad")
    foreground.appModule = app_module

    result_fg, appId, title, key = windowInfo.get_current_window_info()
    assert result_fg is foreground
    assert appId == "notepad"
    assert title == "제목 없음"
    assert key == "notepad|제목 없음"
