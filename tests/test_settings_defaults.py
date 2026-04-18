# -*- coding: utf-8 -*-
"""settings.register()가 live config에 기본값을 실제로 주입하는지,
그리고 settings.get()이 누락 시 CONFSPEC default로 폴백하는지 검증.

conftest.py가 기본으로 `config`를 MagicMock으로 스텁하기 때문에, 본 파일은
그 스텁을 실제 configobj.ConfigObj 기반 가짜 모듈로 교체한다. 실제 NVDA
런타임의 `config.conf`와 동일한 시맨틱(섹션 접근, dict 대입, KeyError
정책)을 재현하기 위함.

이 스모크가 있으면 Phase 1~3 통합 커밋처럼 "spec만 등록하고 defaults가
안 들어가서 KeyError가 터진" 회귀를 변경 시점에서 감지할 수 있다.
"""

from __future__ import annotations

import types

import pytest
from configobj import ConfigObj


ADDON_KEY = "multiTaskingWindowNotifier"


@pytest.fixture
def real_config(monkeypatch):
    """settings 모듈의 `config` 바인딩을 실제 ConfigObj 기반 가짜 모듈로 교체.

    conftest.py가 세션 초기에 `sys.modules["config"]`를 MagicMock으로 주입하고
    settings 모듈이 `import config`로 그 객체를 이미 바인딩해버렸기 때문에,
    `sys.modules["config"]`만 나중에 바꿔도 settings에는 영향이 없다. 그래서
    settings 모듈 자체의 `config` 속성을 직접 가짜 모듈로 교체한다.
    """
    from globalPlugins.multiTaskingWindowNotifier import settings

    conf = ConfigObj()
    # NVDA의 config.conf는 `.spec` dict-like 속성을 제공한다. ConfigObj 자체의
    # `configspec`과 분리된 NVDA 고유 인터페이스라 테스트에서도 단순 dict로 충분.
    conf.spec = {}

    fake_config = types.ModuleType("config")
    fake_config.conf = conf
    monkeypatch.setattr(settings, "config", fake_config)

    return conf


def test_register_creates_section_and_fills_defaults(real_config):
    from globalPlugins.multiTaskingWindowNotifier import settings

    assert ADDON_KEY not in real_config

    settings.register()

    assert ADDON_KEY in real_config
    section = real_config[ADDON_KEY]
    # v4: 2음 재생으로 duration 단축 + gap 신설. maxItems는 BEEP_TABLE과 디커플.
    # beepGapMs는 15→60→100으로 두 차례 상향. 60에서도 두 음이 한 덩어리로
    # 들린다는 피드백 후 100ms로 재조정.
    assert section["beepDuration"] == 50
    assert section["beepGapMs"] == 100
    assert section["beepVolumeLeft"] == 50
    assert section["beepVolumeRight"] == 50
    assert section["maxItems"] == 128


def test_register_preserves_user_values(real_config):
    from globalPlugins.multiTaskingWindowNotifier import settings

    settings.register()
    real_config[ADDON_KEY]["beepDuration"] = 123  # 사용자 오버라이드

    settings.register()  # 멱등 재호출

    assert real_config[ADDON_KEY]["beepDuration"] == 123


def test_get_returns_live_value(real_config):
    from globalPlugins.multiTaskingWindowNotifier import settings

    settings.register()
    real_config[ADDON_KEY]["beepDuration"] = 77

    assert settings.get("beepDuration") == 77


def test_get_fallback_when_section_missing(real_config):
    from globalPlugins.multiTaskingWindowNotifier import settings

    # register 없이 get 호출 — 섹션 부재 시 CONFSPEC default 폴백
    assert settings.get("beepDuration") == 50


def test_get_fallback_when_key_missing(real_config):
    from globalPlugins.multiTaskingWindowNotifier import settings

    settings.register()
    del real_config[ADDON_KEY]["beepVolumeLeft"]

    # 키만 빠진 상황에서도 폴백이 동작해야 event_gainFocus가 안 죽는다
    assert settings.get("beepVolumeLeft") == 50
