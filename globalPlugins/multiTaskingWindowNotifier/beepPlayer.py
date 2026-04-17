# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""비프음 재생 전담 모듈.

Phase 3 재설계 요지:
    - 단음 1회 재생으로 통일. 기존 "기본 + 반음 위 추가" 이중 비프 폐기.
    - scope에 따라 반음 변주 적용 여부만 다름.
        * SCOPE_APP: base_idx 기준음을 그대로 (order 무시)
        * SCOPE_WINDOW: base_idx에서 (order-1) 반음만큼 위로 쉬프트
    - 같은 앱의 창들은 base_idx를 공유하므로 "같은 음 가족"으로 들리고, 창 간에는
      반음씩 미세 차이가 나서 구분 가능.
"""

import tones

from logHandler import log

from .constants import BEEP_TABLE, SCOPE_APP, SCOPE_WINDOW

# 반음 비율 = 2^(1/12)
SEMITONE_RATIO = 1.059463

# config가 미주입되거나 테스트 환경일 때 사용할 기본값.
# 실제 런타임 값은 __init__.py에서 config.conf로 읽어 전달.
BEEP_DURATION_MS = 100
BEEP_LEFT_VOL = 50
BEEP_RIGHT_VOL = 50


def play_beep(
    base_idx: int,
    order: int,
    scope: str,
    duration: int = BEEP_DURATION_MS,
    left: int = BEEP_LEFT_VOL,
    right: int = BEEP_RIGHT_VOL,
) -> None:
    """scope/order에 맞춰 단음 1회 비프 재생.

    Args:
        base_idx: BEEP_TABLE 기준음 인덱스 (0 이상). scope=window일 때
            기준 주파수가 되며, 같은 앱 창들은 동일 base_idx를 공유한다.
        order: 같은 appId 창 entry 중 등록 순서 (1부터). scope=app이면 무시.
        scope: SCOPE_APP 또는 SCOPE_WINDOW.
        duration: 비프 지속 시간(ms).
        left, right: 좌/우 채널 볼륨 (0~100).

    동작:
        - 인덱스 범위를 벗어나면 경고 로그 후 무음 (예외 발생 안 함).
        - SCOPE_APP: BEEP_TABLE[base_idx]를 그대로 재생.
        - SCOPE_WINDOW: BEEP_TABLE[base_idx] * SEMITONE_RATIO**(order-1) 재생.
          order=1이면 base_idx 자체. order>=2부터 반음씩 위.
    """
    if not (0 <= base_idx < len(BEEP_TABLE)):
        log.warning(
            f"mtwn: play_beep base_idx={base_idx} out of range (0..{len(BEEP_TABLE) - 1})"
        )
        return

    base_freq = BEEP_TABLE[base_idx]
    if scope == SCOPE_APP or order <= 1:
        freq = base_freq
    else:
        freq = int(base_freq * (SEMITONE_RATIO ** (order - 1)))

    tones.beep(freq, duration, left, right)
