# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""비프음 재생 전담 모듈."""

import wx
import tones

from logHandler import log

from .constants import BEEP_TABLE

# 반음 비율 = 2^(1/12)
SEMITONE_RATIO = 1.059463

# config가 미주입되거나 테스트 환경일 때 사용할 기본값.
# 실제 런타임 값은 __init__.py에서 config.conf로 읽어 전달.
BEEP_DURATION_MS = 100
BEEP_LEFT_VOL = 50
BEEP_RIGHT_VOL = 50

# 같은 앱의 2번째 창 비프 지연 (ms)
SECONDARY_BEEP_DELAY_MS = 10


def play_window_beep(
    idx: int,
    order: int,
    duration: int = BEEP_DURATION_MS,
    left: int = BEEP_LEFT_VOL,
    right: int = BEEP_RIGHT_VOL,
) -> None:
    """창 인덱스와 같은 앱 내 등록 순서에 맞춰 비프음 재생.

    Args:
        idx: BEEP_TABLE 인덱스 (0부터)
        order: 같은 appId 항목 중 현재 창의 등록 순서 (1부터)
        duration: 비프음 지속 시간(ms). 미지정 시 BEEP_DURATION_MS.
        left: 좌측 볼륨 (0~100). 미지정 시 BEEP_LEFT_VOL.
        right: 우측 볼륨 (0~100). 미지정 시 BEEP_RIGHT_VOL.

    동작:
        - 기본음을 즉시 재생.
        - order >= 2이면 반음씩 높은 음을 wx.CallLater로 지연 재생 (비동기).
    """
    if not (0 <= idx < len(BEEP_TABLE)):
        log.warning(
            f"mtwn: play_window_beep idx={idx} out of range (0..{len(BEEP_TABLE) - 1})"
        )
        return

    base_freq = BEEP_TABLE[idx]
    tones.beep(base_freq, duration, left, right)

    if order > 1:
        higher_freq = int(base_freq * (SEMITONE_RATIO ** (order - 1)))
        wx.CallLater(
            SECONDARY_BEEP_DELAY_MS,
            tones.beep,
            higher_freq,
            duration,
            left,
            right,
        )
