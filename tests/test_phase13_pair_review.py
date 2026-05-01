# -*- coding: utf-8 -*-
"""Phase 13 페어 리뷰 후속: 손상 정책 통일 + 메모리/디스크 일관성 회귀 차단.

대상 IMP:
    IMP-1 set_aliases / move_item을 save() 패턴으로 정렬 (디스크 실패 시 메모리 롤백)
    IMP-2 app.json 항목 key 타입 검증 누락 → 손상 처리
    IMP-3 items 길이 초과를 손상으로 통일 (절단 안 함)
    IMP-4 tabBeepIdx 무효 시 log.warning (재할당)
    IMP-5 set_aliases 입력에 normalize_title 적용
    IMP-9 corrupted 상태 첫 save 시 자동 백업
"""
import glob
import json
import os

import pytest

from globalPlugins.multiTaskingWindowNotifier import store
from globalPlugins.multiTaskingWindowNotifier.constants import MAX_ITEMS


def _list_path(tmp_path):
    return str(tmp_path / "app.list")


def _json_path(tmp_path):
    return str(tmp_path / "app.json")


def _write_corrupt_json(json_path: str, payload) -> None:
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


# ============================================================
# IMP-2: app.json 항목 key 타입 검증
# ============================================================


def test_imp2_int_key_treated_as_corrupted(tmp_path):
    """key가 int면 손상 처리 — splitKey 예외로 초기 로드 깨지지 않게."""
    _write_corrupt_json(_json_path(tmp_path), {
        "version": 9,
        "appBeepMap": {},
        "items": [{"key": 12345, "scope": "window"}],
    })
    path = _list_path(tmp_path)
    assert store.load(path) == []
    assert store.is_corrupted(path) is True


def test_imp2_empty_string_key_treated_as_corrupted(tmp_path):
    _write_corrupt_json(_json_path(tmp_path), {
        "version": 9,
        "appBeepMap": {},
        "items": [{"key": "", "scope": "window"}],
    })
    path = _list_path(tmp_path)
    assert store.load(path) == []
    assert store.is_corrupted(path) is True


def test_imp2_none_key_treated_as_corrupted(tmp_path):
    _write_corrupt_json(_json_path(tmp_path), {
        "version": 9,
        "appBeepMap": {},
        "items": [{"key": None, "scope": "window"}],
    })
    path = _list_path(tmp_path)
    assert store.load(path) == []
    assert store.is_corrupted(path) is True


# ============================================================
# IMP-3: items 길이 초과 → 손상 처리 (절단 아님)
# ============================================================


def test_imp3_items_over_limit_treated_as_corrupted(tmp_path):
    """MAX_ITEMS+1개 → 손상 처리. 원본은 디스크에 보존되어야 한다."""
    items = [
        {"key": f"app{i}|title{i}", "scope": "window"}
        for i in range(MAX_ITEMS + 5)
    ]
    payload = {"version": 9, "appBeepMap": {}, "items": items}
    json_path = _json_path(tmp_path)
    _write_corrupt_json(json_path, payload)
    path = _list_path(tmp_path)

    assert store.load(path) == []
    assert store.is_corrupted(path) is True

    # 원본 app.json은 손상 감지 시점엔 변경되지 않음 (사용자가 복구 기회 가짐)
    with open(json_path, "r", encoding="utf-8") as f:
        kept = json.load(f)
    assert len(kept["items"]) == MAX_ITEMS + 5


# ============================================================
# IMP-4: tabBeepIdx 무효 시 log.warning + 재할당
# ============================================================


def test_imp4_invalid_tab_beep_idx_is_reassigned(tmp_path):
    """tabBeepIdx 타입/범위 불량은 손상 아님 — 다른 entry는 정상 로드되고
    무효 항목만 _ensure_beep_assignments가 다시 채워준다.
    """
    payload = {
        "version": 9,
        "appBeepMap": {"chrome": 0, "notepad": 1},
        "items": [
            {
                "key": "chrome|Example - Chrome",
                "scope": "window",
                "appId": "chrome",
                "title": "Example - Chrome",
                "aliases": [],
                "tabBeepIdx": "not-an-int",  # 무효: str
            },
            {
                "key": "notepad|메모",
                "scope": "window",
                "appId": "notepad",
                "title": "메모",
                "aliases": [],
                "tabBeepIdx": MAX_ITEMS + 99,  # 무효: 범위 초과
            },
        ],
    }
    _write_corrupt_json(_json_path(tmp_path), payload)
    path = _list_path(tmp_path)

    # 손상 아님 — 정상 로드
    assert store.load(path) == ["chrome|Example - Chrome", "notepad|메모"]
    assert store.is_corrupted(path) is False

    # 두 entry 모두 tabBeepIdx 재할당됨 (앱별 독립 카운터로 0부터)
    chrome_meta = store.get_meta(path, "chrome|Example - Chrome")
    notepad_meta = store.get_meta(path, "notepad|메모")
    assert isinstance(chrome_meta["tabBeepIdx"], int)
    assert 0 <= chrome_meta["tabBeepIdx"] < MAX_ITEMS
    assert isinstance(notepad_meta["tabBeepIdx"], int)
    assert 0 <= notepad_meta["tabBeepIdx"] < MAX_ITEMS


# ============================================================
# IMP-5: set_aliases 입력 정규화
# ============================================================


def test_imp5_set_aliases_normalizes_input(tmp_path):
    """`set_aliases`가 normalize_title을 적용해 꼬리 ' - 앱명' 서픽스를 제거.

    호출부가 실수로 정규화 안 한 raw title을 넘겨도 디스크에는 정규형으로 저장돼
    lookupIndex windowLookup의 setdefault 키와 어긋나지 않는다.
    """
    path = _list_path(tmp_path)
    store.save(path, ["chrome|Example"])

    # 꼬리 " - Google Chrome" 서픽스가 normalize_title로 제거되어야 함
    ok = store.set_aliases(path, "chrome|Example", ["다른이름 - Google Chrome"])
    assert ok is True

    meta = store.get_meta(path, "chrome|Example")
    # 정규화로 꼬리 제거된 결과만 저장
    assert meta["aliases"] == ["다른이름"]


def test_imp5_set_aliases_drops_empty_after_normalize(tmp_path):
    """정규화 결과가 빈 문자열이면 드롭 (저장 X)."""
    path = _list_path(tmp_path)
    store.save(path, ["chrome|Example"])

    # 공백/dirty 마커만 있는 입력 → normalize_title 결과 "" → 드롭
    ok = store.set_aliases(path, "chrome|Example", ["   ", "* ● ◌ •"])
    assert ok is True
    meta = store.get_meta(path, "chrome|Example")
    assert meta["aliases"] == []


# ============================================================
# IMP-9: corrupted 상태 첫 save 시 자동 백업
# ============================================================


def test_imp9_corrupted_save_creates_backup(tmp_path):
    """손상 감지 후 신규 등록(save) 한 번에 원본을 영구 소실시키지 않게,
    자동으로 `app.json.corrupted-{timestamp}` 백업이 생성되어야 한다.
    """
    json_path = _json_path(tmp_path)
    # 손상 데이터 (version != 9)
    _write_corrupt_json(json_path, {
        "version": 1,
        "items": [{"key": "old"}],
    })
    path = _list_path(tmp_path)

    # 첫 로드에서 corrupted=True 진입
    assert store.load(path) == []
    assert store.is_corrupted(path) is True

    # 사용자가 신규 등록 → save 한 번
    assert store.save(path, ["new|title"]) is True

    # 백업 파일이 생성되었는지 확인
    backup_files = glob.glob(str(tmp_path / "app.json.corrupted-*"))
    assert len(backup_files) == 1

    # 백업 내용은 손상 원본과 동일 (version=1, items=[{"key": "old"}])
    with open(backup_files[0], "r", encoding="utf-8") as f:
        backup = json.load(f)
    assert backup["version"] == 1
    assert backup["items"] == [{"key": "old"}]

    # 본체는 신규 데이터로 덮어써짐 + corrupted 플래그 해소
    assert store.is_corrupted(path) is False
    assert store.load(path) == ["new|title"]


def test_imp9_normal_save_does_not_create_backup(tmp_path):
    """corrupted 아닌 정상 흐름에선 백업 파일이 생성되지 않아야 한다."""
    path = _list_path(tmp_path)
    store.save(path, ["a|t1"])
    store.save(path, ["a|t1", "b|t2"])

    backup_files = glob.glob(str(tmp_path / "app.json.corrupted-*"))
    assert backup_files == []


# ============================================================
# IMP-1: set_aliases / move_item 디스크 실패 시 메모리 롤백
# ============================================================


def test_imp1_set_aliases_disk_failure_keeps_memory(tmp_path, monkeypatch):
    """`_save_to_disk`가 False를 반환해도 메모리 aliases는 이전 그대로여야 한다.
    이전 구현은 메모리를 먼저 변경해 다음 flush()에서 의도치 않은 값이 디스크에
    슬쩍 박힐 수 있었다.
    """
    path = _list_path(tmp_path)
    store.save(path, ["chrome|Example"])
    store.set_aliases(path, "chrome|Example", ["기존alias"])
    store.flush(path)

    # 이제 _save_to_disk가 실패하도록 monkeypatch
    monkeypatch.setattr(store, "_save_to_disk", lambda *a, **kw: False)

    ok = store.set_aliases(path, "chrome|Example", ["새alias"])
    assert ok is False

    # 메모리는 이전 값 유지
    meta = store.get_meta(path, "chrome|Example")
    assert meta["aliases"] == ["기존alias"]

    # monkeypatch 해제 후 정상 flush가 이전 상태를 그대로 디스크에 써도 안전해야 함
    monkeypatch.undo()
    store.flush(path)
    store.reset_cache()
    meta = store.get_meta(path, "chrome|Example")
    assert meta["aliases"] == ["기존alias"]


def test_imp1_move_item_disk_failure_keeps_order(tmp_path, monkeypatch):
    """move_item의 swap이 디스크 실패 시 메모리 순서로 롤백되어야 한다."""
    path = _list_path(tmp_path)
    store.save(path, ["a|t1", "b|t2", "c|t3"])

    monkeypatch.setattr(store, "_save_to_disk", lambda *a, **kw: False)

    ok = store.move_item(path, "b|t2", "up")
    assert ok is False

    # 메모리 순서 변경 안 됨
    assert store.load(path) == ["a|t1", "b|t2", "c|t3"]

    # 디스크 정상 복구 후 다음 flush에서 잘못된 순서가 박히지 않는지 확인
    monkeypatch.undo()
    store.flush(path)
    store.reset_cache()
    assert store.load(path) == ["a|t1", "b|t2", "c|t3"]
