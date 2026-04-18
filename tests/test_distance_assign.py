# -*- coding: utf-8 -*-
"""순차 idx 할당 알고리즘 (_assign_next_idx) 검증.

v6의 appBeepMap과 tabBeepIdx는 이 알고리즘으로 자동 배정된다. 목표는 등록 순서
추적이 가능한 단순 순차 — max(used)+1. used가 구간 밖이면 무시, 구간 내 값이
없으면 start 반환. 포화 시 구간 내 wrap + log.warning.
"""

from globalPlugins.multiTaskingWindowNotifier.appListStore import _assign_next_idx
from globalPlugins.multiTaskingWindowNotifier.constants import (
    BEEP_TABLE_SIZE,
    BEEP_USABLE_SIZE,
    BEEP_USABLE_START,
)


def test_empty_used_returns_start():
    """used가 비면 start 반환. 기본 start=0."""
    assert _assign_next_idx([]) == 0
    assert _assign_next_idx([], size=10, start=5) == 5


def test_single_used_returns_next():
    """used=[n] → n+1. 등록 순서 다음 반음."""
    assert _assign_next_idx([0]) == 1
    assert _assign_next_idx([5]) == 6


def test_multiple_used_returns_max_plus_one():
    """used 집합의 max+1. 중간 gap은 재사용하지 않음."""
    assert _assign_next_idx([0, 1, 2]) == 3
    # 중간이 비어도 max+1 — 등록 순서 추적 유지.
    assert _assign_next_idx([0, 5, 2]) == 6


def test_saturated_wraps_around():
    """포화 시 구간 내 wrap. size=8, used=[0..7] → 0으로 회귀."""
    result = _assign_next_idx(list(range(8)), size=8)
    assert result == 0
    assert 0 <= result < 8


def test_saturated_wraps_with_start():
    """start가 있어도 wrap은 해당 구간 내에서."""
    # start=10, size=8: 구간 [10, 18). used가 17까지 차면 다음은 10.
    result = _assign_next_idx(list(range(10, 18)), size=8, start=10)
    assert result == 10


def test_start_parameter_shifts_range():
    """start=10 → used 없으면 10. used=[10,11] → 12."""
    assert _assign_next_idx([], size=8, start=10) == 10
    assert _assign_next_idx([10, 11], size=8, start=10) == 12


def test_out_of_range_used_ignored():
    """구간 밖 값은 무시. [100] (size=48) → 0 (used 비어 있는 것과 동일)."""
    assert _assign_next_idx([100], size=48, start=0) == 0
    # 일부만 구간 안 — 구간 내 값만 max 계산.
    assert _assign_next_idx([100, 5, 200], size=48, start=0) == 6


def test_ignores_non_integer_used_entries():
    """None/str/bool 등 잘못된 값 필터링. 정상 int만 max 계산에 포함."""
    assert _assign_next_idx([0, None, "oops", 2]) == 3
    # 숫자 문자열은 int로 승격.
    assert _assign_next_idx(["5", None]) == 6


def test_usable_range_first_assign_is_start():
    """BEEP_USABLE 구간에서 첫 할당은 항상 BEEP_USABLE_START."""
    assert _assign_next_idx(
        [], size=BEEP_USABLE_SIZE, start=BEEP_USABLE_START
    ) == BEEP_USABLE_START


def test_usable_range_second_assign_is_start_plus_one():
    """BEEP_USABLE 구간에서 두 번째 할당은 start+1 — 반음 위."""
    assert _assign_next_idx(
        [BEEP_USABLE_START], size=BEEP_USABLE_SIZE, start=BEEP_USABLE_START
    ) == BEEP_USABLE_START + 1


def test_full_table_first_assign():
    """BEEP_TABLE 전체 범위에서도 첫 할당은 0."""
    assert _assign_next_idx([], size=BEEP_TABLE_SIZE, start=0) == 0
