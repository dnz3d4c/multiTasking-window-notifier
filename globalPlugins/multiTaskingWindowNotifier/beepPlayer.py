# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""비프음 재생 전담 모듈.

v4 2차원 비프:
    - scope=app 매칭은 app_idx 단음 1회 재생.
    - scope=window 매칭은 app_idx(a) 재생 후 gap_ms 뒤에 tab_idx(b) 재생.
      a는 같은 appId의 모든 window가 공유 → "이 앱이다" 식별.
      b는 같은 appId 내에서 고유 → "이 탭이다" 식별.
    - a와 b가 순차로 재생되므로 절대 비교 대신 상대 비교가 되어 작은 간격도
      충분히 변별된다.

타이밍 원칙:
    - 2음 a+silence(gap_ms)+b를 한 번에 OS 오디오 큐에 enqueue한다. 첫 a는
      `tones.beep`(NVDA 표준 경로 — `decide_beep` 확장 포인트 호환)으로 발화하고,
      직후 `tones.player.feed(silence + b_buf)`를 호출해 silence와 b를 큐에
      append한다. `nvwave.WavePlayer.feed` docstring(`nvwave.py:321-330`)이
      "uninterrupted playback as long as a new chunk is fed before the previous
      chunk has finished playing"을 보장하므로 OS 오디오 스택이 정확한 타이밍에
      자체 재생한다.
    - 핵심 효과: NVDA 메인 스레드 freeze(watchdog 0.5초+)에도 b 발화가 정확히
      a 후 gap_ms에 일관 발화. 이전 `core.callLater(gap_ms, tones.beep)` 경로는
      wx 타이머 + queueHandler.eventQueue 두 단계 모두 메인 스레드 의존이라
      freeze 중 b가 600ms+로 밀리는 회귀 발생.
    - settings.CONFSPEC 기본값은 duration=50ms, gap=100ms.

Phase 11 "tones.beep 단일 경로" 원칙 부분 완화:
    Phase 11(`ef9b09e`)은 프리셋 다양성 위한 synthEngine + nvwave.playWaveFile
    파일 캐시 경로를 제거하면서 단일 경로 원칙을 명문화했다. 본 모듈의 b 우회는
    동기가 다르다 — "타이밍 정확성"이라는 별개 요구이며 `tones.player.feed`는
    NVDA 자체가 speech 합성에서 매 발화 사용하는 표준 API다. 첫 a는 여전히
    `tones.beep`을 거치므로 `decide_beep` 확장 포인트는 a 시점 1회 작동한다.

decide_beep 일관성:
    `tones.beep`(a 호출)이 `decide_beep` 확장 포인트로 취소되면 a는 무음 반환된다
    (`tones.py:71-81`). 이 경우 b도 `tones.player.feed`로 직접 enqueue하면 로컬
    비프 차단 의도를 우회한다. b enqueue 전에 같은 `decide_beep.decide()`를 한 번
    더 호출해 a/b 결정을 동기화한다 — 비프 음소거/원격 제어 핸들러가 a를 막으면 b도
    같이 막힌다.

NVDA 버전 호환:
    NVDA 2025.2(commit `26d7cf738`, 2025-02-21)에서 `NVDAHelper.py` 단일
    모듈이 `NVDAHelper/` 패키지로 분리되며 generateBeep이 `NVDAHelper.localLib`
    서브모듈로 이동했다. 그 이전(2019.3 ~ 2025.1.x)에서는 `from NVDAHelper
    import generateBeep`이 정답. manifest minimumNVDAVersion=2019.3.0 약속
    유지 위해 두 import 경로를 모두 시도한다. 최초 호출 시 1회 resolve해서
    모듈 캐시(`_generate_beep_fn`)에 보관 — lookup 비용 0.

    try 순서는 **신경로 우선**. 2025.2+의 `NVDAHelper.__init__.py`가 구경로
    호환을 위해 `_deprecate.MovedSymbol`로 `generateBeep`을 backward-compat
    re-export하는데, 호출 시마다 `log.warning(..., stack_info=True)`를
    찍는다(`_deprecate.py:166-180`). 신경로를 먼저 시도해 2025.2+ 환경에서
    이 deprecation warning을 회피한다.

폴백:
    위 두 경로 모두 실패(미래 NVDA 구조 재변경) 또는 `tones.player`가
    None(NVDA 종료/재로드 직전) 시 기존 `core.callLater` 경로로 회귀해
    동작 자체는 보존한다. user-facing 영향은 callLater 회귀(freeze 시 b
    지연 가능)만이고 무음 회귀는 없다.

프리셋 폴백:
    미지 preset_id 조회 시 classic 폴백 + 경고는 `presets.get_preset_or_classic`
    이 단일 소유. 본 모듈은 호출만 한다 (스팸 가드 이중화 금지).
"""

from ctypes import create_string_buffer

import core
import tones

from logHandler import log

from . import presets
from . import settings
from .constants import SCOPE_APP, SCOPE_WINDOW

# duration/gap_ms 기본값 상수는 두지 않는다. settings.CONFSPEC(settings.py)이
# 사용자 조정 가능한 단일 SoT이며, matcher가 항상 settings.get()으로 주입한다.
# 기본값 조정이 필요하면 settings.CONFSPEC의 default=... 한 곳만 고친다.

# silence 버퍼 1ms당 바이트 수: tones.player가 stereo 16-bit @ 44100 Hz로 초기화됨
# (`tones.py:21-31` initialize). 채널 2 × bytes_per_sample 2 × samplesPerSec / 1000.
# 16-bit signed PCM zero-fill = 무음(Python `bytes(N)`이 zero 보장).
_SILENCE_BYTES_PER_MS = tones.SAMPLE_RATE * 2 * 2 // 1000  # 176

# generateBeep 함수 lazy resolve 캐시. 두 import 경로(NVDA 2025.2+ 신경로 /
# 2025.1.x 이하 구경로)를 첫 호출 시 한 번만 시도하고 결과를 보관.
# `_resolved`로 "아직 resolve 안 됨"과 "resolve 시도했으나 실패(None)"를 구분.
_generate_beep_fn = None
_generate_beep_resolved = False

# `_play_two_tone_burst` 폴백 진입 1회 후 후속 발생은 debugWarning으로 격하.
# 이유: resolve 실패 환경(미래 NVDA 호환 깨짐)에선 매 비프마다 폴백 → log.exception
# 스팸으로 다른 진단 로그 가린다. 첫 발생 stack은 보존, 이후는 진단용 한 줄만.
# `presets.get_preset_or_classic` 단일 소유 가드와 동일 컨벤션.
_two_tone_fallback_logged = False


def _resolve_generate_beep():
    """NVDA 버전별 generateBeep import 경로를 한 번만 resolve해서 캐시.

    NVDA 2025.2+: `NVDAHelper.localLib.generateBeep`
    NVDA 2019.3 ~ 2025.1.x: `NVDAHelper.generateBeep`

    둘 다 실패하면 None 캐시 → 호출자가 callLater 폴백으로 자연 회귀.
    """
    global _generate_beep_fn, _generate_beep_resolved
    if _generate_beep_resolved:
        return _generate_beep_fn
    fn = None
    try:
        from NVDAHelper.localLib import generateBeep
        fn = generateBeep
    except ImportError:
        try:
            from NVDAHelper import generateBeep
            fn = generateBeep
        except ImportError:
            log.warning(
                "mtwn: generateBeep import failed on both NVDAHelper.localLib "
                "(NVDA 2025.2+) and NVDAHelper (<= 2025.1.x); "
                "two-tone burst will use callLater fallback"
            )
    _generate_beep_fn = fn
    _generate_beep_resolved = True
    return _generate_beep_fn


def _play_two_tone_burst(a_freq: int, b_freq: int, duration: int, gap_ms: int) -> None:
    """a + silence(gap_ms) + b를 한 번에 OS 오디오 큐에 enqueue.

    1단계 — `tones.beep(a)` 호출. 내부에서 `player.stop()` + `player.feed(a_buf)`
    실행. `decide_beep` 확장 포인트 통과.

    2단계 — `tones.player.feed(silence + b_buf)` 직접 호출. `tones.beep`이
    `player.stop()` 후 `feed(a_buf)`로 끝난 직후라 우리 feed는 stop 없이 큐에
    append되어 OS 오디오 스택이 a → silence → b를 끊김 없이 연속 재생한다.

    실패 시 기존 `core.callLater` 경로로 폴백해 동작 자체는 보존.
    """
    if tones.player is None:
        # NVDA 종료/재로드 직전 atexit이 player를 None 처리(`tones.py:39-42`).
        return
    tones.beep(a_freq, duration)
    # decide_beep가 a를 취소했으면 b도 같이 차단 — 음소거/원격제어 핸들러 일관성.
    # `tones.beep` 인자와 동일하게 left=50/right=50/isSpeechBeepCommand=False.
    if not tones.decide_beep.decide(
        hz=b_freq, length=duration, left=50, right=50, isSpeechBeepCommand=False,
    ):
        return
    try:
        # generateBeep는 모듈 첫 호출 시 1회 resolve 후 캐시(NVDA 버전별 경로 차이).
        generateBeep = _resolve_generate_beep()
        if generateBeep is None:
            raise RuntimeError("generateBeep unavailable on this NVDA version")
        silence_buf = bytes(gap_ms * _SILENCE_BYTES_PER_MS)
        b_size = generateBeep(None, b_freq, duration, 50, 50)
        b_buf = create_string_buffer(b_size)
        generateBeep(b_buf, b_freq, duration, 50, 50)
        tones.player.feed(silence_buf + b_buf.raw)
    except Exception:
        global _two_tone_fallback_logged
        if not _two_tone_fallback_logged:
            log.exception(
                "mtwn: second beep enqueue failed; falling back to callLater "
                "(further occurrences logged at debug)"
            )
            _two_tone_fallback_logged = True
        else:
            log.debugWarning(
                "mtwn: second beep enqueue failed (suppressed; see earlier exception)"
            )
        try:
            core.callLater(gap_ms, tones.beep, b_freq, duration)
        except Exception:
            log.exception("mtwn: second beep callLater fallback also failed")


def play_beep(
    app_idx: int,
    tab_idx,
    scope: str,
    duration: int,
    gap_ms: int,
    *,
    omit_app_beep: bool = False,
) -> None:
    """앱 비프 a + (옵션) 탭 비프 b 재생. 주파수는 현재 프리셋의 freqs에서 조회.

    Args:
        app_idx: 슬롯 인덱스 (앱 비프 a). 필수. 같은 appId의 모든 항목이 공유.
        tab_idx: 슬롯 인덱스 (탭 비프 b). None이거나 scope=app이면 단음 재생.
        scope: SCOPE_APP 또는 SCOPE_WINDOW. scope=app이면 tab_idx 무시.
        duration: 각 음 지속 시간(ms).
        gap_ms: a 종료 후 b 시작까지 간격(ms).
        omit_app_beep: 같은 앱 내부 탭 전환에서 호출자가 True를 주입. scope=WINDOW
            + tab_idx 있음일 때만 발효 — a를 생략하고 b만 단음 재생. 다른 케이스
            (scope=APP, tab_idx=None)에서는 무시되어 기본 단음 a가 그대로 재생됨
            (무음 회귀 방지).

    동작:
        - 현재 프리셋(`settings.beepPreset`) 조회. 미지 id면 classic 폴백.
        - 프리셋의 `freqs`/`slotCount` 기준 범위 체크.
        - app_idx가 범위 밖이면 경고 로그 후 무음 (예외 없음).
        - tab_idx가 범위 밖이면 경고 로그 + 단음 fallback.
        - omit_app_beep=True + SCOPE_WINDOW + tab_idx: b 단음만 재생.
        - SCOPE_APP: app 비프 a 1회.
        - SCOPE_WINDOW + tab_idx: `_play_two_tone_burst`로 a + silence + b 일괄 큐잉.
    """
    preset_id = settings.get("beepPreset")
    preset = presets.get_preset_or_classic(preset_id)
    size = preset["slotCount"]

    # stored idx는 MAX_ITEMS(=128) 공간에서 배정되고 프리셋 slotCount는 프리셋마다
    # 정의(현재 모두 35). 재생 시점 modulo wrap으로 현재 프리셋 범위에 맞춤.
    # stored idx 자체는 보존돼 프리셋 왕복 시 원복 가능. 음수 방어는 Python의 %
    # 연산자가 양수 결과 보장(-1 % 35 == 34).
    if not isinstance(app_idx, int) or size <= 0:
        log.warning(
            f"mtwn: play_beep invalid app_idx={app_idx!r} or slotCount={size} "
            f"for preset={preset['id']!r}"
        )
        return

    freqs = preset["freqs"]

    # 같은 앱 내부 탭 전환: a 생략 + b만 단음. tab_idx 유효성은 아래 SCOPE_WINDOW
    # 분기와 동일한 검증 적용.
    if omit_app_beep and scope == SCOPE_WINDOW and tab_idx is not None:
        if not isinstance(tab_idx, int):
            log.warning(
                f"mtwn: play_beep invalid tab_idx={tab_idx!r} (intra-app), "
                f"falling back to silence"
            )
            return
        tones.beep(freqs[tab_idx % size], duration)
        return

    effective_app_idx = app_idx % size

    # scope=app 또는 tab_idx 부재 → 단음 종료.
    if scope == SCOPE_APP or tab_idx is None:
        tones.beep(freqs[effective_app_idx], duration)
        return
    if not isinstance(tab_idx, int):
        log.warning(
            f"mtwn: play_beep invalid tab_idx={tab_idx!r}, "
            f"falling back to single beep"
        )
        tones.beep(freqs[effective_app_idx], duration)
        return
    effective_tab_idx = tab_idx % size

    _play_two_tone_burst(
        freqs[effective_app_idx], freqs[effective_tab_idx], duration, gap_ms,
    )


def play_preview(preset_id: str, duration: int, gap_ms: int) -> None:
    """설정 패널 "미리듣기(&P)" 버튼이 호출. 프리셋의 previewSlots 2음 재생.

    Args:
        preset_id: PRESETS의 key. 미지 id면 classic 폴백 + 1회 경고.
        duration: 각 음 지속 시간(ms). 보통 settings["beepDuration"].
        gap_ms: 두 음 간격(ms). 보통 settings["beepGapMs"].

    미리듣기는 실제 재생과 같은 경로(`_play_two_tone_burst`)를 써서 사용자가 실
    사용 시의 소리를 그대로 듣게 한다. 미리듣기 vs 실제 매칭 경합은 OS 오디오
    큐가 stop+feed 시 직전 큐를 자연 해체하는 기본 동작에 의존.
    """
    preset = presets.get_preset_or_classic(preset_id)

    size = preset["slotCount"]
    slot_a, slot_b = preset["previewSlots"]
    # previewSlots는 모듈 로드 시 assert로 검증되므로 범위 밖 케이스는 없음.
    # 그래도 방어적으로 clamp (하위 프리셋이 수동 편집됐을 가능성).
    slot_a = max(0, min(size - 1, slot_a))
    slot_b = max(0, min(size - 1, slot_b))

    freqs = preset["freqs"]
    _play_two_tone_burst(freqs[slot_a], freqs[slot_b], duration, gap_ms)
