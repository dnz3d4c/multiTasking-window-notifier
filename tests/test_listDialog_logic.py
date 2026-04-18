# -*- coding: utf-8 -*-
"""listDialog.py의 순수 로직 함수 (Phase 4.2에서 module-level로 추출).

wx.App 인스턴스화 없이 단위 테스트 가능한 부분만 다룬다. EVT_BUTTON /
EVT_KEY_DOWN 핸들러와 MessageBox 흐름은 NVDA 실기 회귀 테스트로 넘긴다.

conftest.py가 wx/gui를 스텁으로 주입하므로 import 자체는 통과한다 —
wx.Dialog 서브클래스화는 모듈 로드 단계에서 stub class를 상속할 뿐.
"""

from __future__ import annotations

from globalPlugins.multiTaskingWindowNotifier.constants import SCOPE_APP, SCOPE_WINDOW


def test_format_display_text_app_scope():
    """scope=app은 entry 자체가 appId이고 프리픽스 [앱]."""
    from globalPlugins.multiTaskingWindowNotifier.listDialog import format_display_text

    assert format_display_text("chrome", SCOPE_APP) == "[앱] chrome"


def test_format_display_text_window_scope():
    """scope=window는 appId|title을 분해해 [창] appId | title 포맷."""
    from globalPlugins.multiTaskingWindowNotifier.listDialog import format_display_text

    assert format_display_text("chrome|YouTube", SCOPE_WINDOW) == "[창] chrome | YouTube"


def test_format_display_text_legacy_entry_without_appid():
    """구형 entry('|' 없음) → appId 공란은 '앱 미지정' 라벨로 폴백."""
    from globalPlugins.multiTaskingWindowNotifier.listDialog import format_display_text

    assert format_display_text("제목만", SCOPE_WINDOW) == "[창] 앱 미지정 | 제목만"


def test_format_count_text_uses_percent_d():
    """숫자 하나만 있으면 '총 N개' 포맷."""
    from globalPlugins.multiTaskingWindowNotifier.listDialog import format_count_text

    # 번역은 fallback `_ = lambda s: s`로 동작하므로 원문 포맷 그대로.
    assert format_count_text(0) == "총 0개"
    assert format_count_text(5) == "총 5개"


def test_compute_cascade_targets_basic():
    """앱 entry를 선택하면 같은 appId의 window entry가 cascade 후보로."""
    from globalPlugins.multiTaskingWindowNotifier.listDialog import compute_cascade_targets

    entries = [
        "chrome",           # scope=app
        "chrome|YouTube",   # scope=window, chrome 소속
        "chrome|Gmail",     # scope=window, chrome 소속
        "notepad|Memo",     # scope=window, 다른 앱
    ]
    scope_map = {
        "chrome": SCOPE_APP,
        "chrome|YouTube": SCOPE_WINDOW,
        "chrome|Gmail": SCOPE_WINDOW,
        "notepad|Memo": SCOPE_WINDOW,
    }
    result = compute_cascade_targets(
        selected=["chrome"],
        entries=entries,
        get_scope=lambda e: scope_map[e],
    )
    assert result == ["chrome|YouTube", "chrome|Gmail"]


def test_compute_cascade_targets_empty_when_no_app_selected():
    """window만 선택한 경우엔 cascade 대상 없음."""
    from globalPlugins.multiTaskingWindowNotifier.listDialog import compute_cascade_targets

    entries = ["chrome", "chrome|YouTube"]
    scope_map = {"chrome": SCOPE_APP, "chrome|YouTube": SCOPE_WINDOW}
    result = compute_cascade_targets(
        selected=["chrome|YouTube"],
        entries=entries,
        get_scope=lambda e: scope_map[e],
    )
    assert result == []


def test_compute_cascade_targets_empty_selected():
    """selected=[] 계약 방어. _delete_selected가 wx.Bell로 조기 복귀해
    실제론 도달 불가하지만 순수 함수 계약상 빈 리스트를 돌려줘야 한다."""
    from globalPlugins.multiTaskingWindowNotifier.listDialog import compute_cascade_targets

    assert compute_cascade_targets(
        selected=[],
        entries=["chrome", "chrome|YouTube"],
        get_scope=lambda e: SCOPE_APP if e == "chrome" else SCOPE_WINDOW,
    ) == []


def test_compute_cascade_targets_does_not_include_already_selected():
    """이미 selected에 포함된 window entry는 cascade에 다시 넣지 않는다."""
    from globalPlugins.multiTaskingWindowNotifier.listDialog import compute_cascade_targets

    entries = ["chrome", "chrome|YouTube", "chrome|Gmail"]
    scope_map = {
        "chrome": SCOPE_APP,
        "chrome|YouTube": SCOPE_WINDOW,
        "chrome|Gmail": SCOPE_WINDOW,
    }
    result = compute_cascade_targets(
        selected=["chrome", "chrome|YouTube"],
        entries=entries,
        get_scope=lambda e: scope_map[e],
    )
    # chrome|YouTube는 이미 선택돼 있으므로 cascade엔 chrome|Gmail만.
    assert result == ["chrome|Gmail"]
