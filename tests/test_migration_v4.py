# -*- coding: utf-8 -*-
"""v3→v4→v5→v6→v7 자동 마이그레이션 검증.

v3 포맷: `appBeepMap`/`tabBeepIdx` 필드 없음.
v4 포맷: 전 범위(0..BEEP_TABLE_SIZE) 거리 기반 할당.
v5 포맷: 사용 범위를 [BEEP_USABLE_START, BEEP_USABLE_END)로 축소한 거리 기반.
v6 포맷: 반음 64음 테이블 + 등록 순서 기반 순차 할당.
v7 포맷: 테이블을 C major 온음계 35음으로 교체. v6 이하 파일은 로드 시
    기존 할당을 모두 버리고 순차로 1회성 재배정 후 version=7로 저장.
    이후 로드는 재배정 없이 기존 값 보존.
"""

import json
import os

from globalPlugins.multiTaskingWindowNotifier import appListStore
from globalPlugins.multiTaskingWindowNotifier.constants import (
    BEEP_TABLE_SIZE,
    BEEP_USABLE_END,
    BEEP_USABLE_START,
    SCOPE_APP,
    SCOPE_WINDOW,
)


def _list_path(tmp_path):
    return str(tmp_path / "app.list")


def _json_path(tmp_path):
    return str(tmp_path / "app.json")


def _write_json(json_path, payload):
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def _write_v3_json(json_path, items):
    _write_json(json_path, {"version": 3, "items": items})


def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_v3_window_only_gets_app_beep_map_and_tab_idx(tmp_path):
    """v3 scope=window만 있는 파일 → v7로 변환되면서 appBeepMap + tabBeepIdx 채움."""
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
    assert data["version"] == 7
    # 순차 할당: 첫 앱 = BEEP_USABLE_START, 첫 탭 = BEEP_USABLE_START.
    assert data["appBeepMap"] == {"notepad": BEEP_USABLE_START}
    assert data["items"][0]["tabBeepIdx"] == BEEP_USABLE_START


def test_v3_mixed_scope_migration_assigns_sequential_app_idx(tmp_path):
    """v3 scope=app + scope=window 섞인 파일 → 등록 순서대로 순차 app_idx 할당."""
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
    # 등록 순서: chrome → notepad. 각각 START, START+1 (반음 위).
    assert app_map["chrome"] == BEEP_USABLE_START
    assert app_map["notepad"] == BEEP_USABLE_START + 1


def test_v3_multiple_windows_same_app_get_distinct_tab_idx(tmp_path):
    """같은 appId의 window 여러 개 → 앱 내 순차 tabBeepIdx."""
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
    # 앱별 순차: 0, 1, 2 (BEEP_USABLE_START=0 기준).
    assert tab_indices == [
        BEEP_USABLE_START,
        BEEP_USABLE_START + 1,
        BEEP_USABLE_START + 2,
    ]


def test_v3_multiple_apps_tabs_are_app_independent(tmp_path):
    """앱별 탭 카운터가 독립 — 앱 B 탭1도 0부터 시작."""
    _write_v3_json(_json_path(tmp_path), [
        {"key": "chrome|Tab A", "scope": "window",
         "appId": "chrome", "title": "Tab A",
         "registeredAt": "2026-04-17T20:00:00",
         "switchCount": 0, "lastSeenAt": None},
        {"key": "chrome|Tab B", "scope": "window",
         "appId": "chrome", "title": "Tab B",
         "registeredAt": "2026-04-17T20:00:00",
         "switchCount": 0, "lastSeenAt": None},
        {"key": "notepad|File 1", "scope": "window",
         "appId": "notepad", "title": "File 1",
         "registeredAt": "2026-04-17T20:00:00",
         "switchCount": 0, "lastSeenAt": None},
    ])

    list_path = _list_path(tmp_path)
    appListStore.load(list_path)

    data = _read_json(_json_path(tmp_path))
    # 앱 비프: chrome=0, notepad=1.
    assert data["appBeepMap"]["chrome"] == BEEP_USABLE_START
    assert data["appBeepMap"]["notepad"] == BEEP_USABLE_START + 1
    # 탭 비프: chrome 탭1=0, 탭2=1 / notepad 탭1=0 (앱별 독립 카운터).
    items = data["items"]
    assert items[0]["tabBeepIdx"] == BEEP_USABLE_START
    assert items[1]["tabBeepIdx"] == BEEP_USABLE_START + 1
    assert items[2]["tabBeepIdx"] == BEEP_USABLE_START


def test_v5_file_gets_reassigned_to_v7_sequential(tmp_path):
    """v5 파일은 로드 시 거리 기반 값을 버리고 v7 온음계 기준으로 재배정된다."""
    json_path = _json_path(tmp_path)
    _write_json(json_path, {
        "version": 5,
        # v5 거리 기반 결과: 첫/끝으로 배치된 양극단.
        "appBeepMap": {"chrome": 0, "notepad": BEEP_USABLE_END - 1},
        "items": [
            {"key": "chrome|Tab A", "scope": "window",
             "appId": "chrome", "title": "Tab A",
             "tabBeepIdx": 0,
             "registeredAt": "2026-04-17T20:00:00",
             "switchCount": 0, "lastSeenAt": None},
            {"key": "notepad|Memo", "scope": "window",
             "appId": "notepad", "title": "Memo",
             "tabBeepIdx": 0,
             "registeredAt": "2026-04-17T20:00:00",
             "switchCount": 0, "lastSeenAt": None},
        ],
    })

    list_path = _list_path(tmp_path)
    appListStore.load(list_path)

    data = _read_json(json_path)
    assert data["version"] == 7
    # 재배정: 등장 순서대로 chrome=0, notepad=1.
    assert data["appBeepMap"]["chrome"] == BEEP_USABLE_START
    assert data["appBeepMap"]["notepad"] == BEEP_USABLE_START + 1
    # 각 앱의 첫 탭 = 0.
    assert data["items"][0]["tabBeepIdx"] == BEEP_USABLE_START
    assert data["items"][1]["tabBeepIdx"] == BEEP_USABLE_START


def test_v4_file_gets_reassigned_to_v7_range(tmp_path):
    """v4 파일도 v7로 재배정. 한 번 재배정되면 version=7로 저장되어 반복 없음."""
    json_path = _json_path(tmp_path)
    _write_json(json_path, {
        "version": 4,
        "appBeepMap": {"chrome": 10},
        "items": [
            {"key": "chrome|Tab A", "scope": "window",
             "appId": "chrome", "title": "Tab A",
             "tabBeepIdx": 5,
             "registeredAt": "2026-04-17T20:00:00",
             "switchCount": 0, "lastSeenAt": None},
        ],
    })

    list_path = _list_path(tmp_path)
    appListStore.load(list_path)

    data = _read_json(json_path)
    assert data["version"] == 7
    # 재배정된 값은 순차 기준. 첫 할당은 BEEP_USABLE_START.
    assert data["appBeepMap"]["chrome"] == BEEP_USABLE_START
    assert data["items"][0]["tabBeepIdx"] == BEEP_USABLE_START


def test_v6_file_gets_reassigned_to_v7_sequential(tmp_path):
    """v6 파일(반음 64 테이블)은 로드 시 기존 할당을 모두 버리고 v7 온음계
    기준으로 순차 재배정. 이전에는 v6 값 보존이었지만 온음계 전환으로
    인덱스 의미 자체가 달라져 1회성 재배정이 강제된다."""
    json_path = _json_path(tmp_path)
    _write_json(json_path, {
        "version": 6,
        # v6 반음 기준 값. 12=B4, 30=F#7 — v7 테이블(35)에선 다른 음을 가리킴.
        "appBeepMap": {"chrome": 12, "firefox": 40},  # 40은 v7 범위(0~34) 초과
        "items": [
            {"key": "chrome|Tab A", "scope": "window",
             "appId": "chrome", "title": "Tab A",
             "tabBeepIdx": 30,
             "registeredAt": "2026-04-17T20:00:00",
             "switchCount": 0, "lastSeenAt": None},
            {"key": "firefox|Home", "scope": "window",
             "appId": "firefox", "title": "Home",
             "tabBeepIdx": 20,
             "registeredAt": "2026-04-17T20:00:00",
             "switchCount": 0, "lastSeenAt": None},
        ],
    })

    list_path = _list_path(tmp_path)
    appListStore.load(list_path)

    data = _read_json(json_path)
    assert data["version"] == 7
    # 등장 순서대로 재배정: chrome=0, firefox=1.
    assert data["appBeepMap"]["chrome"] == BEEP_USABLE_START
    assert data["appBeepMap"]["firefox"] == BEEP_USABLE_START + 1
    # 각 앱의 첫 탭은 앱별 카운터 0에서 시작.
    assert data["items"][0]["tabBeepIdx"] == BEEP_USABLE_START
    assert data["items"][1]["tabBeepIdx"] == BEEP_USABLE_START


def test_v7_file_preserves_existing_assignments(tmp_path):
    """이미 v7로 저장된 파일은 로드 시 재배정하지 않음."""
    json_path = _json_path(tmp_path)
    _write_json(json_path, {
        "version": 7,
        "appBeepMap": {"chrome": 12},
        "items": [
            {"key": "chrome|Tab A", "scope": "window",
             "appId": "chrome", "title": "Tab A",
             "tabBeepIdx": 20,
             "registeredAt": "2026-04-17T20:00:00",
             "switchCount": 0, "lastSeenAt": None},
        ],
    })

    list_path = _list_path(tmp_path)
    appListStore.load(list_path)

    data = _read_json(json_path)
    assert data["version"] == 7
    assert data["appBeepMap"]["chrome"] == 12
    assert data["items"][0]["tabBeepIdx"] == 20


def test_v7_file_fills_partial_missing_fields(tmp_path):
    """v7지만 일부 필드가 누락된 파일 → 기존 값 보존 + 누락된 것만 자동 채움."""
    json_path = _json_path(tmp_path)
    _write_json(json_path, {
        "version": 7,
        "appBeepMap": {"chrome": 12},
        "items": [
            {"key": "chrome|Tab A", "scope": "window",
             "appId": "chrome", "title": "Tab A",
             "tabBeepIdx": 20,
             "registeredAt": "2026-04-17T20:00:00",
             "switchCount": 0, "lastSeenAt": None},
            # notepad는 appBeepMap 누락 + tabBeepIdx도 누락.
            {"key": "notepad|Memo", "scope": "window",
             "appId": "notepad", "title": "Memo",
             "registeredAt": "2026-04-17T20:00:00",
             "switchCount": 0, "lastSeenAt": None},
        ],
    })

    list_path = _list_path(tmp_path)
    appListStore.load(list_path)

    data = _read_json(json_path)
    # 기존 값 보존.
    assert data["appBeepMap"]["chrome"] == 12
    assert data["items"][0]["tabBeepIdx"] == 20
    # 누락 값 순차 할당. chrome=12 이후 notepad는 max+1=13.
    assert data["appBeepMap"]["notepad"] == 13
    # notepad의 첫 탭은 앱 내 used 없음 → BEEP_USABLE_START.
    assigned_tab = data["items"][1]["tabBeepIdx"]
    assert assigned_tab == BEEP_USABLE_START


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
    """appBeepMap에 범위 밖/잘못된 타입 값이 들어 있으면 재할당.

    v4 파일이라 어차피 v7 강제 재배정이 발동해 값이 정리된다.
    """
    json_path = _json_path(tmp_path)
    _write_json(json_path, {
        "version": 4,
        "appBeepMap": {"chrome": 999, "notepad": "oops"},  # 범위 밖 + 잘못된 타입
        "items": [
            {"key": "chrome|Tab A", "scope": "window",
             "appId": "chrome", "title": "Tab A",
             "tabBeepIdx": 0,
             "registeredAt": "2026-04-17T20:00:00",
             "switchCount": 0, "lastSeenAt": None},
        ],
    })

    list_path = _list_path(tmp_path)
    appListStore.load(list_path)

    data = _read_json(json_path)
    chrome_idx = data["appBeepMap"].get("chrome")
    # 순차 재할당: 첫 할당은 BEEP_USABLE_START.
    assert chrome_idx == BEEP_USABLE_START


def test_v4_reassignment_not_repeated_after_first_load(tmp_path):
    """v4 → v7 재배정은 최초 1회. 두 번째 로드에선 재배정 없이 그대로 유지."""
    json_path = _json_path(tmp_path)
    _write_json(json_path, {
        "version": 4,
        "appBeepMap": {"chrome": 0, "notepad": 63},
        "items": [
            {"key": "chrome|Tab A", "scope": "window",
             "appId": "chrome", "title": "Tab A",
             "tabBeepIdx": 0,
             "registeredAt": "2026-04-17T20:00:00",
             "switchCount": 0, "lastSeenAt": None},
        ],
    })

    list_path = _list_path(tmp_path)
    appListStore.load(list_path)
    first_data = _read_json(json_path)
    first_chrome = first_data["appBeepMap"]["chrome"]
    first_tab = first_data["items"][0]["tabBeepIdx"]

    # 프로세스 재시작 시뮬레이션
    appListStore.reset_cache()

    appListStore.load(list_path)
    second_data = _read_json(json_path)
    assert second_data["version"] == 7
    assert second_data["appBeepMap"]["chrome"] == first_chrome
    assert second_data["items"][0]["tabBeepIdx"] == first_tab
