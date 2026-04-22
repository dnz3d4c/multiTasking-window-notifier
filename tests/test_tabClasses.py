# -*- coding: utf-8 -*-
"""tabClasses 모듈: DEFAULT_TAB_CLASSES 상수 조회 검증.

JSON I/O 경로는 실사용 증거 0(사용자의 tabClasses.json = DEFAULT와 동일,
자동 학습 경로 미호출)으로 제거됨. 현재 모듈은 상수 dict 조회만 담당.
"""

from __future__ import annotations

from globalPlugins.multiTaskingWindowNotifier import tabClasses


def test_is_editor_class_true_for_default_entry():
    """DEFAULT_TAB_CLASSES의 editor 항목은 True를 반환한다."""
    assert tabClasses.is_editor_class("notepad", "RichEditD2DPT") is True


def test_is_editor_class_true_for_chrome():
    """Chrome의 Ctrl+Tab은 event_nameChange 미발화 + gainFocus만 발화하므로
    editor 분기가 유일한 매칭 경로. Chrome_RenderWidgetHostHWND는 탭별 자식 hwnd."""
    assert tabClasses.is_editor_class("chrome", "Chrome_RenderWidgetHostHWND") is True


def test_is_overlay_class_true_for_default_entry():
    """DEFAULT_TAB_CLASSES의 overlay 항목은 True를 반환한다."""
    assert tabClasses.is_overlay_class("notepad++", "#32770") is True


def test_is_editor_class_false_for_unknown_app():
    """등록 안 된 appId는 False."""
    assert tabClasses.is_editor_class("unknown-app", "AnyWcn") is False


def test_is_editor_class_false_for_unknown_wcn():
    """등록된 앱이어도 다른 wcn은 False."""
    assert tabClasses.is_editor_class("notepad", "OtherEditor") is False


def test_is_overlay_class_false_for_editor_wcn():
    """editor 분기에 속한 wcn을 overlay로 묻는 건 False (테이블 격리)."""
    assert tabClasses.is_overlay_class("notepad", "RichEditD2DPT") is False


def test_is_editor_class_empty_inputs():
    """빈 문자열 입력은 항상 False."""
    assert tabClasses.is_editor_class("", "") is False
    assert tabClasses.is_editor_class("notepad", "") is False
    assert tabClasses.is_editor_class("", "RichEditD2DPT") is False


def test_is_overlay_class_empty_inputs():
    """빈 문자열 입력은 항상 False."""
    assert tabClasses.is_overlay_class("", "") is False
    assert tabClasses.is_overlay_class("notepad++", "") is False
