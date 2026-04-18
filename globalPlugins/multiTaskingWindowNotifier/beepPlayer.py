# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""비프음 재생 전담 모듈.

v4 2차원 비프:
    - scope=app 매칭은 app_idx 단음 1회 재생.
    - scope=window 매칭은 app_idx(a) 재생 후 gap_ms 뒤에 tab_idx(b) 재생.
      a는 같은 appId의 모든 window가 공유 → "이 앱이다" 식별.
      b는 같은 appId 내에서 고유 → "이 탭이다" 식별.
    - a와 b가 순차로 재생되므로 절대 비교 대신 상대 비교가 되어 반음 간격도
      충분히 변별된다. 이론 조합 64 × 64 = 4096.

타이밍 원칙:
    - gap_ms는 `wx.CallLater`로 비동기 예약. NVDA 메인 GUI 스레드에서 실행되며
      `event_gainFocus`를 블로킹하지 않는다.
    - duration 기본값은 50ms. 2음 총 150ms(duration 50 + gap 100)로 v3 단음
      100ms보다 길지만 두 음 변별을 위한 여유가 필수.
"""

import tones

from logHandler import log

from .constants import BEEP_TABLE, BEEP_TABLE_SIZE, SCOPE_APP, SCOPE_WINDOW

# config가 미주입되거나 테스트 환경일 때 사용할 기본값.
# 실제 런타임 값은 __init__.py에서 config.conf로 읽어 전달.
BEEP_DURATION_MS = 50
# 앱음과 탭음 사이 간격. 15ms(초기값) → 60ms → 100ms로 두 차례 상향.
# 60ms에서도 "딩동" 한 덩어리처럼 뭉쳐 들린다는 실전 피드백이 있어
# 100ms로 재조정. duration 50ms + gap 100ms = 총 150ms로 두 음이
# 뚜렷이 "딩 … 동"으로 분리되면서도 Alt+Tab 체감 속도는 유지된다.
BEEP_GAP_MS = 100


def _schedule_second_beep(freq: int, duration: int, gap_ms: int) -> None:
    """gap_ms 뒤에 tones.beep을 호출한다.

    우선순위:
        ① NVDA `core.callLater` — NVDA 이벤트 큐와 정합성 보장, 메인 스레드 판별
           자동, `wx.GetApp() is None` 가드 포함. 권장.
        ② `wx.CallLater` — core 모듈 부재(테스트/스텁) 시 폴백.
        ③ 동기 호출 — wx도 없을 때 (테스트 격리용). 실제 gap 없이 순차 실행.
    """
    try:
        import core
        core.callLater(gap_ms, tones.beep, freq, duration)
        return
    except Exception:
        log.debug("mtwn: core.callLater unavailable, falling back to wx")
    try:
        import wx
        wx.CallLater(gap_ms, tones.beep, freq, duration)
        return
    except Exception:
        log.debug("mtwn: wx.CallLater unavailable, second beep fired synchronously")
    try:
        tones.beep(freq, duration)
    except Exception:
        log.exception("mtwn: second beep fallback failed")


def play_beep(
    app_idx: int,
    tab_idx=None,
    scope: str = SCOPE_APP,
    duration: int = BEEP_DURATION_MS,
    gap_ms: int = BEEP_GAP_MS,
) -> None:
    """앱 비프 a + (옵션) 탭 비프 b 재생.

    Args:
        app_idx: BEEP_TABLE 인덱스 (앱 비프 a). 필수. 같은 appId의 모든 항목이
            이 값을 공유한다.
        tab_idx: BEEP_TABLE 인덱스 (탭 비프 b). None이거나 scope=app이면
            단음 재생. 그 외는 a → gap → b 2음 재생.
        scope: SCOPE_APP 또는 SCOPE_WINDOW. scope=app이면 tab_idx가 주어져도
            무시 (단음).
        duration: 각 음 지속 시간(ms). 2음 재생 시 a와 b 모두 같은 duration.
        gap_ms: a 종료 후 b 시작까지 간격(ms). scope=app/tab_idx=None이면 무시.

    동작:
        - app_idx가 BEEP_TABLE 범위를 벗어나면 경고 로그 후 무음 (예외 없음).
        - tab_idx가 범위를 벗어나면 경고 로그 + 단음 fallback.
        - SCOPE_APP: `tones.beep(a, duration)` 1회.
        - SCOPE_WINDOW + tab_idx: a 즉시 재생 → `core.callLater(gap_ms, beep, b)`.
    """
    if not (0 <= app_idx < BEEP_TABLE_SIZE):
        log.warning(
            f"mtwn: play_beep app_idx={app_idx} out of range (0..{BEEP_TABLE_SIZE - 1})"
        )
        return

    a_freq = BEEP_TABLE[app_idx]
    tones.beep(a_freq, duration)

    # scope=app 또는 tab_idx 부재 → 단음 종료.
    if scope == SCOPE_APP or tab_idx is None:
        return
    if not (0 <= tab_idx < BEEP_TABLE_SIZE):
        log.warning(
            f"mtwn: play_beep tab_idx={tab_idx} out of range (0..{BEEP_TABLE_SIZE - 1}), "
            f"falling back to single beep"
        )
        return

    b_freq = BEEP_TABLE[tab_idx]
    _schedule_second_beep(b_freq, duration, gap_ms)
