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
    from globalPlugins.multiTaskingWindowNotifier import beepPlayer

    calls = []

    def fake(app_idx, tab_idx=None, scope=None, **kwargs):
        calls.append((app_idx, tab_idx, scope))

    # matcher가 호출 시점에 beepPlayer.play_beep를 lookup하므로
    # 모듈 속성 교체만으로 캡처 가능.
    monkeypatch.setattr(beepPlayer, "play_beep", fake)
    return calls


def _seed(plugin, items):
    """디스크에 (key, scope) 리스트로 등록 후 메모리 동기화."""
    keys = [k for k, _ in items]
    scopes = {k: s for k, s in items}
    appListStore.save(plugin.appListFile, keys, scopes=scopes)
    plugin.appList = list(keys)
    plugin._rebuild_lookup()


def test_window_match_wins_over_app_match(plugin, monkeypatch):
    """창 + 앱이 동시 등록일 때 창 매치가 우선. v4+: (app_idx, tab_idx, scope)."""
    from globalPlugins.multiTaskingWindowNotifier.constants import BEEP_USABLE_START

    _seed(plugin, [
        ("chrome", SCOPE_APP),
        ("chrome|YouTube", SCOPE_WINDOW),
    ])
    calls = _capture_beeps(monkeypatch)

    plugin._match_and_beep("chrome", "YouTube")

    # appBeepMap[chrome]=BEEP_USABLE_START (첫 할당), 첫 window tabBeepIdx도 동일.
    assert calls == [(BEEP_USABLE_START, BEEP_USABLE_START, SCOPE_WINDOW)]


def test_app_match_used_as_fallback(plugin, monkeypatch):
    """창 매치가 없으면 앱 매치로 fallback. scope=app은 tab_idx=None 단음."""
    from globalPlugins.multiTaskingWindowNotifier.constants import BEEP_USABLE_START

    _seed(plugin, [
        ("chrome", SCOPE_APP),
    ])
    calls = _capture_beeps(monkeypatch)

    plugin._match_and_beep("chrome", "어떤 탭이든")

    # appBeepMap[chrome]=BEEP_USABLE_START, scope=app이므로 tab_idx=None
    assert calls == [(BEEP_USABLE_START, None, SCOPE_APP)]


def test_window_tab_beep_is_distinct_per_window(plugin, monkeypatch):
    """같은 appId 내 서로 다른 window는 서로 다른 tabBeepIdx를 받는다."""
    from globalPlugins.multiTaskingWindowNotifier.constants import BEEP_USABLE_START

    _seed(plugin, [
        ("chrome", SCOPE_APP),                # appBeepMap[chrome]=START (첫 앱)
        ("chrome|Tab A", SCOPE_WINDOW),       # chrome 첫 window → tabBeepIdx=START
        ("notepad|Memo", SCOPE_WINDOW),       # 두 번째 앱 → appBeepMap[notepad]=START+1
        ("chrome|Tab B", SCOPE_WINDOW),       # chrome 두 번째 window → tabBeepIdx=START+1
    ])
    calls = _capture_beeps(monkeypatch)

    plugin._match_and_beep("chrome", "Tab A")
    # 중복 가드 회피용 — 시간 + 시그니처 모두 리셋.
    plugin._last_matched_ts = 0.0
    plugin._last_event_sig = None
    plugin._match_and_beep("chrome", "Tab B")

    # Tab A / Tab B 모두 chrome 앱 비프 공유(app_idx=START),
    # 탭 비프는 앱 내 순차로 분리 (0, 1).
    assert calls == [
        (BEEP_USABLE_START, BEEP_USABLE_START, SCOPE_WINDOW),
        (BEEP_USABLE_START, BEEP_USABLE_START + 1, SCOPE_WINDOW),
    ]


def test_window_without_app_entry_still_has_app_beep(plugin, monkeypatch):
    """scope=app entry가 없어도 appBeepMap은 자동 할당되어 app_idx 확보."""
    from globalPlugins.multiTaskingWindowNotifier.constants import BEEP_USABLE_START

    _seed(plugin, [
        ("notepad|Memo A", SCOPE_WINDOW),  # appBeepMap[notepad]=START, tabBeepIdx=START
        ("chrome|YouTube", SCOPE_WINDOW),  # appBeepMap[chrome]=START+1, tabBeepIdx=START
        ("notepad|Memo B", SCOPE_WINDOW),  # notepad 두 번째 → tabBeepIdx=START+1
    ])
    calls = _capture_beeps(monkeypatch)

    plugin._match_and_beep("notepad", "Memo B")

    # notepad는 app entry 없이도 appBeepMap에 등록되어 app_idx=BEEP_USABLE_START.
    # Memo B는 notepad 두 번째 window라 tabBeepIdx=START+1.
    assert calls == [(BEEP_USABLE_START, BEEP_USABLE_START + 1, SCOPE_WINDOW)]


def test_dedup_guard_suppresses_consecutive_match(plugin, monkeypatch):
    """같은 키가 _MATCH_DEDUP_SEC 이내 재매칭되면 비프가 한 번만 발사."""
    _seed(plugin, [("chrome|YouTube", SCOPE_WINDOW)])
    calls = _capture_beeps(monkeypatch)

    plugin._match_and_beep("chrome", "YouTube")
    plugin._match_and_beep("chrome", "YouTube")  # 즉시 재호출
    plugin._match_and_beep("chrome", "YouTube")

    assert len(calls) == 1


def test_dedup_guard_resets_after_window(plugin, monkeypatch):
    """시간 가드와 시그니처 가드 둘 다 풀리면 재매칭이 다시 발사된다.

    실전에선 사용자가 다른 앱으로 전환했다가 돌아오는 시나리오가
    여기에 해당. 다른 매칭이 끼어들면 _last_event_sig가 자연 갱신된다.
    단위 테스트에선 두 상태를 직접 리셋.
    """
    _seed(plugin, [("chrome|YouTube", SCOPE_WINDOW)])
    calls = _capture_beeps(monkeypatch)

    plugin._match_and_beep("chrome", "YouTube")
    plugin._last_matched_ts = 0.0  # 시간 가드 리셋
    plugin._last_event_sig = None  # 시그니처 가드 리셋 (복귀 시나리오 모사)
    plugin._match_and_beep("chrome", "YouTube")

    assert len(calls) == 2


def test_signature_dedup_blocks_same_hwnd_reentry(plugin, monkeypatch):
    """같은 (appId, title, tab_sig) 재진입은 시간 가드 외에서도 시그니처로 억제.

    메모장 한 탭에 머무는 동안 editor 분기가 0.1초 이상 간격으로 재발동하는
    상황 모사 — 동일 자식 컨트롤 hwnd라 sig가 동일.
    """
    _seed(plugin, [("notepad|제목 없음", SCOPE_WINDOW)])
    calls = _capture_beeps(monkeypatch)

    plugin._match_and_beep("notepad", "제목 없음", tab_sig=0x1001)
    # 시간 가드는 풀어주지만 시그니처는 그대로 → 여전히 skip
    plugin._last_matched_ts = 0.0
    plugin._match_and_beep("notepad", "제목 없음", tab_sig=0x1001)
    plugin._last_matched_ts = 0.0
    plugin._match_and_beep("notepad", "제목 없음", tab_sig=0x1001)

    assert len(calls) == 1


def test_signature_dedup_allows_different_hwnd_same_title(plugin, monkeypatch):
    """같은 (appId, title)이라도 tab_sig(hwnd)가 다르면 매 전환마다 발화.

    메모장에서 "제목 없음" 탭 여러 개를 Ctrl+Tab으로 순회하는 시나리오 — 탭마다
    자식 컨트롤 hwnd가 다르므로 sig가 달라진다. 본 플랜의 핵심 회귀 방지 케이스.
    """
    from globalPlugins.multiTaskingWindowNotifier.constants import BEEP_USABLE_START

    _seed(plugin, [("notepad|제목 없음", SCOPE_WINDOW)])
    calls = _capture_beeps(monkeypatch)

    plugin._match_and_beep("notepad", "제목 없음", tab_sig=0x1001)
    plugin._last_matched_ts = 0.0  # 시간 가드 리셋 (시그니처 가드만 검증)
    plugin._match_and_beep("notepad", "제목 없음", tab_sig=0x1002)
    plugin._last_matched_ts = 0.0
    plugin._match_and_beep("notepad", "제목 없음", tab_sig=0x1003)

    # 같은 entry를 공유하므로 3회 모두 같은 (app_idx, tab_idx) — 다만 호출은 3회 실행.
    assert len(calls) == 3
    assert all(c == (BEEP_USABLE_START, BEEP_USABLE_START, SCOPE_WINDOW) for c in calls)


def test_signature_dedup_allows_different_title(plugin, monkeypatch):
    """시그니처 dedup은 title이 바뀌면 통과시킨다 (Ctrl+Tab 실제 전환)."""
    from globalPlugins.multiTaskingWindowNotifier.constants import BEEP_USABLE_START

    _seed(plugin, [
        ("notepad|파일 A", SCOPE_WINDOW),
        ("notepad|파일 B", SCOPE_WINDOW),
    ])
    calls = _capture_beeps(monkeypatch)

    plugin._match_and_beep("notepad", "파일 A")
    # 시간 가드는 자연 경과 가정. title이 다르므로 시그니처 가드도 통과.
    plugin._last_matched_ts = 0.0
    plugin._match_and_beep("notepad", "파일 B")

    # 앱 내 순차: 파일 A tabBeepIdx=START, 파일 B tabBeepIdx=START+1.
    assert calls == [
        (BEEP_USABLE_START, BEEP_USABLE_START, SCOPE_WINDOW),
        (BEEP_USABLE_START, BEEP_USABLE_START + 1, SCOPE_WINDOW),
    ]


def test_no_match_is_silent(plugin, monkeypatch):
    """등록 안 된 (appId, title)은 무음."""
    _seed(plugin, [("chrome|YouTube", SCOPE_WINDOW)])
    calls = _capture_beeps(monkeypatch)

    plugin._match_and_beep("notepad", "missing")

    assert calls == []


def test_title_only_reverse_mapping_uses_real_app_beep(plugin, monkeypatch):
    """title 역매핑 매치 시 entry의 real appId로 appBeepMap을 조회."""
    from globalPlugins.multiTaskingWindowNotifier.constants import BEEP_USABLE_START

    _seed(plugin, [("notepad|Memo", SCOPE_WINDOW)])
    calls = _capture_beeps(monkeypatch)

    # 호출 인자 appId='explorer'(Alt+Tab 오버레이)지만 matched_key의 real appId는 notepad.
    plugin._match_and_beep("explorer", "Memo")

    assert calls == [(BEEP_USABLE_START, BEEP_USABLE_START, SCOPE_WINDOW)]
    # 메타가 정확히 "notepad|Memo" entry에 기록되었는지 확인
    meta = appListStore.get_meta(plugin.appListFile, "notepad|Memo")
    assert meta["switchCount"] == 1
