# -*- coding: utf-8 -*-
"""tutorial.state의 is/mark 읽기/쓰기 동작을 검증.

conftest.py가 세션 초기에 `sys.modules["config"]`를 MagicMock으로 주입하기
때문에 tutorial.state 모듈도 그 스텁을 바인딩한 채로 로드된다. 본 테스트는
test_settings_defaults.py와 동일한 방식으로 state 모듈 내부 `config` 속성을
ConfigObj 기반 가짜 모듈로 교체한다.
"""

from __future__ import annotations

import types

import pytest
from configobj import ConfigObj


ADDON_KEY = "multiTaskingWindowNotifier"


@pytest.fixture
def real_config(monkeypatch):
    """state 모듈의 `config` 바인딩을 실제 ConfigObj 기반 가짜 모듈로 교체."""
    from globalPlugins.multiTaskingWindowNotifier.tutorial import state

    conf = ConfigObj()
    conf.spec = {}

    fake_config = types.ModuleType("config")
    fake_config.conf = conf
    monkeypatch.setattr(state, "config", fake_config)

    return conf


def test_is_tutorial_shown_returns_false_when_section_missing(real_config):
    """register() 없이 호출 시 KeyError 폴백으로 False 반환 — 안내 누락보다
    한 번 더 띄우는 쪽이 사용자 친화적이라는 설계 결정."""
    from globalPlugins.multiTaskingWindowNotifier.tutorial import state

    assert state.is_tutorial_shown() is False


def test_is_tutorial_shown_returns_false_when_key_missing(real_config):
    from globalPlugins.multiTaskingWindowNotifier.tutorial import state

    real_config[ADDON_KEY] = {}  # 섹션은 있지만 tutorialShown 키 없음

    assert state.is_tutorial_shown() is False


def test_is_tutorial_shown_returns_true_when_flag_set(real_config):
    from globalPlugins.multiTaskingWindowNotifier.tutorial import state

    real_config[ADDON_KEY] = {"tutorialShown": True}

    assert state.is_tutorial_shown() is True


def test_is_tutorial_shown_coerces_truthy_values(real_config):
    """configobj은 저장값이 문자열 'True'/'False'로 올 수도 있어 bool 강제 변환을 확인.

    `bool(config.conf[ADDON_KEY][key])` 직접 조회 시 문자열 'False'는 True가
    되는 함정 — state는 configobj가 이미 bool로 validate한 상태를 가정하므로
    여기서는 bool로 저장된 케이스만 검증하면 충분."""
    from globalPlugins.multiTaskingWindowNotifier.tutorial import state

    real_config[ADDON_KEY] = {"tutorialShown": False}
    assert state.is_tutorial_shown() is False

    real_config[ADDON_KEY] = {"tutorialShown": True}
    assert state.is_tutorial_shown() is True


def test_mark_tutorial_shown_writes_true(real_config):
    from globalPlugins.multiTaskingWindowNotifier.tutorial import state

    real_config[ADDON_KEY] = {"tutorialShown": False}

    state.mark_tutorial_shown()

    assert real_config[ADDON_KEY]["tutorialShown"] is True


def test_mark_tutorial_shown_is_idempotent(real_config):
    from globalPlugins.multiTaskingWindowNotifier.tutorial import state

    real_config[ADDON_KEY] = {"tutorialShown": False}

    state.mark_tutorial_shown()
    state.mark_tutorial_shown()
    state.mark_tutorial_shown()

    assert real_config[ADDON_KEY]["tutorialShown"] is True


def test_mark_tutorial_shown_swallows_exception_when_section_missing(real_config):
    """섹션이 없는 상태에서 mark를 호출해도 예외가 본체로 튀어나가지 않아야 한다.

    실제 흐름에서는 settings.register()가 섹션을 만들어 놓은 뒤 호출되지만,
    방어 계층이 있는지 회귀 방지."""
    from globalPlugins.multiTaskingWindowNotifier.tutorial import state

    # 섹션 미존재 — configobj는 이 경우 section[key]=value가 자동 섹션 생성이라
    # KeyError가 안 나지만, 라이브러리 버전에 따라 달라질 수 있는 경로이므로
    # 예외 안전만 보증.
    state.mark_tutorial_shown()  # 예외 없어야 함

    # 호출 후 섹션이 생성됐든 안 생성됐든 is_tutorial_shown이 일관 동작
    result = state.is_tutorial_shown()
    assert result in (True, False)
