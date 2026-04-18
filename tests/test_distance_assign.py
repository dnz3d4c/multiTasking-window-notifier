# -*- coding: utf-8 -*-
"""거리 기반 idx 할당 알고리즘 (_assign_distant_idx) 검증.

v4의 appBeepMap과 tabBeepIdx는 이 알고리즘으로 자동 배정된다. 목표는
기존 used 세트와 L1 거리 최대화. 팔레트 포화 시에도 wrap/중복 허용으로
예외 없이 최대 거리 idx를 반환한다.
"""

import pytest

from globalPlugins.multiTaskingWindowNotifier.appListStore import _assign_distant_idx
from globalPlugins.multiTaskingWindowNotifier.constants import BEEP_TABLE_SIZE


def test_empty_used_returns_zero():
    assert _assign_distant_idx([]) == 0


def test_single_used_picks_far_end():
    # used={0} → size=64 범위에서 가장 먼 i는 63.
    assert _assign_distant_idx([0]) == 63


def test_two_used_picks_middle():
    # used={0, 63} → 중간 31이 min거리 최대 (동률 시 작은 i 선택).
    assert _assign_distant_idx([0, 63]) == 31


def test_three_used_fills_remaining_gap():
    # used={0, 63, 31} → 남은 큰 gap은 [31, 63]의 중앙 근처. 47이 min=16으로 최대.
    assert _assign_distant_idx([0, 63, 31]) == 47


def test_saturated_used_still_returns_valid_idx():
    # 포화 상태: 팔레트 크기만큼 used 채움. 중복 허용으로 결과가 유효 범위 내여야.
    used = list(range(BEEP_TABLE_SIZE))
    result = _assign_distant_idx(used)
    assert 0 <= result < BEEP_TABLE_SIZE


def test_custom_size_parameter():
    # size=8로 좁히면 used={0}에서 가장 먼 건 7.
    assert _assign_distant_idx([0], size=8) == 7


def test_ties_pick_lowest_index():
    # used={0, 6} in size=8:
    #   i=3: min(3, 3)=3
    #   i=4: min(4, 2)=2
    #   → 3이 선택 (더 먼 거리).
    assert _assign_distant_idx([0, 6], size=8) == 3


def test_ignores_non_integer_used_entries():
    # 방어: used에 None/str 등 잘못된 값이 섞여도 필터링되고 유효 결과 반환.
    result = _assign_distant_idx([0, None, "oops", 63])
    assert result == 31
