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

경로 분기:
    - `preset["waveform"]` 미지정 → `tones.beep` (classic/pentatonic/fifths)
    - `preset["waveform"]` 지정 → synthEngine.render_wav + nvwave
      (arcade_pop/coin_dash/soft_retro 등 hybrid. Phase 7.5부터 glass_step도 포함)

타이밍 원칙:
    - gap_ms는 NVDA `core.callLater`로 비동기 예약. 내부에서 wx.CallLater를
      거쳐 queueHandler.eventQueue로 진입하므로 NVDA 이벤트 큐와 정합성 유지.
      `event_gainFocus`를 블로킹하지 않는다.
    - settings.CONFSPEC 기본값은 duration=50ms, gap=100ms. 2음 총 150ms
      (duration 50 + gap 100)로 v3 단음 100ms보다 길지만 두 음 변별을 위한
      여유가 필수.

프리셋 폴백:
    미지 preset_id 조회 시 classic 폴백 + 경고는 `presets.get_preset_or_classic`
    이 단일 소유. 본 모듈은 호출만 한다 (스팸 가드 이중화 금지).
"""

import tones

from logHandler import log

from . import presets
from . import settings
from .constants import SCOPE_APP, SCOPE_WINDOW

# synthEngine / nvwave는 지연 import로 감쌈. NVDA 외 환경(단위 테스트)에서는
# nvwave가 없어도 tones.beep 경로만 타면 import 없이 동작. 지연 import 실패는
# 해당 호출에서 tones.beep 폴백으로 흡수.

# duration/gap_ms 기본값 상수는 두지 않는다. settings.CONFSPEC(settings.py)이
# 사용자 조정 가능한 단일 SoT이며, matcher가 항상 settings.get()으로 주입한다.
# 기본값 조정이 필요하면 settings.CONFSPEC의 default=... 한 곳만 고친다.


def _resolve_volume(volume):
    """volume=None이면 현재 설정 조회. 명시된 값이면 그대로 사용(미리듣기 override)."""
    if volume is None:
        try:
            return int(settings.get("beepVolume"))
        except Exception:
            return 100
    return int(volume)


def _play_via_synth(freq: int, duration: int, waveform: str, volume=None) -> None:
    """synthEngine으로 wav 파일 생성 후 nvwave로 비동기 재생. 실패 시 tones.beep 폴백.

    호출 경로: hybrid 프리셋 메타에 `waveform` 키가 있을 때만 진입.
    classic/pentatonic/fifths(waveform 메타 없음)는 tones.beep 경로.

    `volume` (50~150%) 인자. None이면 `settings.beepVolume` 조회. 미리듣기는
    슬라이더 현재값을 override로 전달해 저장 전 즉시 체감.

    폴백 정책 (절대 침묵 금지):
        - synthEngine import 실패(모듈 누락 등): tones.beep(freq) 단순 재생
        - nvwave import 실패: tones.beep 폴백
        - nvwave.playWaveFile 예외(오디오 서비스 중단/디바이스 점유): tones.beep 폴백
    """
    try:
        from . import synthEngine
        import nvwave
    except Exception:
        log.exception("mtwn: synth import failed, falling back to tones.beep")
        tones.beep(freq, duration)
        return
    try:
        vol = _resolve_volume(volume)
        wav_path = synthEngine.render_wav(waveform, freq, duration, volume=vol)
        # asynchronous=True — event_gainFocus 블로킹 방지. NVDA 내부는
        # 다음 호출이 이 재생을 stop()으로 인터럽트(단일 player 구조).
        nvwave.playWaveFile(wav_path, asynchronous=True)
    except Exception:
        log.exception(
            f"mtwn: nvwave play failed (waveform={waveform!r}, freq={freq}), "
            f"falling back to tones.beep"
        )
        tones.beep(freq, duration)


def _play_one_beep(freq: int, duration: int, waveform, volume=None) -> None:
    """단음 재생. waveform이 None이면 tones.beep(volume 무시), 그 외는 nvwave."""
    if waveform is None:
        # classic 계열은 NVDA tones.beep 내부 볼륨 체계를 따른다. beepVolume 슬라이더
        # 영향 받지 않음 (Phase 6 설계 결정 — settings.py CONFSPEC 주석 참조).
        tones.beep(freq, duration)
    else:
        _play_via_synth(freq, duration, waveform, volume=volume)


def _schedule_second_beep(
    freq: int, duration: int, gap_ms: int, waveform=None, volume=None
) -> None:
    """gap_ms 뒤에 단음 재생을 예약.

    NVDA `core.callLater`(core.py:1187-1202)는 `wx.GetApp() is None`일 때만
    NVDANotInitializedError를 던지는데, GlobalPlugin이 실행되는 시점엔 wx.App이
    반드시 존재하므로 실패 경로 없음. NVDA 자체(core.py:783, 975 등)도
    이 함수를 try 없이 사용.

    상위 이벤트 훅(`__init__.py`의 event_* 3종)이 이미 try/except로 예외를
    흡수하지만, 컨텍스트 마커 보존을 위해 여기서도 log.exception 한 겹만 유지.

    waveform=None(기본)이면 tones.beep 경로, 아니면 synthEngine 경로로 분기.
    """
    try:
        import core
        core.callLater(gap_ms, _play_one_beep, freq, duration, waveform, volume)
    except Exception:
        log.exception("mtwn: second beep scheduling failed")


def play_beep(
    app_idx: int,
    tab_idx,
    scope: str,
    duration: int,
    gap_ms: int,
) -> None:
    """앱 비프 a + (옵션) 탭 비프 b 재생. 주파수는 현재 프리셋의 freqs에서 조회.

    Args:
        app_idx: 슬롯 인덱스 (앱 비프 a). 필수. 같은 appId의 모든 항목이 공유.
        tab_idx: 슬롯 인덱스 (탭 비프 b). None이거나 scope=app이면 단음 재생.
        scope: SCOPE_APP 또는 SCOPE_WINDOW. scope=app이면 tab_idx 무시.
        duration: 각 음 지속 시간(ms).
        gap_ms: a 종료 후 b 시작까지 간격(ms).

    동작:
        - 현재 프리셋(`settings.beepPreset`) 조회. 미지 id면 classic 폴백.
        - 프리셋의 `freqs`/`slotCount` 기준 범위 체크.
        - app_idx가 범위 밖이면 경고 로그 후 무음 (예외 없음).
        - tab_idx가 범위 밖이면 경고 로그 + 단음 fallback.
        - SCOPE_APP: app 비프 a 1회.
        - SCOPE_WINDOW + tab_idx: a 즉시 재생 → `core.callLater(gap_ms, beep, b)`.
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
    effective_app_idx = app_idx % size

    freqs = preset["freqs"]
    waveform = preset.get("waveform")  # None이면 tones.beep 경로(classic 계열)

    a_freq = freqs[effective_app_idx]
    _play_one_beep(a_freq, duration, waveform)

    # scope=app 또는 tab_idx 부재 → 단음 종료.
    if scope == SCOPE_APP or tab_idx is None:
        return
    if not isinstance(tab_idx, int):
        log.warning(
            f"mtwn: play_beep invalid tab_idx={tab_idx!r}, "
            f"falling back to single beep"
        )
        return
    effective_tab_idx = tab_idx % size

    b_freq = freqs[effective_tab_idx]
    _schedule_second_beep(b_freq, duration, gap_ms, waveform)


def play_preview(preset_id: str, duration: int, gap_ms: int, volume=None) -> None:
    """설정 패널 "미리듣기(&P)" 버튼이 호출. 프리셋의 previewSlots 2음 재생.

    Args:
        preset_id: PRESETS의 key. 미지 id면 classic 폴백 + 1회 경고.
        duration: 각 음 지속 시간(ms). 보통 settings["beepDuration"].
        gap_ms: 두 음 간격(ms). 보통 settings["beepGapMs"].
        volume: beepVolume(50~150%). None이면 settings 조회. 설정 패널 슬라이더
            현재값을 override로 전달해 저장 전 즉시 체감 가능.

    미리듣기는 실제 재생과 같은 경로를 써서 사용자가 실 사용 시의 소리를 그대로
    듣게 한다. 미리듣기 vs 실제 매칭 경합 정책은 NVDA `core.callLater`의 기본
    동작(이전 콜백 대체 없음)에 의존.
    """
    preset = presets.get_preset_or_classic(preset_id)

    size = preset["slotCount"]
    slot_a, slot_b = preset["previewSlots"]
    # previewSlots는 모듈 로드 시 assert로 검증되므로 범위 밖 케이스는 없음.
    # 그래도 방어적으로 clamp (하위 프리셋이 수동 편집됐을 가능성).
    slot_a = max(0, min(size - 1, slot_a))
    slot_b = max(0, min(size - 1, slot_b))

    freqs = preset["freqs"]
    waveform = preset.get("waveform")
    _play_one_beep(freqs[slot_a], duration, waveform, volume=volume)
    _schedule_second_beep(freqs[slot_b], duration, gap_ms, waveform, volume=volume)
