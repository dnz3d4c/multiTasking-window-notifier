# -*- coding: utf-8 -*-
"""constants: 상수/비프 테이블 스모크 테스트."""

from globalPlugins.multiTaskingWindowNotifier.constants import (
    ADDON_NAME,
    BEEP_TABLE,
    BEEP_TABLE_SIZE,
    MAX_ITEMS,
)


def test_addon_name():
    assert ADDON_NAME == "multiTaskingWindowNotifier"


def test_beep_table_size_is_64():
    assert len(BEEP_TABLE) == BEEP_TABLE_SIZE == 64


def test_max_items_decoupled_from_palette():
    # v4: MAX_ITEMS는 BEEP_TABLE 크기와 분리되어 entry 상한만 의미. 팔레트 공유 가능.
    assert MAX_ITEMS >= BEEP_TABLE_SIZE


def test_beep_table_monotonic_increasing():
    assert all(
        BEEP_TABLE[i] < BEEP_TABLE[i + 1]
        for i in range(len(BEEP_TABLE) - 1)
    ), "비프 테이블은 반음 단위로 단조 증가해야 한다"


def test_beep_table_audible_range():
    # 130Hz~4978Hz (C3~B8) — NVDA tones.beep 가청 범위 내
    assert 100 <= BEEP_TABLE[0] <= 140
    assert 4900 <= BEEP_TABLE[-1] <= 5000
