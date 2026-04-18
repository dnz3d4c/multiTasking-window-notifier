# -*- coding: utf-8 -*-
"""pytest conftest: NVDA 런타임 모듈 스텁을 sys.modules에 미리 주입.

실제 NVDA가 없는 환경(CI/로컬 venv)에서 `globalPlugins.multiTaskingWindowNotifier`
서브모듈을 import 가능하게 만든다.

주입 시점:
    이 파일이 모듈 레벨로 import되는 순간(= pytest collection 단계, 각 테스트
    파일의 import 이전). 따라서 애드온 코드의 `import api` 등이 스텁을 받는다.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest


# ─── NVDA 모듈 스텁 ────────────────────────────────────────────────────────────
# MagicMock은 임의 속성 접근/호출을 모두 허용하므로 `api.getForegroundObject()` 등
# 호출 자체는 통과한다. 반환값은 테스트별로 `monkeypatch.setattr`로 조정.

def _mock_module(name: str) -> types.ModuleType:
    """MagicMock을 담은 모듈 객체를 sys.modules에 등록."""
    mod = MagicMock(name=name)
    mod.__name__ = name
    mod.__spec__ = types.SimpleNamespace(name=name)
    sys.modules[name] = mod
    return mod


# 단순 모킹 대상
# controlTypes: __init__.py 학습 훅의 role 게이트에서 `controlTypes.Role.EDITABLETEXT`/
#   `controlTypes.Role.DOCUMENT`만 참조한다. MagicMock이 속성 접근을 자동 캐시하므로
#   같은 enum이 같은 객체로 돌아와 identity 비교 + in 연산 둘 다 안전.
for _name in [
    "api",
    "ui",
    "tones",
    "speech",
    "logHandler",
    "addonHandler",
    "scriptHandler",
    "config",
    "controlTypes",
    "appModuleHandler",
]:
    _mock_module(_name)


# appModuleHandler.getAppModuleForNVDAObject: 기본 반환을 `obj.appModule`로 세팅.
# 기존 테스트들이 `focus.appModule.appName = "..."` 방식으로 fixture를 구성해 왔으므로
# 이 호환 경로가 있어야 Phase 1 이후에도 기존 fixture가 그대로 통과한다.
sys.modules["appModuleHandler"].getAppModuleForNVDAObject = lambda obj: getattr(
    obj, "appModule", None
)


# globalVars: appArgs.configPath 속성 접근이 필요.
# fixture가 monkeypatch로 tmp_path를 덮어씌우므로 기본값은 빈 문자열.
_globalVars = types.ModuleType("globalVars")
_globalVars.appArgs = types.SimpleNamespace(configPath="")
sys.modules["globalVars"] = _globalVars


# globalPluginHandler: GlobalPlugin 베이스 클래스가 필요.
# 본 테스트는 GlobalPlugin 인스턴스화를 하지 않으므로 빈 클래스로 충분.
_gph = types.ModuleType("globalPluginHandler")
class _GlobalPluginStub:
    def __init__(self, *a, **kw):
        pass
_gph.GlobalPlugin = _GlobalPluginStub
sys.modules["globalPluginHandler"] = _gph


# scriptHandler.script: 무동작 decorator (kwargs 소비)
_sh = sys.modules["scriptHandler"]
_sh.script = lambda **kw: (lambda fn: fn)


# addonHandler.initTranslation: no-op
_ah = sys.modules["addonHandler"]
_ah.initTranslation = lambda: None


# gui 패키지와 서브모듈(guiHelper, settingsDialogs)
_gui = types.ModuleType("gui")
sys.modules["gui"] = _gui

_guiHelper = types.ModuleType("gui.guiHelper")
sys.modules["gui.guiHelper"] = _guiHelper
_gui.guiHelper = _guiHelper

_settingsDialogs = types.ModuleType("gui.settingsDialogs")
class _SettingsPanelStub:
    title = ""
    def __init__(self, *a, **kw):
        pass
_settingsDialogs.SettingsPanel = _SettingsPanelStub
sys.modules["gui.settingsDialogs"] = _settingsDialogs
_gui.settingsDialogs = _settingsDialogs


# logHandler.log: 디버그/정보/경고/에러 메서드 전부 지원 (MagicMock이 자동 처리)
# 이미 _mock_module("logHandler")로 처리됨. `from logHandler import log` 경로를 위해
# 명시적으로 log 속성을 MagicMock 인스턴스로 설정.
sys.modules["logHandler"].log = MagicMock(name="logHandler.log")


# ─── autouse fixture ──────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_addon_state(monkeypatch, tmp_path):
    """매 테스트마다 appListStore 캐시를 초기화하고 configPath를 tmp_path로 격리.

    사용자 실제 NVDA 설정 경로를 보호하기 위해 반드시 autouse로 돈다.
    """
    # 지연 import: sys.modules 스텁이 모두 주입된 이후여야 안전.
    from globalPlugins.multiTaskingWindowNotifier import appListStore

    appListStore.reset_cache()
    monkeypatch.setattr(
        sys.modules["globalVars"].appArgs,
        "configPath",
        str(tmp_path),
        raising=False,
    )
    yield
    appListStore.reset_cache()
