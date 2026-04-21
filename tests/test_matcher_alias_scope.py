# -*- coding: utf-8 -*-
"""v8 aliases 회귀 가드: scope=app + alias로 잡혔을 때 **단음** 재생.

Phase 7(v8 aliases) 전에는 `matcher.py`의 title-only 역매핑 분기가
`scope=SCOPE_WINDOW`로 하드코딩되어 있었다. v8에서 scope=app entry도
alias로 windowLookup에 역매핑되므로, 하드코딩을 유지하면 scope=app entry가
alias 경유로 히트됐을 때 2음이 재생되는 회귀가 발생한다.

본 테스트는 scope=app entry "messenger"에 alias "대화창제목"을 달고
Alt+Tab 오버레이 시뮬레이션(appId="" + 역매핑 title)에서 단음
(tab_idx=None, scope=SCOPE_APP)이 재생되는지 가드한다.
"""

from __future__ import annotations

import sys
import types

import pytest
from configobj import ConfigObj

from globalPlugins.multiTaskingWindowNotifier import store
from globalPlugins.multiTaskingWindowNotifier.constants import SCOPE_APP, SCOPE_WINDOW


@pytest.fixture
def plugin(monkeypatch, tmp_path):
    """실 ConfigObj 바인딩 + GlobalPlugin 부팅. 다른 매칭 테스트와 동일 패턴."""
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
    """play_beep 호출을 (app_idx, tab_idx, scope)로 캡처."""
    from globalPlugins.multiTaskingWindowNotifier import beepPlayer

    calls = []

    def fake(app_idx, tab_idx=None, scope=None, **kwargs):
        calls.append((app_idx, tab_idx, scope))

    monkeypatch.setattr(beepPlayer, "play_beep", fake)
    return calls


def test_alias_hit_on_app_scope_entry_plays_single_note(plugin, monkeypatch):
    """scope=app entry의 alias가 역매핑으로 잡히면 단음(tab_idx=None, scope=app)."""
    # scope=app entry 등록 + alias 설정
    store.save(plugin.appListFile, ["messenger"], scopes={"messenger": SCOPE_APP})
    assert store.set_aliases(plugin.appListFile, "messenger", ["대화창제목"])
    plugin.appList = store.load(plugin.appListFile)
    plugin._rebuild_lookup()

    calls = _capture_beeps(monkeypatch)

    # Alt+Tab 오버레이 시뮬레이션: match_appId="" + alias title.
    # focusDispatcher가 Alt+Tab 분기에서 match_appId=""를 내리는 구조를 그대로 재현.
    plugin._match_and_beep("", "대화창제목", tab_sig=0x2001)

    assert len(calls) == 1, f"단일 호출 기대, 실제: {calls}"
    _app_idx, tab_idx, scope = calls[0]
    # 핵심 가드: scope=app은 반드시 단음 (tab_idx=None).
    assert tab_idx is None, f"scope=app alias 매칭이 2음으로 재생됨 — scope 하드코딩 회귀"
    assert scope == SCOPE_APP, f"scope 조회 실패 — 기대 {SCOPE_APP}, 실제 {scope!r}"


def test_alias_hit_on_window_scope_entry_still_plays_double_note(plugin, monkeypatch):
    """scope=window entry의 alias가 역매핑으로 잡히면 기존 2음 재생 유지."""
    store.save(plugin.appListFile, ["notepad|메모"], scopes={"notepad|메모": SCOPE_WINDOW})
    assert store.set_aliases(plugin.appListFile, "notepad|메모", ["별칭제목"])
    plugin.appList = store.load(plugin.appListFile)
    plugin._rebuild_lookup()

    calls = _capture_beeps(monkeypatch)

    # alias로 매칭 (title-only 역매핑 경유).
    plugin._match_and_beep("", "별칭제목", tab_sig=0x3001)

    assert len(calls) == 1
    _app_idx, tab_idx, scope = calls[0]
    # scope=window는 tabBeepIdx가 있어야 하므로 int 반환.
    assert isinstance(tab_idx, int), f"scope=window alias 매칭이 단음으로 재생됨 — 회귀"
    assert scope == SCOPE_WINDOW


def test_alias_registered_in_window_lookup_for_app_scope(plugin):
    """scope=app entry의 alias가 windowLookup에 등록되어야 title-only 역매핑 가능."""
    store.save(plugin.appListFile, ["messenger"], scopes={"messenger": SCOPE_APP})
    store.set_aliases(plugin.appListFile, "messenger", ["대화창제목"])
    plugin.appList = store.load(plugin.appListFile)
    plugin._rebuild_lookup()

    # scope=app entry는 appLookup에 있고, alias는 windowLookup에도 있어야 한다.
    assert plugin.appLookup.get("messenger") == 0
    assert plugin.windowLookup.get("대화창제목") == 0
