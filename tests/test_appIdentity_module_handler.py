# -*- coding: utf-8 -*-
"""appIdentity.getAppId: appModuleHandler 경유 경로 검증.

Phase 1에서 `obj.appModule` 직접 getattr을 NVDA 공식 API
`appModuleHandler.getAppModuleForNVDAObject(obj)`로 교체했다. 이 테스트는 교체 이후:
    1. getAppModuleForNVDAObject가 실제로 호출되는지
    2. None 반환 시 windowClassName 폴백
    3. 예외 발생 시에도 windowClassName 폴백
    4. windowClassName까지 비면 "unknown"
을 보장한다.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock


def _make_obj(appName="", windowClassName=""):
    obj = types.SimpleNamespace()
    obj.appModule = types.SimpleNamespace(appName=appName)
    obj.windowClassName = windowClassName
    return obj


def test_uses_appModuleHandler_when_available(monkeypatch):
    """appModuleHandler.getAppModuleForNVDAObject가 호출되고 그 결과의 appName 반환."""
    from globalPlugins.multiTaskingWindowNotifier import appIdentity

    spy = MagicMock(return_value=types.SimpleNamespace(appName="chrome"))
    monkeypatch.setattr(sys.modules["appModuleHandler"], "getAppModuleForNVDAObject", spy)

    obj = _make_obj(appName="legacy-wrong", windowClassName="Chrome_WidgetWin_1")
    assert appIdentity.getAppId(obj) == "chrome"
    spy.assert_called_once_with(obj)


def test_falls_back_to_windowClassName_when_appModuleHandler_returns_None(monkeypatch):
    """appModule 객체 자체가 없으면 windowClassName으로 폴백."""
    from globalPlugins.multiTaskingWindowNotifier import appIdentity

    monkeypatch.setattr(
        sys.modules["appModuleHandler"], "getAppModuleForNVDAObject", lambda obj: None
    )

    obj = _make_obj(appName="ignored", windowClassName="SomeWindowClass")
    assert appIdentity.getAppId(obj) == "SomeWindowClass"


def test_falls_back_to_windowClassName_on_exception(monkeypatch):
    """appModuleHandler 호출이 예외를 던져도 이벤트 경로가 죽지 않고 폴백."""
    from globalPlugins.multiTaskingWindowNotifier import appIdentity

    def _boom(obj):
        raise RuntimeError("simulated appModule resolution failure")

    monkeypatch.setattr(sys.modules["appModuleHandler"], "getAppModuleForNVDAObject", _boom)

    obj = _make_obj(windowClassName="Notepad")
    assert appIdentity.getAppId(obj) == "Notepad"


def test_falls_back_to_unknown_when_everything_fails(monkeypatch):
    """appModuleHandler도 실패하고 windowClassName도 비면 'unknown'."""
    from globalPlugins.multiTaskingWindowNotifier import appIdentity

    monkeypatch.setattr(
        sys.modules["appModuleHandler"], "getAppModuleForNVDAObject", lambda obj: None
    )

    obj = _make_obj(windowClassName="")
    assert appIdentity.getAppId(obj) == "unknown"


def test_returns_empty_appName_triggers_fallback(monkeypatch):
    """appModule은 있지만 appName이 빈 문자열이면 windowClassName 폴백."""
    from globalPlugins.multiTaskingWindowNotifier import appIdentity

    monkeypatch.setattr(
        sys.modules["appModuleHandler"],
        "getAppModuleForNVDAObject",
        lambda obj: types.SimpleNamespace(appName=""),
    )

    obj = _make_obj(windowClassName="Explorer")
    assert appIdentity.getAppId(obj) == "Explorer"
