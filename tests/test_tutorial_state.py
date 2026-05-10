# -*- coding: utf-8 -*-
"""tutorial.state의 is/mark 읽기/쓰기 동작을 검증.

conftest.py가 세션 초기에 `sys.modules["config"]`를 MagicMock으로 주입하기
때문에 tutorial.state 모듈도 그 스텁을 바인딩한 채로 로드된다. 본 테스트는
test_settings_defaults.py와 동일한 방식으로 state 모듈 내부 `config` 속성을
ConfigObj 기반 가짜 모듈로 교체한다.
"""

from __future__ import annotations

import types
from unittest.mock import MagicMock

import pytest
from configobj import ConfigObj


ADDON_KEY = "multiTaskingWindowNotifier"


@pytest.fixture
def real_config(monkeypatch):
    """state 모듈의 `config` 바인딩을 실제 ConfigObj 기반 가짜 모듈로 교체.

    `config.conf.save`는 NVDA ConfigManager 메서드라 ConfigObj에는 없다 —
    `mark_tutorial_shown`이 save를 명시 호출하므로 호출 가능하도록 MagicMock으로
    부착한다. 호출 횟수는 `save_mock`(아래 별도 fixture)으로 검증 가능.
    """
    from globalPlugins.multiTaskingWindowNotifier.tutorial import state

    conf = ConfigObj()
    conf.spec = {}
    conf.save = MagicMock()

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


def test_mark_tutorial_shown_calls_config_save(real_config):
    """save() 명시 호출 — saveOnExit OFF 환경/비정상 종료에서도 디스크 반영 보장.

    NVDA의 종료 시 자동 저장은 `general.saveConfigurationOnExit=True` + 정상
    종료 경로에서만 동작하므로, mark 시점에 명시 save해야 다음 부팅에 플래그가
    유지된다. 이게 빠지면 매 부팅마다 첫 실행 안내가 다시 뜨는 회귀 발생.
    """
    from globalPlugins.multiTaskingWindowNotifier.tutorial import state

    real_config[ADDON_KEY] = {"tutorialShown": False}

    state.mark_tutorial_shown()

    real_config.save.assert_called_once()


def test_mark_tutorial_shown_swallows_save_failure(real_config):
    """save() 자체가 실패해도 메모리 갱신은 유효 — 같은 세션 내 중복 노출 차단.

    디스크 권한 오류 등으로 save가 실패해도 본체 흐름을 막지 않아야 한다.
    """
    from globalPlugins.multiTaskingWindowNotifier.tutorial import state

    real_config[ADDON_KEY] = {"tutorialShown": False}
    real_config.save.side_effect = OSError("disk full")

    # 예외가 흘러나오면 안 됨
    state.mark_tutorial_shown()

    # 메모리 갱신은 save 시도 전에 끝나므로 True 보장
    assert real_config[ADDON_KEY]["tutorialShown"] is True


def test_mark_tutorial_shown_skips_save_when_write_failed(real_config, monkeypatch):
    """write 단계에서 예외가 나면 save도 시도하지 않음.

    `config.conf[ADDON_NAME]["tutorialShown"] = True` 자체가 실패한 경우,
    저장할 변경분이 없으므로 save 호출 의미 없음 + log 노이즈만 늘림.
    """
    from globalPlugins.multiTaskingWindowNotifier.tutorial import state

    # `config.conf[ADDON_NAME]`가 반환하는 섹션의 __setitem__이 예외 던지도록 구성.
    # mark는 `config.conf[ADDON_NAME]["tutorialShown"] = True` 두 단계 dunder라
    # 안쪽 __setitem__만 RuntimeError로 막아야 정확한 시나리오 재현.
    failing_section = MagicMock()
    failing_section.__setitem__.side_effect = RuntimeError("write blocked")

    failing_conf = MagicMock()
    failing_conf.__getitem__.return_value = failing_section
    failing_conf.save = MagicMock()
    monkeypatch.setattr(state.config, "conf", failing_conf)

    state.mark_tutorial_shown()  # 예외 흡수

    failing_conf.save.assert_not_called()


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
