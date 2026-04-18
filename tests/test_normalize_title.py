# -*- coding: utf-8 -*-
"""appIdentity.normalize_title 엣지 케이스.

Alt+Tab 오버레이(obj.name), editor fg.name, MRU obj.name 세 경로가 같은
형태로 떨어지도록 꼬리 " - 앱명" 서픽스와 선두 dirty 마커(`*`, `●`, `◌`, `•`)를
제거한다. 이 테스트는 각 분기가 독립적으로 동작함을 단언하고, 매칭 소스가
같은 규칙을 거치기 때문에 허용 가능한 엣지(정상 타이틀에 ' - ' 포함)를 명시한다.
"""

from __future__ import annotations

import pytest

from globalPlugins.multiTaskingWindowNotifier.appIdentity import normalize_title


@pytest.mark.parametrize("raw,expected", [
    ("제목 없음 - 메모장", "제목 없음"),
    ("Example - Chrome", "Example"),
])
def test_trailing_app_suffix_removed(raw, expected):
    assert normalize_title(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("*새로운 10 - Notepad++", "새로운 10"),          # Notepad++ dirty
    ("● main.py - VS Code", "main.py"),               # VS Code 수정됨
    ("◌ untitled - Sublime", "untitled"),             # Sublime 대체 마커
    ("• todo.md - Typora", "todo.md"),                # 일반 bullet
])
def test_leading_dirty_marker_stripped(raw, expected):
    assert normalize_title(raw) == expected


def test_hyphen_in_content_is_stripped_too():
    """정상 타이틀이 ' - '를 포함하면 마지막 덩이도 잘린다. 매칭 소스도
    같은 규칙을 거치므로 기능 회귀는 없다 (docstring 엣지 설명)."""
    assert normalize_title("Chapter 1 - Introduction - NPP") == "Chapter 1 - Introduction"


def test_no_suffix_returns_as_is():
    assert normalize_title("새로운 10") == "새로운 10"


@pytest.mark.parametrize("raw,expected", [
    ("", ""),
    (None, ""),
    ("   ", ""),
    ("*", ""),           # dirty 마커만 있는 경우
    ("* ● ◌ •", ""),      # 연속 마커도 전부 소거
])
def test_empty_or_marker_only(raw, expected):
    assert normalize_title(raw) == expected
