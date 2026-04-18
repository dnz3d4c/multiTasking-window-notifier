# -*- coding: utf-8 -*-
"""constants: 상수/비프 테이블 스모크 테스트."""

from globalPlugins.multiTaskingWindowNotifier.constants import (
    ADDON_NAME,
    BEEP_TABLE,
    BEEP_TABLE_SIZE,
    BEEP_USABLE_END,
    BEEP_USABLE_SIZE,
    BEEP_USABLE_START,
    MAX_ITEMS,
)


def test_addon_name():
    assert ADDON_NAME == "multiTaskingWindowNotifier"


def test_beep_table_size_is_35():
    """v7: C major 온음계 7음 × 5옥타브 = 35."""
    assert len(BEEP_TABLE) == BEEP_TABLE_SIZE == 35


def test_max_items_decoupled_from_palette():
    # v4: MAX_ITEMS는 BEEP_TABLE 크기와 분리되어 entry 상한만 의미. 팔레트 공유 가능.
    assert MAX_ITEMS >= BEEP_TABLE_SIZE


def test_beep_table_monotonic_increasing():
    assert all(
        BEEP_TABLE[i] < BEEP_TABLE[i + 1]
        for i in range(len(BEEP_TABLE) - 1)
    ), "비프 테이블은 단조 증가해야 한다"


def test_beep_table_audible_range():
    # C3 130Hz ~ B7 3951Hz — NVDA tones.beep 가청 범위 내
    assert 100 <= BEEP_TABLE[0] <= 140
    assert 3800 <= BEEP_TABLE[-1] <= 4000


def test_beep_table_diatonic_c_major_pattern():
    """C major 온음계 W-W-H-W-W-W-H 반복 (옥타브당 7음).

    주파수 비율: 전음(W) ≈ 2^(2/12) ≈ 1.122, 반음(H) ≈ 2^(1/12) ≈ 1.059.
    허용 오차 ±0.015(정수 반올림 오차 흡수).
    """
    # 옥타브당 7슬롯. 35 = 7 × 5옥타브.
    assert BEEP_TABLE_SIZE % 7 == 0

    # 옥타브 내 인접 음정 패턴: C→D(W), D→E(W), E→F(H), F→G(W), G→A(W), A→B(W), B→C(H)
    # 마지막 B→C는 다음 옥타브 첫 음이라 인덱스 7 간격.
    W = 2 ** (2 / 12)
    H = 2 ** (1 / 12)
    tol = 0.015

    expected_ratios = [W, W, H, W, W, W]  # 한 옥타브 내 6개 인접 쌍 (C→D, D→E, …, A→B)
    for oct_start in range(0, BEEP_TABLE_SIZE, 7):
        for i, exp in enumerate(expected_ratios):
            ratio = BEEP_TABLE[oct_start + i + 1] / BEEP_TABLE[oct_start + i]
            assert abs(ratio - exp) < tol, (
                f"옥타브 {oct_start//7} 슬롯 {i}→{i+1} 비율 {ratio:.4f} ≠ 예상 {exp:.4f}"
            )


def test_beep_table_octave_doubling():
    """같은 음이 한 옥타브 위면 주파수가 2배 (정수 반올림 오차 허용)."""
    for i in range(BEEP_TABLE_SIZE - 7):
        ratio = BEEP_TABLE[i + 7] / BEEP_TABLE[i]
        assert 1.97 <= ratio <= 2.03, f"idx {i}→{i+7} 옥타브 비율 {ratio:.3f}"


def test_beep_usable_range_is_inside_full_palette():
    """실사용 구간은 BEEP_TABLE 내부여야 한다."""
    assert 0 <= BEEP_USABLE_START
    assert BEEP_USABLE_END <= BEEP_TABLE_SIZE
    assert BEEP_USABLE_START < BEEP_USABLE_END


def test_beep_usable_size_matches_start_end():
    """BEEP_USABLE_SIZE = END - START (불변식)."""
    assert BEEP_USABLE_SIZE == BEEP_USABLE_END - BEEP_USABLE_START


def test_beep_usable_covers_full_table_v7():
    """v7부터 온음계 자체가 변별력을 보장하므로 전 구간을 실사용한다."""
    assert BEEP_USABLE_START == 0
    assert BEEP_USABLE_END == BEEP_TABLE_SIZE
