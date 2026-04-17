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
    """play_beep 호출을 캡처하는 fake 설치."""
    import globalPlugins.multiTaskingWindowNotifier as pkg

    calls = []

    def fake(base_idx, order, scope, **kwargs):
        calls.append((base_idx, order, scope))

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
    """창 + 앱이 동시 등록일 때 창 매치가 우선."""
    _seed(plugin, [
        ("chrome", SCOPE_APP),
        ("chrome|YouTube", SCOPE_WINDOW),
    ])
    calls = _capture_beeps(monkeypatch)

    plugin._match_and_beep("chrome", "YouTube")

    # base_idx=0(chrome app entry), order=1(첫 SCOPE_WINDOW), scope=window
    assert calls == [(0, 1, SCOPE_WINDOW)]


def test_app_match_used_as_fallback(plugin, monkeypatch):
    """창 매치가 없으면 앱 매치로 fallback."""
    _seed(plugin, [
        ("chrome", SCOPE_APP),
    ])
    calls = _capture_beeps(monkeypatch)

    plugin._match_and_beep("chrome", "어떤 탭이든")

    # SCOPE_APP은 order 무시, base_idx=0(chrome app entry), order=1
    assert calls == [(0, 1, SCOPE_APP)]


def test_window_order_increments_per_appid(plugin, monkeypatch):
    """같은 appId 창 entry의 order가 등록 순서로 증가."""
    _seed(plugin, [
        ("chrome", SCOPE_APP),                # idx=0
        ("chrome|Tab A", SCOPE_WINDOW),       # idx=1, order=1
        ("notepad|Memo", SCOPE_WINDOW),       # idx=2, 다른 앱이라 카운트 영향 없음
        ("chrome|Tab B", SCOPE_WINDOW),       # idx=3, order=2
    ])
    calls = _capture_beeps(monkeypatch)

    plugin._match_and_beep("chrome", "Tab A")
    # 중복 가드 회피용 시간 경과 시뮬레이션
    plugin._last_matched_ts = 0.0
    plugin._match_and_beep("chrome", "Tab B")

    assert calls == [
        (0, 1, SCOPE_WINDOW),  # base=app(chrome) idx=0, order=1
        (0, 2, SCOPE_WINDOW),  # base=app(chrome) idx=0, order=2
    ]


def test_window_without_app_entry_uses_first_window_idx(plugin, monkeypatch):
    """앱 entry가 없으면 같은 appId 첫 창 entry idx가 base_idx."""
    _seed(plugin, [
        ("notepad|Memo A", SCOPE_WINDOW),  # idx=0, order=1
        ("chrome|YouTube", SCOPE_WINDOW),  # idx=1
        ("notepad|Memo B", SCOPE_WINDOW),  # idx=2, order=2
    ])
    calls = _capture_beeps(monkeypatch)

    plugin._match_and_beep("notepad", "Memo B")

    # notepad의 첫 창 entry는 idx=0(Memo A) → base_idx=0, order=2
    assert calls == [(0, 2, SCOPE_WINDOW)]


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


def test_title_only_reverse_mapping_returns_full_entry(plugin, monkeypatch):
    """title 역매핑으로 매치되어도 record_switch에는 entry 풀키가 전달돼야 함."""
    _seed(plugin, [("notepad|Memo", SCOPE_WINDOW)])
    calls = _capture_beeps(monkeypatch)

    # title만 일치하는 케이스 (Alt+Tab 오버레이가 obj.appId='explorer'로 전달)
    plugin._match_and_beep("explorer", "Memo")

    assert calls == [(0, 1, SCOPE_WINDOW)]
    # 메타가 정확히 "notepad|Memo" entry에 기록되었는지 확인
    meta = appListStore.get_meta(plugin.appListFile, "notepad|Memo")
    assert meta["switchCount"] == 1
