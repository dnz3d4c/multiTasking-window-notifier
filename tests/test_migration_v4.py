# -*- coding: utf-8 -*-
"""v3→v4→v5→v6→v7→v8→v9 자동 마이그레이션 검증.

v3 포맷: `appBeepMap`/`tabBeepIdx` 필드 없음.
v4 포맷: 전 범위(0..BEEP_TABLE_SIZE) 거리 기반 할당.
v5 포맷: 사용 범위를 [BEEP_USABLE_START, BEEP_USABLE_END)로 축소한 거리 기반.
v6 포맷: 반음 64음 테이블 + 등록 순서 기반 순차 할당.
v7 포맷: 테이블을 C major 온음계 35음으로 교체. v6 이하 파일은 로드 시
    기존 할당을 모두 버리고 순차로 1회성 재배정 후 저장.
v8 포맷: scope=window/app 양쪽 entry에 `aliases: [str]` 배열 추가.
    v7 이하 파일은 로드 시 모든 entry에 aliases=[] 주입 후 version 승격.
    비프 재배정 없음 (단순 필드 확장).
v9 포맷: normalize_title 파이프라인 확장(em-dash 1순위 + 카운트 토큰 흡수).
    v8 이하 파일은 로드 시 title 자동 재정규화 + aliases 재정규화 + 1회 .v8.bak
    백업 후 version=9로 저장. 비프 재배정/스키마 변경 없음. 이후 로드는 변경 없이 유지.
"""

import json
import os

from globalPlugins.multiTaskingWindowNotifier import store
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
    keys = store.load(list_path)
    assert keys == ["notepad|제목 없음"]

    data = _read_json(_json_path(tmp_path))
    assert data["version"] == 9
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
    store.load(list_path)

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
    store.load(list_path)

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
    store.load(list_path)

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
    store.load(list_path)

    data = _read_json(json_path)
    assert data["version"] == 9
    # 재배정: 등장 순서대로 chrome=0, notepad=1.
    assert data["appBeepMap"]["chrome"] == BEEP_USABLE_START
    assert data["appBeepMap"]["notepad"] == BEEP_USABLE_START + 1
    # 각 앱의 첫 탭 = 0.
    assert data["items"][0]["tabBeepIdx"] == BEEP_USABLE_START
    assert data["items"][1]["tabBeepIdx"] == BEEP_USABLE_START


def test_v4_file_gets_reassigned_to_v7_range(tmp_path):
    """v4 파일도 v9까지 단번에 승격. 비프는 순차 재배정, aliases는 []로 주입."""
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
    store.load(list_path)

    data = _read_json(json_path)
    assert data["version"] == 9
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
    store.load(list_path)

    data = _read_json(json_path)
    assert data["version"] == 9
    # 등장 순서대로 재배정: chrome=0, firefox=1.
    assert data["appBeepMap"]["chrome"] == BEEP_USABLE_START
    assert data["appBeepMap"]["firefox"] == BEEP_USABLE_START + 1
    # 각 앱의 첫 탭은 앱별 카운터 0에서 시작.
    assert data["items"][0]["tabBeepIdx"] == BEEP_USABLE_START
    assert data["items"][1]["tabBeepIdx"] == BEEP_USABLE_START


def test_v7_file_preserves_existing_assignments(tmp_path):
    """v7 파일 → v9 승격 시 비프 할당은 그대로 보존. aliases=[]만 추가."""
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
    store.load(list_path)

    data = _read_json(json_path)
    # v7 → v9 승격: version 필드 교체 + aliases 배열 주입 (비프 재배정 없음).
    assert data["version"] == 9
    assert data["appBeepMap"]["chrome"] == 12
    assert data["items"][0]["tabBeepIdx"] == 20
    assert data["items"][0]["aliases"] == []


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
    store.load(list_path)

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
    store.save(path, ["chrome|Tab A", "notepad"],
                      scopes={"notepad": SCOPE_APP})

    chrome_idx = store.get_app_beep_idx(path, "chrome")
    notepad_idx = store.get_app_beep_idx(path, "notepad")
    tab_a_idx = store.get_tab_beep_idx(path, "chrome|Tab A")

    assert isinstance(chrome_idx, int) and 0 <= chrome_idx < BEEP_TABLE_SIZE
    assert isinstance(notepad_idx, int) and 0 <= notepad_idx < BEEP_TABLE_SIZE
    assert chrome_idx != notepad_idx  # 서로 다른 appId는 다른 idx
    assert isinstance(tab_a_idx, int) and 0 <= tab_a_idx < BEEP_TABLE_SIZE


def test_get_tab_beep_idx_returns_none_for_app_scope(tmp_path):
    """scope=app entry는 tabBeepIdx 없음 → None."""
    path = _list_path(tmp_path)
    store.save(path, ["chrome"], scopes={"chrome": SCOPE_APP})
    assert store.get_tab_beep_idx(path, "chrome") is None


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
    store.load(list_path)

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
    store.load(list_path)
    first_data = _read_json(json_path)
    first_chrome = first_data["appBeepMap"]["chrome"]
    first_tab = first_data["items"][0]["tabBeepIdx"]

    # 프로세스 재시작 시뮬레이션
    store.reset_cache()

    store.load(list_path)
    second_data = _read_json(json_path)
    assert second_data["version"] == 9
    assert second_data["appBeepMap"]["chrome"] == first_chrome
    assert second_data["items"][0]["tabBeepIdx"] == first_tab


# ────────────────────────────────────────────────────────────────────────────
# Phase 9.2: v8 → v9 마이그레이션 (normalize_title 파이프라인 확장)
# ────────────────────────────────────────────────────────────────────────────


def _write_v8_json(json_path, items, app_beep_map=None):
    _write_json(json_path, {
        "version": 8,
        "appBeepMap": app_beep_map or {},
        "items": items,
    })


def test_v8_title_with_count_token_renormalized_to_v9(tmp_path):
    """v8 사용자 title `(12) · news_Healing — Mozilla Firefox`가 v9 부팅 시
    `news_Healing`으로 흡수되어 key가 재구성되고 version=9로 저장된다."""
    json_path = _json_path(tmp_path)
    _write_v8_json(json_path, [
        {"key": "firefox|(12) · news_Healing — Mozilla Firefox", "scope": "window",
         "appId": "firefox", "title": "(12) · news_Healing — Mozilla Firefox",
         "aliases": [],
         "tabBeepIdx": BEEP_USABLE_START,
         "registeredAt": "2026-04-17T20:00:00",
         "switchCount": 0, "lastSeenAt": None},
    ], app_beep_map={"firefox": BEEP_USABLE_START})

    list_path = _list_path(tmp_path)
    store.load(list_path)

    data = _read_json(json_path)
    assert data["version"] == 9
    assert data["items"][0]["title"] == "news_Healing"
    assert data["items"][0]["key"] == "firefox|news_Healing"
    # 비프 매핑은 그대로 보존(재배정 없음).
    assert data["appBeepMap"]["firefox"] == BEEP_USABLE_START
    assert data["items"][0]["tabBeepIdx"] == BEEP_USABLE_START


def test_v8_aliases_with_count_token_renormalized_to_v9(tmp_path):
    """v8 entry의 aliases 필드도 새 normalize_title 룰로 재정규화된다."""
    json_path = _json_path(tmp_path)
    _write_v8_json(json_path, [
        {"key": "kakao|카카오톡", "scope": "window",
         "appId": "kakao", "title": "카카오톡",
         "aliases": ["(5) 링키지접근성 — Mozilla Firefox"],
         "tabBeepIdx": BEEP_USABLE_START,
         "registeredAt": "2026-04-17T20:00:00",
         "switchCount": 0, "lastSeenAt": None},
    ], app_beep_map={"kakao": BEEP_USABLE_START})

    list_path = _list_path(tmp_path)
    store.load(list_path)

    data = _read_json(json_path)
    assert data["version"] == 9
    # alias의 카운트 토큰 + em-dash 앱 서픽스가 모두 흡수됨.
    assert data["items"][0]["aliases"] == ["링키지접근성"]


def test_v8_to_v9_creates_v8_bak_backup(tmp_path):
    """v8 → v9 첫 마이그레이션에서 `app.json.v8.bak` 백업 파일 생성."""
    json_path = _json_path(tmp_path)
    _write_v8_json(json_path, [
        {"key": "chrome|Tab A", "scope": "window",
         "appId": "chrome", "title": "Tab A",
         "aliases": [],
         "tabBeepIdx": BEEP_USABLE_START,
         "registeredAt": "2026-04-17T20:00:00",
         "switchCount": 0, "lastSeenAt": None},
    ], app_beep_map={"chrome": BEEP_USABLE_START})

    list_path = _list_path(tmp_path)
    store.load(list_path)

    bak = json_path + ".v8.bak"
    assert os.path.exists(bak), "v8 → v9 백업 파일이 생성되어야 한다"
    # 백업 내용은 마이그레이션 전 v8 원본
    bak_data = _read_json(bak)
    assert bak_data["version"] == 8


def test_v9_load_does_not_overwrite_existing_backup(tmp_path):
    """이미 .v8.bak이 존재하면(사용자가 의도적으로 보존) 덮어쓰지 않는다."""
    json_path = _json_path(tmp_path)
    bak = json_path + ".v8.bak"

    # 사용자가 이미 백업을 보관해둔 상태로 시뮬레이션
    _write_v8_json(json_path, [
        {"key": "chrome|Tab A", "scope": "window",
         "appId": "chrome", "title": "Tab A",
         "aliases": [],
         "tabBeepIdx": BEEP_USABLE_START,
         "registeredAt": "2026-04-17T20:00:00",
         "switchCount": 0, "lastSeenAt": None},
    ], app_beep_map={"chrome": BEEP_USABLE_START})
    # 사용자 보관 백업 (다른 내용)
    with open(bak, "w", encoding="utf-8") as f:
        json.dump({"version": 8, "items": [], "appBeepMap": {},
                   "user_preserved": True}, f)

    list_path = _list_path(tmp_path)
    store.load(list_path)

    bak_data = _read_json(bak)
    assert bak_data.get("user_preserved") is True, "기존 백업이 보존되어야 한다"


def test_v9_renormalization_runs_only_once(tmp_path):
    """v8 → v9 백업/재정규화는 1회. 두 번째 로드는 no-op."""
    json_path = _json_path(tmp_path)
    _write_v8_json(json_path, [
        {"key": "firefox|(12) · news_Healing — Mozilla Firefox", "scope": "window",
         "appId": "firefox", "title": "(12) · news_Healing — Mozilla Firefox",
         "aliases": [],
         "tabBeepIdx": BEEP_USABLE_START,
         "registeredAt": "2026-04-17T20:00:00",
         "switchCount": 0, "lastSeenAt": None},
    ], app_beep_map={"firefox": BEEP_USABLE_START})

    list_path = _list_path(tmp_path)
    store.load(list_path)

    first_data = _read_json(json_path)
    assert first_data["version"] == 9
    first_title = first_data["items"][0]["title"]

    # 프로세스 재시작 시뮬레이션
    store.reset_cache()

    store.load(list_path)
    second_data = _read_json(json_path)
    assert second_data["version"] == 9
    # 첫 마이그레이션 결과 그대로 유지
    assert second_data["items"][0]["title"] == first_title
