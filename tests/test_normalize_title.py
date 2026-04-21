# -*- coding: utf-8 -*-
"""appIdentity.normalize_title 엣지 케이스.

Alt+Tab 오버레이(obj.name), editor foreground.name, MRU obj.name 세 경로가 같은
형태로 떨어지도록 꼬리 " - 앱명" 서픽스와 선두 dirty 마커(`*`, `●`, `◌`, `•`)를
제거한다. 이 테스트는 각 분기가 독립적으로 동작함을 단언하고, 매칭 소스가
같은 규칙을 거치기 때문에 허용 가능한 엣지(정상 타이틀에 ' - ' 포함)를 명시한다.
"""

from __future__ import annotations

import pytest

from globalPlugins.multiTaskingWindowNotifier.appIdentity import (
    _RE_COUNT_TOKEN,
    normalize_title,
)


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


# ────────────────────────────────────────────────────────────────────────────
# Phase 9.1: em-dash 1순위 + 카운트 토큰 흡수
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("raw,expected", [
    # 케이스 1: 선두 카운트 + middle-dot + em-dash 앱 서픽스
    ("(12) · news_Healing — Mozilla Firefox", "news_Healing"),
    # 카운트 0이어도 동일 키
    ("(0) news_Healing — Mozilla Firefox", "news_Healing"),
    # 카운트 자체가 없어도 동일 키 (변동성에 무관)
    ("news_Healing — Mozilla Firefox", "news_Healing"),
    # 99+ 형태도 흡수
    ("(99+) Slack — Mozilla Firefox", "Slack"),
])
def test_browser_tab_with_leading_count(raw, expected):
    assert normalize_title(raw) == expected


@pytest.mark.parametrize("raw", [
    "받은편지함 (79) - advck1123@gmail.com - Gmail — Mozilla Firefox",
    "받은편지함 (3) - advck1123@gmail.com - Gmail — Mozilla Firefox",
    "받은편지함 (0) - advck1123@gmail.com - Gmail — Mozilla Firefox",
    "받은편지함 (9999) - advck1123@gmail.com - Gmail — Mozilla Firefox",
])
def test_inline_count_normalizes_to_same_key(raw):
    """카운트 (N)이 변해도 같은 정규화 키 → Alt+Tab 매칭 일관성."""
    assert normalize_title(raw) == "받은편지함 - advck1123@gmail.com - Gmail"


def test_dotted_version_preserved():
    """`(3.11)` 같은 dotted version은 카운트로 오인하지 않고 보존."""
    raw = "Python (3.11) Release Notes — Mozilla Firefox"
    assert normalize_title(raw) == "Python (3.11) Release Notes"


def test_content_em_dash_preserved():
    """콘텐츠 본문에 포함된 em-dash는 보존(마지막 한 덩이만 앱 서픽스로 제거)."""
    raw = "Chapter 1 — Introduction — Mozilla Firefox"
    assert normalize_title(raw) == "Chapter 1 — Introduction"


def test_em_dash_priority_over_hyphen():
    """em-dash와 hyphen이 같이 있으면 em-dash 우선 rsplit."""
    # 'foo - bar — baz' → em-dash 우선이라 'foo - bar' 보존
    assert normalize_title("foo - bar — baz") == "foo - bar"


def test_long_count_preserved():
    """5자리 이상 (12345)는 카운트로 보지 않고 보존(실측상 알림 카운트는 4자리 이내)."""
    assert normalize_title("(12345) Foo — Bar") == "(12345) Foo"


# ────────────────────────────────────────────────────────────────────────────
# helper 단언: _RE_COUNT_TOKEN 분류기 직접 검증 (회귀 시 1차 디버깅 지점)
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("token", [
    "(12)", "(0)", "(99+)", "[3]", "{42}", "(9999)",
])
def test_count_token_matches(token):
    assert _RE_COUNT_TOKEN.match(token)


@pytest.mark.parametrize("token", [
    "(3.11)",       # dotted version
    "(12345)",      # 5자리 이상
    "(abc)",        # 비숫자
    "(12",          # 닫히지 않음
    "12)",          # 열리지 않음
    "(12) ",        # 공백 포함
    "(12)x",        # 뒤에 문자
    "(5]",          # 괄호 종류 mismatch
    "[5}",          # 괄호 종류 mismatch
    "{5)",          # 괄호 종류 mismatch
])
def test_count_token_rejects(token):
    assert not _RE_COUNT_TOKEN.match(token)
