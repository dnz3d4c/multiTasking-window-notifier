# -*- coding: utf-8 -*-
"""_match_and_beep 우선순위/비프 파라미터/중복 가드 테스트."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest
from configobj import ConfigObj

from globalPlugins.multiTaskingWindowNotifier import appListStore
from globalPlugins.multiTaskingWindowNotifier.constants import SCOPE_APP, SCOPE_WINDOW


@pytest.fixture
def plugin(monkeypatch, tmp_path):
    """ConfigObj 묶음 + GlobalPlugin 부팅."""
    from globalPlugins.multiTaskingWindowNotifier import settings, settingsPanel

    conf = ConfigObj()
    conf.spec = {}
    fake_config = types.ModuleType("config")
    fake_config.conf = conf
    monkeypatch.setattr(settings, "config", fake_config)
    monkeypatch.setattr(settingsPanel, "config", fake_config)

    sys.modules["globalVars"].appArgs.configPath = str(tmp_path)

    from globalPlugins.multiTaskingWindowNotifier import GlobalPlugin

    return GlobalPlugin()


def _capture_beeps(monkeypatch):
    """play_beep 호출을 캡처하는 fake 설치. v4 시그니처 (app_idx, tab_idx, scope)."""
    import globalPlugins.multiTaskingWindowNotifier as pkg

    calls = []

    def fake(app_idx, tab_idx=None, scope=None, **kwargs):
        calls.append((app_idx, tab_idx, scope))

    monkeypatch.setattr(pkg, "play_beep", fake)
    return calls


def _seed(plugin, items):
    """디스크에 (key, scope) 리스트로 등록 후 메모리 동기화."""
    keys = [k for k, _ in items]
    scopes = {k: s for k, s in items}
    appListStore.save(plugin.appListFile, keys, scopes=scopes)
    plugin.appList = list(keys)
    plugin._rebuild_lookup()


def test_window_match_wins_over_app_match(plugin, monkeypatch):
    """창 + 앱이 동시 등록일 때 창 매치가 우선. v4: (app_idx, tab_idx, scope)."""
    _seed(plugin, [
        ("chrome", SCOPE_APP),
        ("chrome|YouTube", SCOPE_WINDOW),
    ])
    calls = _capture_beeps(monkeypatch)

    plugin._match_and_beep("chrome", "YouTube")

    # appBeepMap[chrome]=0 (첫 할당), chrome 내 첫 window tabBeepIdx=0
    assert calls == [(0, 0, SCOPE_WINDOW)]


def test_app_match_used_as_fallback(plugin, monkeypatch):
    """창 매치가 없으면 앱 매치로 fallback. scope=app은 tab_idx=None 단음."""
    _seed(plugin, [
        ("chrome", SCOPE_APP),
    ])
    calls = _capture_beeps(monkeypatch)

    plugin._match_and_beep("chrome", "어떤 탭이든")

    # appBeepMap[chrome]=0, scope=app이므로 tab_idx=None
    assert calls == [(0, None, SCOPE_APP)]


def test_window_tab_beep_is_distinct_per_window(plugin, monkeypatch):
    """같은 appId 내 서로 다른 window는 서로 다른 tabBeepIdx를 받는다."""
    _seed(plugin, [
        ("chrome", SCOPE_APP),                # appBeepMap[chrome]=0
        ("chrome|Tab A", SCOPE_WINDOW),       # chrome 내 첫 window → tabBeepIdx=0
        ("notepad|Memo", SCOPE_WINDOW),       # 새 appId → appBeepMap[notepad]=63
        ("chrome|Tab B", SCOPE_WINDOW),       # chrome 내 두 번째 → tabBeepIdx=63
    ])
    calls = _capture_beeps(monkeypatch)

    plugin._match_and_beep("chrome", "Tab A")
    # 중복 가드 회피용 시간 경과 시뮬레이션
    plugin._last_matched_ts = 0.0
    plugin._match_and_beep("chrome", "Tab B")

    # Tab A / Tab B 모두 chrome 앱 비프 공유(app_idx=0), 탭 비프는 0과 63으로 분리.
    assert calls == [
        (0, 0, SCOPE_WINDOW),
        (0, 63, SCOPE_WINDOW),
    ]


def test_window_without_app_entry_still_has_app_beep(plugin, monkeypatch):
    """scope=app entry가 없어도 appBeepMap은 자동 할당되어 app_idx 확보."""
    _seed(plugin, [
        ("notepad|Memo A", SCOPE_WINDOW),  # appBeepMap[notepad]=0, tabBeepIdx=0
        ("chrome|YouTube", SCOPE_WINDOW),  # appBeepMap[chrome]=63, tabBeepIdx=0
        ("notepad|Memo B", SCOPE_WINDOW),  # notepad 두 번째 → tabBeepIdx=63
    ])
    calls = _capture_beeps(monkeypatch)

    plugin._match_and_beep("notepad", "Memo B")

    # notepad는 app entry 없이도 appBeepMap에 등록되어 app_idx=0.
    # Memo B는 notepad 두 번째 window라 tabBeepIdx=63.
    assert calls == [(0, 63, SCOPE_WINDOW)]


def test_dedup_guard_suppresses_consecutive_match(plugin, monkeypatch):
    """같은 키가 _MATCH_DEDUP_SEC 이내 재매칭되면 비프가 한 번만 발사."""
    _seed(plugin, [("chrome|YouTube", SCOPE_WINDOW)])
    calls = _capture_beeps(monkeypatch)

    plugin._match_and_beep("chrome", "YouTube")
    plugin._match_and_beep("chrome", "YouTube")  # 즉시 재호출
    plugin._match_and_beep("chrome", "YouTube")

    assert len(calls) == 1


def test_dedup_guard_resets_after_window(plugin, monkeypatch):
    """가드 윈도우가 지나면 재매칭이 다시 발사된다."""
    _seed(plugin, [("chrome|YouTube", SCOPE_WINDOW)])
    calls = _capture_beeps(monkeypatch)

    plugin._match_and_beep("chrome", "YouTube")
    plugin._last_matched_ts = 0.0  # 충분히 오래 전으로
    plugin._match_and_beep("chrome", "YouTube")

    assert len(calls) == 2


def test_no_match_is_silent(plugin, monkeypatch):
    """등록 안 된 (appId, title)은 무음."""
    _seed(plugin, [("chrome|YouTube", SCOPE_WINDOW)])
    calls = _capture_beeps(monkeypatch)

    plugin._match_and_beep("notepad", "missing")

    assert calls == []


def test_title_only_reverse_mapping_uses_real_app_beep(plugin, monkeypatch):
    """title 역매핑 매치 시 entry의 real appId로 appBeepMap을 조회."""
    _seed(plugin, [("notepad|Memo", SCOPE_WINDOW)])
    calls = _capture_beeps(monkeypatch)

    # 호출 인자 appId='explorer'(Alt+Tab 오버레이)지만 matched_key의 real appId는 notepad.
    plugin._match_and_beep("explorer", "Memo")

    assert calls == [(0, 0, SCOPE_WINDOW)]
    # 메타가 정확히 "notepad|Memo" entry에 기록되었는지 확인
    meta = appListStore.get_meta(plugin.appListFile, "notepad|Memo")
    assert meta["switchCount"] == 1
