# -*- coding: utf-8 -*-
"""v3 → v4 자동 마이그레이션 검증.

v3 포맷: `appBeepMap`/`tabBeepIdx` 필드 없음.
v4 포맷: top-level `appBeepMap` + scope=window entry의 `tabBeepIdx` 필수.

로드 시 _ensure_beep_assignments가 거리 기반으로 자동 채워 넣어야 하고,
그 결과가 디스크에 영구화되어야 한다.
"""

import json
import os

from globalPlugins.multiTaskingWindowNotifier import appListStore
from globalPlugins.multiTaskingWindowNotifier.constants import (
    BEEP_TABLE_SIZE,
    SCOPE_APP,
    SCOPE_WINDOW,
)


def _list_path(tmp_path):
    return str(tmp_path / "app.list")


def _json_path(tmp_path):
    return str(tmp_path / "app.json")


def _write_v3_json(json_path, items):
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"version": 3, "items": items}, f)


def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_v3_window_only_gets_app_beep_map_and_tab_idx(tmp_path):
    """v3 scope=window만 있는 파일 → v4로 변환되면서 appBeepMap + tabBeepIdx 채움."""
    _write_v3_json(_json_path(tmp_path), [
        {"key": "notepad|제목 없음", "scope": "window",
         "appId": "notepad", "title": "제목 없음",
         "registeredAt": "2026-04-17T20:00:00",
         "switchCount": 0, "lastSeenAt": None},
    ])

    list_path = _list_path(tmp_path)
    keys = appListStore.load(list_path)
    assert keys == ["notepad|제목 없음"]

    data = _read_json(_json_path(tmp_path))
    assert data["version"] == 4
    assert data["appBeepMap"] == {"notepad": 0}
    assert data["items"][0]["tabBeepIdx"] == 0


def test_v3_mixed_scope_migration_assigns_distinct_app_idx(tmp_path):
    """v3 scope=app + scope=window 섞인 파일 → 각 appId마다 서로 다른 app_idx 할당."""
    _write_v3_json(_json_path(tmp_path), [
        {"key": "chrome", "scope": "app",
         "appId": "chrome", "title": "",
         "registeredAt": "2026-04-17T20:00:00",
         "switchCount": 0, "lastSeenAt": None},
        {"key": "chrome|YouTube", "scope": "window",
         "appId": "chrome", "title": "YouTube",
         "registeredAt": "2026-04-17T20:00:00",
         "switchCount": 0, "lastSeenAt": None},
        {"key": "notepad|Memo", "scope": "window",
         "appId": "notepad", "title": "Memo",
         "registeredAt": "2026-04-17T20:00:00",
         "switchCount": 0, "lastSeenAt": None},
    ])

    list_path = _list_path(tmp_path)
    appListStore.load(list_path)

    app_map = _read_json(_json_path(tmp_path))["appBeepMap"]
    # 서로 다른 appId는 거리 기반으로 충분히 멀리 떨어진 idx 획득.
    assert app_map["chrome"] != app_map["notepad"]
    # 등장 순서: chrome → notepad → 각각 0과 63 (BEEP_TABLE_SIZE-1).
    assert app_map["chrome"] == 0
    assert app_map["notepad"] == BEEP_TABLE_SIZE - 1


def test_v3_multiple_windows_same_app_get_distinct_tab_idx(tmp_path):
    """같은 appId의 window 여러 개 → 각자 다른 tabBeepIdx."""
    _write_v3_json(_json_path(tmp_path), [
        {"key": "chrome|Tab A", "scope": "window",
         "appId": "chrome", "title": "Tab A",
         "registeredAt": "2026-04-17T20:00:00",
         "switchCount": 0, "lastSeenAt": None},
        {"key": "chrome|Tab B", "scope": "window",
         "appId": "chrome", "title": "Tab B",
         "registeredAt": "2026-04-17T20:00:00",
         "switchCount": 0, "lastSeenAt": None},
        {"key": "chrome|Tab C", "scope": "window",
         "appId": "chrome", "title": "Tab C",
         "registeredAt": "2026-04-17T20:00:00",
         "switchCount": 0, "lastSeenAt": None},
    ])

    list_path = _list_path(tmp_path)
    appListStore.load(list_path)

    items = _read_json(_json_path(tmp_path))["items"]
    tab_indices = [it["tabBeepIdx"] for it in items]
    # 3개 모두 서로 다름 (거리 기반 할당).
    assert len(set(tab_indices)) == 3
    # 첫 window는 0, 두 번째는 가장 먼 63, 세 번째는 중간 31.
    assert tab_indices == [0, 63, 31]


def test_v4_file_preserves_existing_assignments(tmp_path):
    """이미 v4 형태로 저장된 파일은 로드 시 재할당하지 않음."""
    json_path = _json_path(tmp_path)
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    payload = {
        "version": 4,
        "appBeepMap": {"chrome": 10},
        "items": [
            {"key": "chrome|Tab A", "scope": "window",
             "appId": "chrome", "title": "Tab A",
             "tabBeepIdx": 5,
             "registeredAt": "2026-04-17T20:00:00",
             "switchCount": 0, "lastSeenAt": None},
        ],
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)

    list_path = _list_path(tmp_path)
    appListStore.load(list_path)

    data = _read_json(json_path)
    assert data["appBeepMap"]["chrome"] == 10
    assert data["items"][0]["tabBeepIdx"] == 5


def test_v4_file_fills_partial_missing_fields(tmp_path):
    """v4지만 일부 필드가 누락된 파일 → 누락된 것만 자동 채움."""
    json_path = _json_path(tmp_path)
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    payload = {
        "version": 4,
        "appBeepMap": {"chrome": 10},
        "items": [
            {"key": "chrome|Tab A", "scope": "window",
             "appId": "chrome", "title": "Tab A",
             "tabBeepIdx": 5,
             "registeredAt": "2026-04-17T20:00:00",
             "switchCount": 0, "lastSeenAt": None},
            # notepad는 appBeepMap 누락 + tabBeepIdx도 누락.
            {"key": "notepad|Memo", "scope": "window",
             "appId": "notepad", "title": "Memo",
             "registeredAt": "2026-04-17T20:00:00",
             "switchCount": 0, "lastSeenAt": None},
        ],
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)

    list_path = _list_path(tmp_path)
    appListStore.load(list_path)

    data = _read_json(json_path)
    # 기존 값 보존.
    assert data["appBeepMap"]["chrome"] == 10
    assert data["items"][0]["tabBeepIdx"] == 5
    # 누락 값 할당됨.
    assert "notepad" in data["appBeepMap"]
    assert isinstance(data["items"][1]["tabBeepIdx"], int)


def test_getters_return_assigned_indices(tmp_path):
    """get_app_beep_idx / get_tab_beep_idx 공개 API 동작 검증."""
    path = _list_path(tmp_path)
    appListStore.save(path, ["chrome|Tab A", "notepad"],
                      scopes={"notepad": SCOPE_APP})

    chrome_idx = appListStore.get_app_beep_idx(path, "chrome")
    notepad_idx = appListStore.get_app_beep_idx(path, "notepad")
    tab_a_idx = appListStore.get_tab_beep_idx(path, "chrome|Tab A")

    assert isinstance(chrome_idx, int) and 0 <= chrome_idx < BEEP_TABLE_SIZE
    assert isinstance(notepad_idx, int) and 0 <= notepad_idx < BEEP_TABLE_SIZE
    assert chrome_idx != notepad_idx  # 서로 다른 appId는 다른 idx
    assert isinstance(tab_a_idx, int) and 0 <= tab_a_idx < BEEP_TABLE_SIZE


def test_get_tab_beep_idx_returns_none_for_app_scope(tmp_path):
    """scope=app entry는 tabBeepIdx 없음 → None."""
    path = _list_path(tmp_path)
    appListStore.save(path, ["chrome"], scopes={"chrome": SCOPE_APP})
    assert appListStore.get_tab_beep_idx(path, "chrome") is None


def test_invalid_beep_map_value_is_reassigned(tmp_path):
    """appBeepMap에 범위 밖/잘못된 타입 값이 들어 있으면 재할당."""
    json_path = _json_path(tmp_path)
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    payload = {
        "version": 4,
        "appBeepMap": {"chrome": 999, "notepad": "oops"},  # 범위 밖 + 잘못된 타입
        "items": [
            {"key": "chrome|Tab A", "scope": "window",
             "appId": "chrome", "title": "Tab A",
             "tabBeepIdx": 0,
             "registeredAt": "2026-04-17T20:00:00",
             "switchCount": 0, "lastSeenAt": None},
        ],
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)

    list_path = _list_path(tmp_path)
    appListStore.load(list_path)

    data = _read_json(json_path)
    chrome_idx = data["appBeepMap"].get("chrome")
    assert isinstance(chrome_idx, int) and 0 <= chrome_idx < BEEP_TABLE_SIZE
