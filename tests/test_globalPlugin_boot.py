# -*- coding: utf-8 -*-
"""GlobalPlugin이 "빈 nvda.ini + 빈 등록 목록" 상태에서 부팅 + 이벤트 처리를
예외 없이 끝내는지 검증.

회귀 시나리오: register()가 defaults를 주입하지 않던 시절에는
event_gainFocus 안의 settings.get("enableAllWindows")가 KeyError를 던졌고,
외곽 except가 이걸 조용히 삼켜서 비프가 사라졌다. 이 스모크는 빈 설정
상황에서도 이벤트 핸들러가 정상 경로(nextHandler 호출)를 완주하는지
보장해, 같은 회귀가 다시 들어왔을 때 곧바로 실패하게 한다.
"""

from __future__ import annotations

import types
from unittest.mock import MagicMock

import pytest
from configobj import ConfigObj


ADDON_KEY = "multiTaskingWindowNotifier"


@pytest.fixture
def booted_plugin(monkeypatch, tmp_path):
    """빈 config + 빈 애드온 디렉토리에서 GlobalPlugin을 최소 부팅해 반환.

    settings/settingsPanel 둘 다 모듈 수준 `config` 바인딩을 같은 가짜로
    교체해야 `config.conf[X][key]` 경로가 실제 ConfigObj로 연결된다.
    """
    from globalPlugins.multiTaskingWindowNotifier import settings, settingsPanel

    conf = ConfigObj()
    conf.spec = {}
    fake_config = types.ModuleType("config")
    fake_config.conf = conf

    monkeypatch.setattr(settings, "config", fake_config)
    monkeypatch.setattr(settingsPanel, "config", fake_config)

    # 사용자 실제 nvda 경로가 아닌 tmp_path를 쓰도록 conftest autouse fixture가
    # 이미 globalVars.appArgs.configPath를 바꿔둔다. 여기서는 방어적으로 재확인.
    import sys

    sys.modules["globalVars"].appArgs.configPath = str(tmp_path)

    from globalPlugins.multiTaskingWindowNotifier import GlobalPlugin

    plugin = GlobalPlugin()
    return plugin, conf


def test_boot_creates_config_defaults(booted_plugin):
    """GlobalPlugin.__init__이 register()를 타고 섹션/기본값을 만든다."""
    _plugin, conf = booted_plugin

    assert ADDON_KEY in conf
    assert conf[ADDON_KEY]["beepDuration"] == 100
    assert conf[ADDON_KEY]["enableAllWindows"] is False


def test_event_gain_focus_survives_empty_state(booted_plugin):
    """빈 등록 목록 + 빈 포커스 객체에서 event_gainFocus가 예외 없이 완주."""
    plugin, _conf = booted_plugin

    focus = MagicMock()
    focus.windowClassName = "ArbitraryClass"
    focus.name = ""
    focus.appModule = MagicMock()
    focus.appModule.appName = "someapp"

    import api

    api.getFocusObject.return_value = focus

    called = []

    def nextHandler():
        called.append(True)

    plugin.event_gainFocus(focus, nextHandler)

    # 핵심 불변식: 본 애드온에서 어떤 일이 일어나든 NVDA 이벤트 체인이
    # 끊기면 안 된다. nextHandler는 반드시 정확히 한 번 호출되어야 한다.
    assert called == [True]


def test_event_gain_focus_survives_when_config_section_wiped(booted_plugin, monkeypatch):
    """섹션이 사라진 상태에서도 KeyError가 event_gainFocus 외부로 새지 않는다.

    프로필 전환이나 사용자의 수동 nvda.ini 편집 같은 경계 상황에 대한
    안전망. settings.get의 폴백이 실제로 작동하는지 실증.
    """
    plugin, conf = booted_plugin

    # 섹션을 통째로 제거해 KeyError 조건 재현
    del conf[ADDON_KEY]

    focus = MagicMock()
    focus.windowClassName = "Windows.UI.Input.InputSite.WindowClass"
    focus.name = "테스트 창"
    focus.appModule = MagicMock()
    focus.appModule.appName = "testapp"

    import api

    api.getFocusObject.return_value = focus

    called = []

    def nextHandler():
        called.append(True)

    plugin.event_gainFocus(focus, nextHandler)

    assert called == [True]
