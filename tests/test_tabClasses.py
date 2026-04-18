# -*- coding: utf-8 -*-
"""tabClasses 모듈: load/merge/save + is_*_class 조회.

tabClasses.json은 Alt+Tab 오버레이 매칭(overlay)과 Ctrl+Tab 확정 후 자식
컨트롤 매칭(editor)에 쓰인다. 로드 시 DEFAULT_TAB_CLASSES와 합집합 병합돼
사용자가 실수로 기본값을 지워도 자동 복원된다.
"""

from __future__ import annotations

import json

import pytest

from globalPlugins.multiTaskingWindowNotifier import tabClasses


@pytest.fixture(autouse=True)
def _reset_tab_classes_cache():
    tabClasses.reset_cache()
    yield
    tabClasses.reset_cache()


def _tab_path(tmp_path):
    return str(tmp_path / "tabClasses.json")


def test_load_creates_defaults_when_file_missing(tmp_path):
    path = _tab_path(tmp_path)
    tabClasses.load(path)
    # DEFAULT_TAB_CLASSES의 메모장/Notepad++ 항목이 조회 가능해야 한다.
    assert tabClasses.is_editor_class("notepad", "RichEditD2DPT") is True
    assert tabClasses.is_overlay_class("notepad++", "#32770") is True


def test_load_merges_defaults_into_existing_file(tmp_path):
    """사용자가 기본값 일부를 지워도 load가 합집합 병합으로 복원한다."""
    path = _tab_path(tmp_path)
    # 사용자가 notepad의 editor를 실수로 비운 상황 시뮬레이션
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "version": 2,
            "apps": {"notepad": {"editor": [], "overlay": []}},
        }, f)
    tabClasses.load(path)
    # DEFAULT의 RichEditD2DPT가 병합돼 복원돼야 한다.
    assert tabClasses.is_editor_class("notepad", "RichEditD2DPT") is True


def test_load_preserves_user_additions(tmp_path):
    """사용자가 추가한 커스텀 wcn은 병합 후에도 보존된다."""
    path = _tab_path(tmp_path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "version": 2,
            "apps": {"notepad": {"editor": ["CustomEditor"], "overlay": []}},
        }, f)
    tabClasses.load(path)
    assert tabClasses.is_editor_class("notepad", "CustomEditor") is True
    # DEFAULT도 함께 병합 확인
    assert tabClasses.is_editor_class("notepad", "RichEditD2DPT") is True


def test_save_persists_cache_to_disk(tmp_path):
    path = _tab_path(tmp_path)
    tabClasses.load(path)
    assert tabClasses.save(path) is True
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["version"] == 2
    assert "notepad" in data["apps"]


def test_is_editor_class_false_for_unknown_app(tmp_path):
    tabClasses.load(_tab_path(tmp_path))
    assert tabClasses.is_editor_class("unknown-app", "AnyWcn") is False


def test_is_overlay_class_empty_inputs(tmp_path):
    tabClasses.load(_tab_path(tmp_path))
    # 빈 appId/wcn은 조회 자체가 거부되어 False.
    assert tabClasses.is_overlay_class("", "") is False
    assert tabClasses.is_overlay_class("notepad++", "") is False
