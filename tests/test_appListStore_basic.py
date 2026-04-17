# -*- coding: utf-8 -*-
"""appListStore: load/save/record_switch/flush 기본 왕복 스모크."""

from globalPlugins.multiTaskingWindowNotifier import appListStore


def _list_path(tmp_path):
    # appListStore는 '.../app.list' 경로를 받으면 내부에서 '.../app.json'으로 변환.
    # 디렉터리는 자동 생성되므로 존재하지 않아도 무방.
    return str(tmp_path / "app.list")


def test_load_empty_when_no_files(tmp_path):
    assert appListStore.load(_list_path(tmp_path)) == []


def test_save_load_round_trip(tmp_path):
    path = _list_path(tmp_path)
    keys = ["notepad|제목 없음 - 메모장", "chrome|Example - Chrome"]
    assert appListStore.save(path, keys) is True
    assert appListStore.load(path) == keys


def test_save_respects_order(tmp_path):
    path = _list_path(tmp_path)
    keys = ["b|t2", "a|t1", "c|t3"]
    appListStore.save(path, keys)
    assert appListStore.load(path) == keys


def test_record_switch_updates_meta(tmp_path):
    path = _list_path(tmp_path)
    appListStore.save(path, ["a|t1", "b|t2"])

    appListStore.record_switch(path, "a|t1")
    appListStore.record_switch(path, "a|t1")

    meta = appListStore.get_meta(path, "a|t1")
    assert meta is not None
    assert meta["switchCount"] == 2
    assert meta["lastSeenAt"] is not None


def test_record_switch_unknown_key_is_noop(tmp_path):
    path = _list_path(tmp_path)
    appListStore.save(path, ["a|t1"])
    appListStore.record_switch(path, "nonexistent|key")
    # 매칭 실패는 디버그 로그만. 예외 없이 통과해야 함.
    assert appListStore.get_meta(path, "a|t1")["switchCount"] == 0


def test_flush_persists_across_cache_reset(tmp_path):
    path = _list_path(tmp_path)
    appListStore.save(path, ["a|t1"])
    appListStore.record_switch(path, "a|t1")
    assert appListStore.flush(path) is True

    # 프로세스 재시작 시뮬레이션: 캐시만 비우고 디스크 JSON은 그대로
    appListStore.reset_cache()

    assert appListStore.load(path) == ["a|t1"]
    meta = appListStore.get_meta(path, "a|t1")
    assert meta["switchCount"] == 1


def test_is_corrupted_false_after_save(tmp_path):
    path = _list_path(tmp_path)
    # 아직 로드 안 했으므로 상태 없음 → False
    assert appListStore.is_corrupted(path) is False
    appListStore.save(path, ["a|t1"])
    assert appListStore.is_corrupted(path) is False
