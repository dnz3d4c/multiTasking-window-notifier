# -*- coding: utf-8 -*-
"""play_beep 시그니처 및 2음 재생 분기 검증.

tones.beep과 wx.CallLater를 각각 모킹해 호출 인자/횟수를 확인한다.
실제 사운드 디바이스 접근 없이 재생 정책을 검증한다.
"""

from unittest.mock import MagicMock

import pytest

from globalPlugins.multiTaskingWindowNotifier import beepPlayer
from globalPlugins.multiTaskingWindowNotifier.constants import (
    BEEP_TABLE,
    SCOPE_APP,
    SCOPE_WINDOW,
)


@pytest.fixture
def mock_tones(monkeypatch):
    """tones.beep 호출을 캡처."""
    calls = []

    def fake_beep(freq, duration):
        calls.append(("beep", freq, duration))

    monkeypatch.setattr(beepPlayer.tones, "beep", fake_beep)
    return calls


@pytest.fixture
def mock_call_later(monkeypatch):
    """core.callLater(NVDA 권장) + wx.CallLater 폴백 둘 다 즉시 실행으로 대체."""
    def fake_call_later(ms, fn, *args, **kwargs):
        fn(*args, **kwargs)

    fake_core = MagicMock()
    fake_core.callLater = fake_call_later

    fake_wx = MagicMock()
    fake_wx.CallLater = fake_call_later

    # beepPlayer._schedule_second_beep이 `import core` → 실패 시 `import wx`.
    # 두 쪽 다 주입해두면 어떤 경로든 즉시 실행된다.
    import sys
    monkeypatch.setitem(sys.modules, "core", fake_core)
    monkeypatch.setitem(sys.modules, "wx", fake_wx)
    return fake_core


def test_scope_app_plays_single_beep(mock_tones, mock_call_later):
    """scope=app은 app_idx 단음 1회 재생. tab_idx는 무시."""
    beepPlayer.play_beep(10, tab_idx=20, scope=SCOPE_APP,
                         duration=50, gap_ms=15)

    # 단 1번, app_idx=10의 주파수.
    assert len(mock_tones) == 1
    assert mock_tones[0] == ("beep", BEEP_TABLE[10], 50)


def test_scope_window_plays_two_beeps(mock_tones, mock_call_later):
    """scope=window + tab_idx 지정 → a → b 2음."""
    beepPlayer.play_beep(5, tab_idx=30, scope=SCOPE_WINDOW,
                         duration=50, gap_ms=15)

    assert len(mock_tones) == 2
    # 첫 번째: app_idx=5의 주파수 (앱 비프 a)
    assert mock_tones[0] == ("beep", BEEP_TABLE[5], 50)
    # 두 번째: tab_idx=30의 주파수 (탭 비프 b)
    assert mock_tones[1] == ("beep", BEEP_TABLE[30], 50)


def test_scope_window_without_tab_idx_is_single_beep(mock_tones, mock_call_later):
    """scope=window지만 tab_idx=None이면 단음 fallback."""
    beepPlayer.play_beep(7, tab_idx=None, scope=SCOPE_WINDOW,
                         duration=50, gap_ms=15)

    assert len(mock_tones) == 1
    assert mock_tones[0] == ("beep", BEEP_TABLE[7], 50)


def test_app_idx_out_of_range_is_silent(mock_tones, mock_call_later):
    """app_idx 범위 밖이면 경고 로그 + 무음."""
    beepPlayer.play_beep(999, tab_idx=0, scope=SCOPE_WINDOW,
                         duration=50, gap_ms=100)

    assert mock_tones == []


def test_tab_idx_out_of_range_falls_back_to_single(mock_tones, mock_call_later):
    """tab_idx가 범위 밖이면 경고 + 단음 (app 비프는 발사)."""
    beepPlayer.play_beep(10, tab_idx=999, scope=SCOPE_WINDOW,
                         duration=50, gap_ms=15)

    # a는 이미 재생됐고 b는 생략.
    assert len(mock_tones) == 1
    assert mock_tones[0] == ("beep", BEEP_TABLE[10], 50)


def test_scope_app_does_not_schedule_second_beep(mock_tones, mock_call_later):
    """scope=app에서는 wx.CallLater가 호출되지 않아야 함."""
    # _schedule_second_beep이 wx를 import하므로 그 호출 여부로 확인.
    # 여기서는 mock_tones 길이로 간접 검증 (app은 1번만).
    beepPlayer.play_beep(0, tab_idx=5, scope=SCOPE_APP,
                         duration=50, gap_ms=100)
    assert len(mock_tones) == 1
