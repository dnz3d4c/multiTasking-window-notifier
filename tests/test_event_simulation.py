# -*- coding: utf-8 -*-
"""event_gainFocus / event_nameChange end-to-end 시나리오.

Phase 2/3까지는 각 레이어(focusDispatcher/matcher/nameChangeWatcher/store)를
독립 단위 테스트로만 검증했다. 본 파일은 실제 진입점(`dispatch`/`handle`)부터
matcher를 거쳐 `store.record_switch`와 `beepPlayer.play_beep`까지 한 번에
흐르는지를 확인한다.

시나리오:
    1. Alt+Tab 오버레이 → 창 매치 비프 + record_switch
    2. Ctrl+Tab editor 분기 → 창 매치 + tab_sig 전파
    3. Ctrl+Tab overlay 분기 (Notepad++ MRU 형태)
    4. event_nameChange 확정 전환 → 비프
    5. 연속 동일 전환 dedup (같은 event_sig면 skip)
    6. 자식 컨트롤 재진입 (hwnd 동일) → 동일 sig로 2회 째 skip

beepPlayer/store.record_switch는 모듈 속성 monkeypatch로 감지한다 — matcher가
호출 시점에 속성을 lookup하므로 가능.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest
from configobj import ConfigObj

from globalPlugins.multiTaskingWindowNotifier import (
    focusDispatcher,
    foregroundWatcher,
    nameChangeWatcher,
    store,
)
from globalPlugins.multiTaskingWindowNotifier.constants import (
    ALT_TAB_HOST_FG_WCN,
    ALT_TAB_OVERLAY_WCN,
    SCOPE_APP,
    SCOPE_WINDOW,
)


@pytest.fixture
def plugin(monkeypatch, tmp_path):
    """GlobalPlugin 부팅 + seed + 비프/레코드 캡처 인프라."""
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


@pytest.fixture
def seeded_plugin(plugin):
    """메모장/Notepad++/Chrome 창을 등록 + lookup 재구성."""
    keys = [
        "notepad|제목 없음",
        "notepad++|main.cpp",
        "chrome|YouTube",
    ]
    scopes = {k: SCOPE_WINDOW for k in keys}
    store.save(plugin.appListFile, keys, scopes=scopes)
    plugin.appList = list(keys)
    plugin._rebuild_lookup()
    return plugin


@pytest.fixture
def beep_calls(monkeypatch):
    from globalPlugins.multiTaskingWindowNotifier import beepPlayer

    calls = []
    monkeypatch.setattr(
        beepPlayer, "play_beep",
        lambda app_idx, tab_idx=None, scope=None, **kw: calls.append((app_idx, tab_idx, scope)),
    )
    return calls


@pytest.fixture
def record_calls(monkeypatch):
    """store.record_switch 호출 감지. matcher가 모듈 속성으로 참조하므로
    store 모듈 자체에 monkeypatch (matcher는 `from . import store` 사용)."""
    calls = []
    monkeypatch.setattr(
        store, "record_switch",
        lambda path, key: calls.append(key),
    )
    return calls


@pytest.fixture
def quiet_api(monkeypatch):
    """getForegroundObject 주입 헬퍼."""
    state = {"fg": None}
    monkeypatch.setattr(focusDispatcher.api, "getForegroundObject", lambda: state["fg"])
    return state


@pytest.fixture(autouse=True)
def _silence_debug(monkeypatch):
    monkeypatch.setattr(focusDispatcher.settings, "get", lambda key: False)
    monkeypatch.setattr(focusDispatcher.tabClasses, "is_overlay_class", lambda a, w: False)
    monkeypatch.setattr(focusDispatcher.tabClasses, "is_editor_class", lambda a, w: False)


def _obj(wcn="", name="", hwnd=0x1000, appName=""):
    o = MagicMock()
    o.windowClassName = wcn
    o.name = name
    o.windowHandle = hwnd
    o.appModule = MagicMock()
    o.appModule.appName = appName
    return o


def test_alt_tab_overlay_fires_beep_and_record(
    seeded_plugin, beep_calls, record_calls, quiet_api
):
    """Alt+Tab 오버레이 → 창 매치 → 비프 + record_switch(notepad|제목 없음)."""
    obj = _obj(wcn=ALT_TAB_OVERLAY_WCN, name="제목 없음 - 메모장", hwnd=0xAAA)
    fg = _obj(wcn=ALT_TAB_HOST_FG_WCN, name="작업 전환", hwnd=0xBBB)
    quiet_api["fg"] = fg

    focusDispatcher.dispatch(seeded_plugin, obj)

    assert len(beep_calls) == 1
    assert record_calls == ["notepad|제목 없음"]


def test_editor_branch_fires_beep_with_child_hwnd(
    seeded_plugin, beep_calls, record_calls, quiet_api, monkeypatch
):
    """Ctrl+Tab editor 분기 — fg.name을 제목으로, 자식 hwnd를 tab_sig로."""
    obj = _obj(wcn="RichEditD2DPT", hwnd=0xE001, appName="notepad")
    fg = _obj(wcn="Notepad", name="제목 없음 - 메모장", hwnd=0xF001, appName="notepad")
    quiet_api["fg"] = fg
    monkeypatch.setattr(
        focusDispatcher.tabClasses, "is_editor_class",
        lambda appId, wcn: appId == "notepad" and wcn == "RichEditD2DPT",
    )

    focusDispatcher.dispatch(seeded_plugin, obj)

    assert len(beep_calls) == 1
    assert record_calls == ["notepad|제목 없음"]


def test_app_overlay_branch_fires_beep(
    seeded_plugin, beep_calls, record_calls, quiet_api, monkeypatch
):
    """Notepad++ MRU 오버레이: fg_wcn이 overlay 목록이면 obj.name을 제목으로."""
    obj = _obj(wcn="SysListView32", name="main.cpp", hwnd=0xC001, appName="notepad++")
    fg = _obj(wcn="#32770", name="MRU", hwnd=0xC000, appName="notepad++")
    quiet_api["fg"] = fg
    monkeypatch.setattr(
        focusDispatcher.tabClasses, "is_overlay_class",
        lambda appId, wcn: appId == "notepad++" and wcn == "#32770",
    )

    focusDispatcher.dispatch(seeded_plugin, obj)

    assert len(beep_calls) == 1
    assert record_calls == ["notepad++|main.cpp"]


def test_name_change_fires_beep_on_confirmed_tab(
    seeded_plugin, beep_calls, record_calls, monkeypatch
):
    """event_nameChange로 title이 바뀌어 들어오면 매칭 + 비프."""
    fg = _obj(wcn="Chrome_WidgetWin_1", name="YouTube - Chrome", hwnd=0x7777, appName="chrome")
    # 최상위 foreground와 nameChange의 obj가 같은 상황(확정 탭 전환)
    monkeypatch.setattr(nameChangeWatcher.api, "getForegroundObject", lambda: fg)

    nameChangeWatcher.handle(seeded_plugin, fg)

    assert len(beep_calls) == 1
    assert record_calls == ["chrome|YouTube"]


def test_consecutive_identical_events_are_deduped(
    seeded_plugin, beep_calls, record_calls, quiet_api
):
    """같은 (appId, title, tab_sig) 연속 발생 → 첫 이벤트만 울리고 두 번째 skip."""
    obj = _obj(wcn=ALT_TAB_OVERLAY_WCN, name="제목 없음 - 메모장", hwnd=0xAAA)
    fg = _obj(wcn=ALT_TAB_HOST_FG_WCN, name="작업 전환", hwnd=0xBBB)
    quiet_api["fg"] = fg

    focusDispatcher.dispatch(seeded_plugin, obj)
    focusDispatcher.dispatch(seeded_plugin, obj)

    assert len(beep_calls) == 1
    assert record_calls == ["notepad|제목 없음"]


def test_app_scope_fallback_beep(
    plugin, beep_calls, record_calls, quiet_api
):
    """SCOPE_APP 등록만 있고 창 매치가 없을 때 appLookup fallback으로 단음.

    Alt+Tab 분기는 appId를 빈 문자열로 넘겨 appLookup을 막지만, overlay/editor
    분기가 아닌 일반 포커스 이동으로 scope=app 매치가 되는 케이스는
    nameChangeWatcher 경로가 담당한다. 여기선 nameChange handle이 app 매치를
    단음으로 울리는지 확인 (tab_idx=None 폴백).
    """
    keys = ["chrome"]
    scopes = {"chrome": SCOPE_APP}
    store.save(plugin.appListFile, keys, scopes=scopes)
    plugin.appList = list(keys)
    plugin._rebuild_lookup()

    fg = _obj(wcn="Chrome_WidgetWin_1", name="Some page - Chrome",
              hwnd=0x9999, appName="chrome")
    import sys as _sys
    _sys.modules["api"].getForegroundObject = lambda: fg

    nameChangeWatcher.handle(plugin, fg)

    # scope=app: (app_idx, None, SCOPE_APP) 단음
    assert len(beep_calls) == 1
    assert beep_calls[0][1] is None  # tab_idx=None
    assert beep_calls[0][2] == SCOPE_APP
    assert record_calls == ["chrome"]


def test_child_control_reentry_does_not_double_beep(
    seeded_plugin, beep_calls, record_calls, quiet_api, monkeypatch
):
    """editor 분기 활성 상태에서 같은 hwnd로 포커스가 두 번 들어와도 1회만.

    자식 컨트롤을 클릭하거나 포커스 이동해도 sig(appId, title, hwnd)가 동일이면
    dedup으로 skip — Matcher.last_event_sig 가드.
    """
    obj = _obj(wcn="RichEditD2DPT", hwnd=0xE001, appName="notepad")
    fg = _obj(wcn="Notepad", name="제목 없음 - 메모장", hwnd=0xF001, appName="notepad")
    quiet_api["fg"] = fg
    monkeypatch.setattr(
        focusDispatcher.tabClasses, "is_editor_class",
        lambda appId, wcn: appId == "notepad" and wcn == "RichEditD2DPT",
    )

    focusDispatcher.dispatch(seeded_plugin, obj)
    focusDispatcher.dispatch(seeded_plugin, obj)

    assert len(beep_calls) == 1
    assert len(record_calls) == 1


# ---------------- Phase 7: event_foreground 회귀 그물 ----------------
# foregroundWatcher.handle은 NVDA가 event_foreground를 발화한 시점에 호출되며
# obj는 새 foreground 본체다. 같은 fg hwnd 내부 포커스 이동에는 NVDA가 발화
# 자체를 안 하므로 dedup은 NVDA 책임. 우리 모듈은 호출만 들어오면 무조건
# matcher로 위임한다 — 이 점을 테스트 시 가정.


def test_event_foreground_fires_app_scope_beep_for_unmapped_app(
    plugin, beep_calls, record_calls
):
    """SCOPE_APP만 등록된 앱(예: Spotify)으로 foreground 전환 시 단음 발화.

    focusDispatcher 3분기는 모두 미스이지만 foregroundWatcher가 직접
    matcher로 위임 → app_lookup hit → SCOPE_APP 단음. 이게 막힌 게 Phase 7
    이전의 핵심 버그였다.
    """
    keys = ["spotify"]
    scopes = {"spotify": SCOPE_APP}
    store.save(plugin.appListFile, keys, scopes=scopes)
    plugin.appList = list(keys)
    plugin._rebuild_lookup()

    fg = _obj(wcn="Chrome_WidgetWin_1", name="Spotify Premium",
              hwnd=0x9001, appName="spotify")

    foregroundWatcher.handle(plugin, fg)

    assert len(beep_calls) == 1
    assert beep_calls[0][1] is None  # tab_idx=None (단음)
    assert beep_calls[0][2] == SCOPE_APP
    assert record_calls == ["spotify"]


def test_event_foreground_window_match_takes_priority_over_app(
    plugin, beep_calls, record_calls
):
    """KakaoTalk 같이 SCOPE_APP + SCOPE_WINDOW 혼합 등록 시 창 정확 매치 우선.

    matcher의 우선순위는 window 정확 → window title-only → app_lookup.
    동일 fg.name이 window 키와 정확 일치하면 SCOPE_WINDOW 비프(2음).
    SCOPE_APP fallback은 발화 안 함.
    """
    keys = ["kakaotalk", "kakaotalk|메인 채팅"]
    scopes = {"kakaotalk": SCOPE_APP, "kakaotalk|메인 채팅": SCOPE_WINDOW}
    store.save(plugin.appListFile, keys, scopes=scopes)
    plugin.appList = list(keys)
    plugin._rebuild_lookup()

    fg = _obj(wcn="EVA_Window_Dblclk", name="메인 채팅",
              hwnd=0xA001, appName="kakaotalk")

    foregroundWatcher.handle(plugin, fg)

    assert len(beep_calls) == 1
    assert beep_calls[0][2] == SCOPE_WINDOW
    assert record_calls == ["kakaotalk|메인 채팅"]


def test_event_foreground_unregistered_app_no_beep(
    seeded_plugin, beep_calls, record_calls
):
    """등록 안 된 앱으로 foreground 전환 시 무음. matcher miss로 자연 종료."""
    fg = _obj(wcn="UnknownApp", name="Some Random Window",
              hwnd=0xB001, appName="unknownapp")

    foregroundWatcher.handle(seeded_plugin, fg)

    assert beep_calls == []
    assert record_calls == []


def test_alt_tab_overlay_then_foreground_both_fire(
    plugin, beep_calls, record_calls, quiet_api
):
    """Alt+Tab 도중 분기 1(미리듣기) + 릴리스 후 event_foreground(본 비프) 양쪽 발화.

    두 이벤트는 서로 다른 sig — 분기 1은 (appId='', title=norm, hwnd=overlay),
    foregroundWatcher는 (appId=실제, title=norm, hwnd=fg) — 이라 sig dedup이
    흡수하지 않고 의도된 2회로 분리된다(탐색 단계 + 확정 단계).
    """
    keys = ["spotify"]
    scopes = {"spotify": SCOPE_APP}
    store.save(plugin.appListFile, keys, scopes=scopes)
    plugin.appList = list(keys)
    plugin._rebuild_lookup()
    # window_lookup에도 title-only로 미리듣기가 잡히도록 SCOPE_WINDOW 별도 추가.
    keys = ["spotify", "spotify|Spotify Premium"]
    scopes = {"spotify": SCOPE_APP, "spotify|Spotify Premium": SCOPE_WINDOW}
    store.save(plugin.appListFile, keys, scopes=scopes)
    plugin.appList = list(keys)
    plugin._rebuild_lookup()

    # 1) Alt+Tab 오버레이 미리듣기 (분기 1)
    overlay = _obj(wcn=ALT_TAB_OVERLAY_WCN, name="Spotify Premium",
                   hwnd=0xCAFE, appName="explorer")
    overlay_fg = _obj(wcn=ALT_TAB_HOST_FG_WCN, name="작업 전환",
                      hwnd=0xBEEF, appName="explorer")
    quiet_api["fg"] = overlay_fg
    focusDispatcher.dispatch(plugin, overlay)

    # 2) Alt 릴리스 후 실제 foreground 전환 (foregroundWatcher)
    real_fg = _obj(wcn="Chrome_WidgetWin_1", name="Spotify Premium",
                   hwnd=0x9001, appName="spotify")
    foregroundWatcher.handle(plugin, real_fg)

    # 양쪽 다 발화 — 미리듣기(window 매치) + 본 비프(window 매치, 다른 hwnd)
    assert len(beep_calls) == 2
    assert len(record_calls) == 2
