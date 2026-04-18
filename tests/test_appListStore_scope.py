# -*- coding: utf-8 -*-
"""store: scope 필드 + v2→v3 마이그레이션."""

import json
import os

from globalPlugins.multiTaskingWindowNotifier import store
from globalPlugins.multiTaskingWindowNotifier.constants import SCOPE_APP, SCOPE_WINDOW


def _list_path(tmp_path):
    return str(tmp_path / "app.list")


def _json_path(tmp_path):
    return str(tmp_path / "app.json")


def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_save_writes_version_7(tmp_path):
    path = _list_path(tmp_path)
    store.save(path, ["a|t1"])
    data = _read_json(_json_path(tmp_path))
    assert data["version"] == 7


def test_new_keys_default_to_window_scope(tmp_path):
    path = _list_path(tmp_path)
    store.save(path, ["chrome|YouTube"])
    meta = store.get_meta(path, "chrome|YouTube")
    assert meta["scope"] == SCOPE_WINDOW
    assert meta["appId"] == "chrome"
    assert meta["title"] == "YouTube"


def test_app_scope_via_scopes_param(tmp_path):
    path = _list_path(tmp_path)
    store.save(path, ["chrome"], scopes={"chrome": SCOPE_APP})
    meta = store.get_meta(path, "chrome")
    assert meta["scope"] == SCOPE_APP
    assert meta["appId"] == "chrome"
    assert meta["title"] == ""


def test_mixed_scope_round_trip(tmp_path):
    path = _list_path(tmp_path)
    # title은 normalize_title 영향 받지 않는 형태 사용 — normalize 마이그레이션
    # 동작은 별도 테스트 소관. 여기선 mixed scope의 순수 round trip만 검증.
    keys = ["chrome", "chrome|YouTube", "notepad|룰루루"]
    scopes = {"chrome": SCOPE_APP}
    store.save(path, keys, scopes=scopes)

    store.reset_cache()

    assert store.load(path) == keys
    assert store.get_meta(path, "chrome")["scope"] == SCOPE_APP
    assert store.get_meta(path, "chrome|YouTube")["scope"] == SCOPE_WINDOW
    assert store.get_meta(path, "notepad|룰루루")["scope"] == SCOPE_WINDOW


def test_v2_file_loads_with_window_scope_injected(tmp_path):
    """v2 파일을 직접 만들고 load 시 자동 v3 마이그레이션 확인."""
    json_path = _json_path(tmp_path)
    payload = {
        "version": 2,
        "items": [
            {"key": "notepad|test", "appId": "notepad", "title": "test",
             "registeredAt": "2026-04-17T20:00:00",
             "switchCount": 5, "lastSeenAt": "2026-04-17T20:01:00"},
            {"key": "chrome|hello", "appId": "chrome", "title": "hello",
             "registeredAt": "2026-04-17T20:00:00",
             "switchCount": 1, "lastSeenAt": None},
        ],
    }
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)

    list_path = _list_path(tmp_path)
    keys = store.load(list_path)
    assert keys == ["notepad|test", "chrome|hello"]

    # scope 자동 주입 + 기존 메타(switchCount 등) 보존
    m1 = store.get_meta(list_path, "notepad|test")
    assert m1["scope"] == SCOPE_WINDOW
    assert m1["switchCount"] == 5
    assert m1["lastSeenAt"] == "2026-04-17T20:01:00"

    m2 = store.get_meta(list_path, "chrome|hello")
    assert m2["scope"] == SCOPE_WINDOW
    assert m2["switchCount"] == 1


def test_v2_file_promotes_to_v7_on_load(tmp_path):
    """v2 로드 시 스스로 v7로 승격 (scope 주입 + appBeepMap/tabBeepIdx 순차 할당)."""
    json_path = _json_path(tmp_path)
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "version": 2,
            "items": [{"key": "a|t1", "appId": "a", "title": "t1",
                       "registeredAt": "2026-04-17T20:00:00",
                       "switchCount": 0, "lastSeenAt": None}],
        }, f)

    list_path = _list_path(tmp_path)
    store.load(list_path)

    data = _read_json(json_path)
    assert data["version"] == 7
    # 저장된 항목에 scope 필드 + tabBeepIdx 채워짐
    assert data["items"][0]["scope"] == SCOPE_WINDOW
    assert isinstance(data["items"][0]["tabBeepIdx"], int)
    # top-level appBeepMap에 appId 등록됨
    assert "appBeepMap" in data
    assert "a" in data["appBeepMap"]


def test_unknown_scope_value_is_coerced_to_window(tmp_path):
    """손상/오타로 알 수 없는 scope 값이 디스크에 들어 있으면 window로 보정."""
    json_path = _json_path(tmp_path)
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "version": 3,
            "items": [{"key": "a|t1", "scope": "garbage",
                       "appId": "a", "title": "t1",
                       "registeredAt": "2026-04-17T20:00:00",
                       "switchCount": 0, "lastSeenAt": None}],
        }, f)

    list_path = _list_path(tmp_path)
    store.load(list_path)
    meta = store.get_meta(list_path, "a|t1")
    assert meta["scope"] == SCOPE_WINDOW


def test_app_scope_meta_preserves_across_save(tmp_path):
    """기존 app entry는 save() 후에도 scope 메타가 보존되어야 함."""
    path = _list_path(tmp_path)
    store.save(path, ["chrome"], scopes={"chrome": SCOPE_APP})
    store.record_switch(path, "chrome")

    # 같은 키 리스트로 재저장 — 기존 메타 보존 (scopes 인자 없이)
    store.save(path, ["chrome"])
    meta = store.get_meta(path, "chrome")
    assert meta["scope"] == SCOPE_APP
    assert meta["switchCount"] == 1
