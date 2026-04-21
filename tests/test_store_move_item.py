# -*- coding: utf-8 -*-
"""store.move_item: 등록 목록 순서 변경 API 검증.

등록 순서가 곧 화면 표시 순서이므로 swap 결과가 디스크/캐시 양쪽에
즉시 반영되어야 한다.
"""

from globalPlugins.multiTaskingWindowNotifier import store


def _list_path(tmp_path):
    return str(tmp_path / "app.list")


def test_move_up_swaps_with_previous(tmp_path):
    path = _list_path(tmp_path)
    store.save(path, ["a|t1", "b|t2", "c|t3"])

    assert store.move_item(path, "b|t2", "up") is True
    assert store.load(path) == ["b|t2", "a|t1", "c|t3"]


def test_move_down_swaps_with_next(tmp_path):
    path = _list_path(tmp_path)
    store.save(path, ["a|t1", "b|t2", "c|t3"])

    assert store.move_item(path, "b|t2", "down") is True
    assert store.load(path) == ["a|t1", "c|t3", "b|t2"]


def test_move_up_at_top_returns_false(tmp_path):
    path = _list_path(tmp_path)
    store.save(path, ["a|t1", "b|t2"])

    assert store.move_item(path, "a|t1", "up") is False
    # 실패 시 순서 불변
    assert store.load(path) == ["a|t1", "b|t2"]


def test_move_down_at_bottom_returns_false(tmp_path):
    path = _list_path(tmp_path)
    store.save(path, ["a|t1", "b|t2"])

    assert store.move_item(path, "b|t2", "down") is False
    assert store.load(path) == ["a|t1", "b|t2"]


def test_move_unknown_key_returns_false(tmp_path):
    path = _list_path(tmp_path)
    store.save(path, ["a|t1", "b|t2"])

    assert store.move_item(path, "nonexistent|key", "up") is False
    assert store.load(path) == ["a|t1", "b|t2"]


def test_move_invalid_direction_returns_false(tmp_path):
    path = _list_path(tmp_path)
    store.save(path, ["a|t1", "b|t2"])

    assert store.move_item(path, "a|t1", "left") is False
    assert store.move_item(path, "a|t1", "") is False
    assert store.load(path) == ["a|t1", "b|t2"]


def test_move_persists_across_cache_reset(tmp_path):
    path = _list_path(tmp_path)
    store.save(path, ["a|t1", "b|t2", "c|t3"])
    assert store.move_item(path, "c|t3", "up") is True

    # 프로세스 재시작 시뮬레이션
    store.reset_cache()

    assert store.load(path) == ["a|t1", "c|t3", "b|t2"]


def test_move_preserves_meta(tmp_path):
    """swap 후에도 switchCount/lastSeenAt 등 메타가 유지되어야 한다."""
    path = _list_path(tmp_path)
    store.save(path, ["a|t1", "b|t2"])
    store.record_switch(path, "a|t1")
    store.record_switch(path, "a|t1")
    store.flush(path)

    assert store.move_item(path, "a|t1", "down") is True

    meta = store.get_meta(path, "a|t1")
    assert meta is not None
    assert meta["switchCount"] == 2
    assert meta["lastSeenAt"] is not None
