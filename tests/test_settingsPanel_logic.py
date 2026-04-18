# -*- coding: utf-8 -*-
"""settingsPanel의 순수 로직(`_clamp` + 범위 상수) 단위 테스트.

wx.SpinCtrl 컨트롤 자체는 NVDA 실기에서만 검증 가능하지만, "수동 입력 경로가
범위를 넘기면 clamp"라는 계약은 `_clamp` 순수 함수와 MIN/MAX 상수만으로
확인할 수 있다. 회귀 시 onSave에서 잘못된 값이 conf에 기록돼 비프 재생이
깨질 수 있다.
"""

from __future__ import annotations

import pytest

from globalPlugins.multiTaskingWindowNotifier.settingsPanel import (
    DURATION_MAX,
    DURATION_MIN,
    GAP_MAX,
    GAP_MIN,
    _clamp,
)


@pytest.mark.parametrize("value,lo,hi,expected", [
    (50, 20, 500, 50),         # 정상 범위 내
    (10, 20, 500, 20),         # lo 미만 → lo
    (1000, 20, 500, 500),      # hi 초과 → hi
    (20, 20, 500, 20),         # 경계 (lo)
    (500, 20, 500, 500),       # 경계 (hi)
])
def test_clamp_enforces_bounds(value, lo, hi, expected):
    assert _clamp(value, lo, hi) == expected


def test_clamp_coerces_non_int_to_int():
    """str/float을 SpinCtrl이 돌려줄 가능성은 낮지만 계약상 int() 캐스팅이 돼야
    configobj가 자연스럽게 받아먹는다."""
    assert _clamp(3.7, 0, 10) == 3  # int()는 truncate
    assert _clamp("25", 20, 500) == 25


def test_duration_and_gap_ranges_are_sensible():
    """설정 UI 범위 상수가 비프 재생에 유효한 구간인지 자체 모순 체크.

    duration: 20~500ms (너무 짧으면 안 들리고, 너무 길면 전환 지연 체감)
    gap: 0~200ms (0=거의 붙음, 200ms=사용자가 구분 인지 가능한 상한)
    """
    assert DURATION_MIN < DURATION_MAX
    assert GAP_MIN <= GAP_MAX
    # 기본값(settings.py confspec: 50/100)이 구간 내
    assert DURATION_MIN <= 50 <= DURATION_MAX
    assert GAP_MIN <= 100 <= GAP_MAX
