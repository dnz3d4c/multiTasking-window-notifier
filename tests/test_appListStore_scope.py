# -*- coding: utf-8 -*-
"""store: scope 필드 round trip + v9 손상 처리."""

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


def test_save_writes_current_version(tmp_path):
    """현 포맷(v9)으로 저장되는지 확인."""
    path = _list_path(tmp_path)
    store.save(path, ["a|t1"])
    data = _read_json(_json_path(tmp_path))
    assert data["version"] == 9
    # aliases 배열은 모든 entry에 존재한다 (scope 무관).
    assert data["items"][0]["aliases"] == []


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


def _write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def test_non_v9_version_is_treated_as_corrupted(tmp_path):
    """v9 이외 version 값은 손상으로 취급 — 빈 목록 + is_corrupted=True."""
    json_path = _json_path(tmp_path)
    _write_json(json_path, {
        "version": 2,
        "items": [{"key": "a|t1", "scope": SCOPE_WINDOW, "appId": "a",
                   "title": "t1", "aliases": [],
                   "registeredAt": "2026-04-17T20:00:00",
                   "switchCount": 0, "lastSeenAt": None}],
    })

    list_path = _list_path(tmp_path)
    assert store.load(list_path) == []
    assert store.is_corrupted(list_path) is True
    # 손상 감지 후 자동 덮어쓰기 금지 — 원본 파일은 그대로 보존되어야 함.
    assert _read_json(json_path)["version"] == 2


def test_missing_scope_is_treated_as_corrupted(tmp_path):
    """scope 필드가 누락된 v9 파일은 손상으로 취급 — 빈 목록 + is_corrupted=True."""
    json_path = _json_path(tmp_path)
    _write_json(json_path, {
        "version": 9,
        "items": [{"key": "a|t1", "appId": "a", "title": "t1", "aliases": [],
                   "registeredAt": "2026-04-17T20:00:00",
                   "switchCount": 0, "lastSeenAt": None}],
    })

    list_path = _list_path(tmp_path)
    assert store.load(list_path) == []
    assert store.is_corrupted(list_path) is True


def test_unknown_scope_value_is_treated_as_corrupted(tmp_path):
    """scope 값이 SCOPE_APP/SCOPE_WINDOW 외면 전체 파일 손상 취급."""
    json_path = _json_path(tmp_path)
    _write_json(json_path, {
        "version": 9,
        "items": [{"key": "a|t1", "scope": "garbage",
                   "appId": "a", "title": "t1", "aliases": [],
                   "registeredAt": "2026-04-17T20:00:00",
                   "switchCount": 0, "lastSeenAt": None}],
    })

    list_path = _list_path(tmp_path)
    assert store.load(list_path) == []
    assert store.is_corrupted(list_path) is True


def test_save_after_corruption_clears_flag(tmp_path):
    """손상 감지 후 save 성공 시 is_corrupted 플래그 해소 + 파일 정상 전환."""
    json_path = _json_path(tmp_path)
    _write_json(json_path, {"version": 3, "items": []})

    list_path = _list_path(tmp_path)
    store.load(list_path)  # 캐시에 상태 등록(is_corrupted는 캐시 조회형)
    assert store.is_corrupted(list_path) is True

    # 사용자가 빈 상태 안내 들은 뒤 새 항목 추가 → save 성공 → 플래그 리셋
    assert store.save(list_path, ["chrome"], scopes={"chrome": SCOPE_APP})
    assert store.is_corrupted(list_path) is False
    data = _read_json(json_path)
    assert data["version"] == 9
    assert data["items"][0]["key"] == "chrome"


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
