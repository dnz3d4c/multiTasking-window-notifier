# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""비프음 재생 전담 모듈."""

import wx
import tones

from .constants import BEEP_TABLE

# 반음 비율 = 2^(1/12)
SEMITONE_RATIO = 1.059463

BEEP_DURATION_MS = 50
BEEP_LEFT_VOL = 30
BEEP_RIGHT_VOL = 30

# 같은 앱의 2번째 창 비프 지연 (ms)
SECONDARY_BEEP_DELAY_MS = 10


def play_window_beep(idx: int, order: int) -> None:
    """창 인덱스와 같은 앱 내 등록 순서에 맞춰 비프음 재생.

    Args:
        idx: BEEP_TABLE 인덱스 (0부터)
        order: 같은 appId 항목 중 현재 창의 등록 순서 (1부터)

    동작:
        - 기본음을 즉시 재생.
        - order >= 2이면 반음씩 높은 음을 wx.CallLater로 지연 재생 (비동기).
    """
    if not (0 <= idx < len(BEEP_TABLE)):
        return

    base_freq = BEEP_TABLE[idx]
    tones.beep(base_freq, BEEP_DURATION_MS, BEEP_LEFT_VOL, BEEP_RIGHT_VOL)

    if order > 1:
        higher_freq = int(base_freq * (SEMITONE_RATIO ** (order - 1)))
        wx.CallLater(
            SECONDARY_BEEP_DELAY_MS,
            tones.beep,
            higher_freq,
            BEEP_DURATION_MS,
            BEEP_LEFT_VOL,
            BEEP_RIGHT_VOL,
        )
