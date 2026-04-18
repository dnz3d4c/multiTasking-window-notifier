# -*- coding: utf-8 -*-
"""_rebuild_lookup의 title 역매핑 동작 가드.

회귀 시나리오:
    Phase 2에서 신형 복합키(`appId|title`) 포맷을 도입한 이후, 기존의 title-only
    fallback이 event_gainFocus에서 더 이상 작동하지 않았다. Alt+Tab 오버레이의
    포커스 객체는 appId가 `explorer`/`windowsterminal`로 찍혀 복합키 정확 매치가
    영구 불가능하고, lookup에 title 컴포넌트가 들어있지 않으니 title fallback도
    miss. 결과: 신형 키로 저장된 창은 Alt+Tab에서 비프가 나지 않았다.

    본 테스트는 _rebuild_lookup이 복합키 entry의 title을 역매핑해두는지, 그리고
    그 덕에 Alt+Tab 오버레이 경로(appId='explorer')에서도 event_gainFocus가
    비프 함수를 호출하는지 직접 검증한다.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest
from configobj import ConfigObj


ADDON_KEY = "multiTaskingWindowNotifier"


@pytest.fixture
def plugin(monkeypatch, tmp_path):
    """settings/settingsPanel 바인딩을 실제 ConfigObj로 묶은 뒤 GlobalPlugin 부팅."""
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


def test_composite_entry_title_is_reverse_mapped(plugin):
    """복합키 entry의 title 컴포넌트가 windowLookup에 같은 idx로 추가된다."""
    plugin.appList = ["notepad|제목 없음 - 메모장"]
    plugin._rebuild_lookup()

    assert plugin.windowLookup["notepad|제목 없음 - 메모장"] == 0
    assert plugin.windowLookup["제목 없음 - 메모장"] == 0
    # 메타 미주입 상태에서는 SCOPE_WINDOW로 fallback → appLookup은 비어있음
    assert plugin.appLookup == {}


def test_legacy_entry_creates_single_mapping(plugin):
    """구형 title-only entry는 역매핑 중복 없이 한 번만 windowLookup에 등록된다."""
    plugin.appList = ["Steam"]
    plugin._rebuild_lookup()

    assert plugin.windowLookup == {"Steam": 0}


def test_title_collision_keeps_first_registered(plugin):
    """같은 title을 가진 복합키가 여럿이면 먼저 등록된 idx가 title을 선점."""
    plugin.appList = [
        "notepad|제목 없음 - 메모장",
        "otherapp|제목 없음 - 메모장",
    ]
    plugin._rebuild_lookup()

    assert plugin.windowLookup["notepad|제목 없음 - 메모장"] == 0
    assert plugin.windowLookup["otherapp|제목 없음 - 메모장"] == 1
    # title 역매핑은 setdefault로 먼저 등록된 idx 유지
    assert plugin.windowLookup["제목 없음 - 메모장"] == 0


def test_alt_tab_overlay_triggers_beep_via_title_fallback(plugin, monkeypatch):
    """실측 재현: Alt+Tab 오버레이(appId='explorer')에서 obj가 들고 온 raw title
    (" - 메모장" 서픽스 포함)이 normalize_title을 거쳐 복합키 entry의 정규화된
    title과 일치하면, title 역매핑 덕에 match 성공 + 비프 발사.

    Phase 2 회귀 당시엔 여기서 matched=None이 되어 조용히 빠져나갔다.
    Phase B(normalize_title 도입) 이후에는 appList의 title이 정규화 형태
    ("제목 없음")로 저장되며, Alt+Tab obj.name의 raw 서픽스는 event_gainFocus
    의 normalize_title 적용으로 흡수된다.
    """
    # 정규화 마이그레이션 후 실측 디스크 상태를 모사 (꼬리 " - 메모장" 없음).
    plugin.appList = ["notepad|제목 없음"]
    plugin._rebuild_lookup()

    focus = MagicMock()
    focus.windowClassName = "Windows.UI.Input.InputSite.WindowClass"
    # Alt+Tab obj는 윈도우 타이틀바의 raw 문자열을 그대로 들고 온다.
    focus.name = "제목 없음 - 메모장"
    focus.appModule = MagicMock()
    # Alt+Tab 오버레이의 전형적 appName. 대상 앱(notepad)과 다르다.
    focus.appModule.appName = "explorer"

    import api

    api.getFocusObject.return_value = focus

    from globalPlugins.multiTaskingWindowNotifier import beepPlayer

    called = []

    def fake_beep(app_idx, tab_idx=None, scope=None, **kwargs):
        called.append((app_idx, tab_idx, scope))

    # matcher가 호출 시점에 beepPlayer.play_beep를 lookup하므로 모듈 속성
    # 교체로 가로챈다.
    monkeypatch.setattr(beepPlayer, "play_beep", fake_beep)

    plugin.event_gainFocus(focus, lambda: None)

    # v6 순차 할당: appBeepMap[notepad]=0 (첫 앱), 첫 window tabBeepIdx=0, scope=window.
    assert called == [(0, 0, "window")], f"비프 호출 누락: got={called}"
