# -*- coding: utf-8 -*-
"""appIdentity: 앱/창 복합키 생성·파싱 스모크 테스트."""

from globalPlugins.multiTaskingWindowNotifier.appIdentity import makeKey, splitKey


def test_make_key_basic():
    assert makeKey("notepad", "제목 없음 - 메모장") == "notepad|제목 없음 - 메모장"


def test_make_key_empty_title():
    assert makeKey("notepad", "") == "notepad|"


def test_split_key_basic():
    assert splitKey("notepad|제목") == ("notepad", "제목")


def test_split_key_legacy_title_only():
    # 구형 포맷: 구분자 없이 제목만 있던 시절의 항목
    assert splitKey("레거시 제목") == ("", "레거시 제목")


def test_split_key_multiple_separators():
    # 구분자가 2개 이상이어도 첫 구분자 기준 분리 (제목에 '|'가 포함된 경우)
    assert splitKey("a|b|c") == ("a", "b|c")


def test_round_trip():
    appId, title = "chrome", "Example Page"
    assert splitKey(makeKey(appId, title)) == (appId, title)
