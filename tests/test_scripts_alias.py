# -*- coding: utf-8 -*-
"""Phase 7(v8 aliases) UI 레이어 테스트.

`_prompt_for_alias`는 wx 의존이라 단위 테스트에서 monkeypatch로 결과만
주입하고, 핵심 로직인 `_do_add(alias=...)`와 `_edit_alias_from_dialog`가
store에 올바르게 반영되는지 검증한다.
"""

from __future__ import annotations

import sys
import types

import pytest
from configobj import ConfigObj

from globalPlugins.multiTaskingWindowNotifier import store, scripts
from globalPlugins.multiTaskingWindowNotifier.constants import SCOPE_APP, SCOPE_WINDOW


@pytest.fixture
def plugin(monkeypatch, tmp_path):
    """ConfigObj 묶음 + GlobalPlugin 부팅. 다른 매칭 테스트와 동일 패턴."""
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


# ---- _do_add + alias ----


def test_do_add_with_alias_stores_normalized(plugin):
    """등록 시 alias가 normalize_title 적용 후 aliases=[정규화값]으로 저장."""
    plugin._do_add("messenger", "메신저앱", "messenger|메신저앱", SCOPE_WINDOW,
                   alias="대화창제목 - 메신저앱")
    meta = store.get_meta(plugin.appListFile, "messenger|메신저앱")
    # " - 메신저앱" 꼬리 서픽스가 normalize_title에서 벗겨져야 함.
    assert meta["aliases"] == ["대화창제목"]
    # windowLookup에 alias 역매핑 등록 확인.
    assert plugin.windowLookup.get("대화창제목") == 0
    assert plugin.windowLookup.get("messenger|메신저앱") == 0


def test_do_add_empty_alias_stays_empty(plugin):
    """alias 빈 문자열이면 aliases=[] 유지 (제거도 등록도 아닌 기본값)."""
    plugin._do_add("messenger", "메신저앱", "messenger|메신저앱", SCOPE_WINDOW, alias="")
    meta = store.get_meta(plugin.appListFile, "messenger|메신저앱")
    assert meta["aliases"] == []
    # alias 없으니 windowLookup에는 primary만.
    assert "대화창제목" not in plugin.windowLookup


def test_do_add_app_scope_with_alias(plugin):
    """scope=app 등록 시에도 alias가 저장되고 windowLookup 역매핑 주입."""
    plugin._do_add("messenger", "", "messenger", SCOPE_APP, alias="대화창제목")
    meta = store.get_meta(plugin.appListFile, "messenger")
    assert meta["scope"] == SCOPE_APP
    assert meta["aliases"] == ["대화창제목"]
    # Alt+Tab 오버레이는 match_appId=""라 appLookup fallback 불가.
    # alias가 windowLookup에 들어가야 역매핑 경유 매칭 가능.
    assert plugin.windowLookup.get("대화창제목") == 0
    assert plugin.appLookup.get("messenger") == 0


# ---- _edit_alias_from_dialog ----


def test_edit_alias_updates_store(plugin, monkeypatch):
    """편집 다이얼로그로 alias 교체."""
    store.save(plugin.appListFile, ["messenger|메신저앱"])
    plugin.appList = store.load(plugin.appListFile)
    plugin._rebuild_lookup()

    monkeypatch.setattr(scripts, "_prompt_for_alias",
                        lambda current_alias="": "새 별칭")
    assert plugin._edit_alias_from_dialog("messenger|메신저앱") is True

    meta = store.get_meta(plugin.appListFile, "messenger|메신저앱")
    assert meta["aliases"] == ["새 별칭"]
    # lookup 재구성으로 새 alias가 windowLookup에 들어왔는지 확인.
    assert plugin.windowLookup.get("새 별칭") == 0


def test_edit_alias_cancel_returns_none(plugin, monkeypatch):
    """Cancel을 누르면 변경 없음. store와 lookup 모두 그대로."""
    store.save(plugin.appListFile, ["messenger|메신저앱"])
    store.set_aliases(plugin.appListFile, "messenger|메신저앱", ["기존별칭"])
    plugin.appList = store.load(plugin.appListFile)
    plugin._rebuild_lookup()

    monkeypatch.setattr(scripts, "_prompt_for_alias",
                        lambda current_alias="": None)
    assert plugin._edit_alias_from_dialog("messenger|메신저앱") is None

    # store에 변화 없어야 함
    meta = store.get_meta(plugin.appListFile, "messenger|메신저앱")
    assert meta["aliases"] == ["기존별칭"]


def test_edit_alias_empty_removes(plugin, monkeypatch):
    """빈 값 확인 시 alias 제거."""
    store.save(plugin.appListFile, ["messenger|메신저앱"])
    store.set_aliases(plugin.appListFile, "messenger|메신저앱", ["기존별칭"])
    plugin.appList = store.load(plugin.appListFile)
    plugin._rebuild_lookup()

    monkeypatch.setattr(scripts, "_prompt_for_alias",
                        lambda current_alias="": "")
    assert plugin._edit_alias_from_dialog("messenger|메신저앱") is True

    meta = store.get_meta(plugin.appListFile, "messenger|메신저앱")
    assert meta["aliases"] == []
    # 제거 후엔 lookup에서도 빠짐
    assert "기존별칭" not in plugin.windowLookup


def test_edit_alias_no_op_when_unchanged(plugin, monkeypatch):
    """정규화 후 값이 동일하면 저장 건너뛰고 True 반환."""
    store.save(plugin.appListFile, ["messenger|메신저앱"])
    store.set_aliases(plugin.appListFile, "messenger|메신저앱", ["같은값"])
    plugin.appList = store.load(plugin.appListFile)
    plugin._rebuild_lookup()

    # 입력값 "같은값" 그대로 — normalize 후에도 동일.
    monkeypatch.setattr(scripts, "_prompt_for_alias",
                        lambda current_alias="": "같은값")
    assert plugin._edit_alias_from_dialog("messenger|메신저앱") is True

    meta = store.get_meta(plugin.appListFile, "messenger|메신저앱")
    assert meta["aliases"] == ["같은값"]


# ---- listDialog 표시 텍스트 ----


def test_format_display_text_with_alias():
    """alias가 있으면 꼬리에 `(대체: ...)` 포맷이 붙는다."""
    from globalPlugins.multiTaskingWindowNotifier.listDialog import format_display_text

    assert format_display_text(
        "messenger|메신저앱", "window", aliases=["대화창제목"]
    ) == "[창] messenger | 메신저앱 (대체: 대화창제목)"


def test_format_display_text_app_scope_with_alias():
    """scope=app에도 alias 꼬리표 붙음."""
    from globalPlugins.multiTaskingWindowNotifier.listDialog import format_display_text

    assert format_display_text(
        "messenger", "app", aliases=["대화창제목"]
    ) == "[앱] messenger (대체: 대화창제목)"


def test_format_display_text_empty_alias_no_suffix():
    """alias 배열이 비어있으면 꼬리표 없음 (기존 동작 유지)."""
    from globalPlugins.multiTaskingWindowNotifier.listDialog import format_display_text

    assert format_display_text("messenger", "app") == "[앱] messenger"
    assert format_display_text("messenger", "app", aliases=[]) == "[앱] messenger"
    assert format_display_text("messenger", "app", aliases=[""]) == "[앱] messenger"
