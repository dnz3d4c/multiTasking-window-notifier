# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""프리셋 데이터 단일 소유자 모듈 (Phase 7.1 신설).

여러 모듈(constants/synthEngine/beepPlayer/settings/settingsPanel)에 산재했던
프리셋 관련 로직 — dict 정의, freqs 빌더, 부팅 불변식 assert, 폴백 경고,
폐기 프리셋 감지·마이그레이션 — 을 한 모듈로 응집한다.

원칙:
    - 프리셋 데이터 소유자는 이 모듈뿐. 다른 모듈은 공개 API만 호출.
    - 의존 방향: presets.py → constants.py 만 허용. settings/beepPlayer/
      synthEngine을 import하지 않는다(역전 금지).
    - 공개 API: PRESETS, CLASSIC_PRESET_ID, get_preset, get_preset_or_classic,
      is_deprecated, migrate_deprecated_preset.

프리셋 dict 포맷:
    id                  — 내부 식별자(settings.beepPreset에 저장)
    nameLabel           — UI 노출 이름 (raw str; UI 레이어가 _() 번역)
    type                — "tonal" | "hybrid"
    slotCount           — 슬롯 수. 재생 시점 effective_idx = stored_idx % slotCount
    recommendedMaxApps  — 이 프리셋에서 변별 가능한 앱 수 (UI 경고 기준)
    optIn               — True면 기본 라인업 불포함 (현재 모든 프리셋 False)
    previewSlots        — "미리듣기(&P)" 버튼이 재생할 대표 슬롯 인덱스 2개
    descriptionLabel    — ListBox focus 시 표시되는 짧은 설명 (raw str)
    freqs               — slotCount 길이의 정수 주파수(Hz) 리스트
    durationMs / gapMs  — 2음 순차 재생의 각 음 길이/간격
    suppressRepeat      — 최근 0.3초 내 같은 키 재매칭 시 tab음 생략
    octaveVariation     — 같은 앱 재진입 시 tab idx ±7 clip
    gain                — 재생 음량 계수 (nvwave 경로에서 적용)
    waveform            — (hybrid 전용) nvwave+synthEngine.render_wav 경로 진입 트리거

Phase 7.1에서 철회된 프리셋(drum_kit/lazer_pack/eight_bit_jump/daily_life/
humor_pack)은 이 모듈에 존재하지 않는다. 사용자 저장값에 그 id가 남아있어도
`migrate_deprecated_preset`이 silent write로 CLASSIC_PRESET_ID로 돌린다.
"""

from logHandler import log

from .constants import BEEP_TABLE, MAX_ITEMS


# 미지/폐기 id 폴백의 목표. settings.beepPreset이 삭제/손상된 경우에도 항상 이
# id의 프리셋으로 재생되어야 한다.
CLASSIC_PRESET_ID = "classic"


# Phase 4~6 synthSpecs 5종(Phase 7에서 철회) + Phase 3/7.5 날카로운 hybrid 3종
# (Phase 8에서 철회). 사용자 저장값에 남아 있을 수 있어 마이그레이션이 감지.
# 새 철회 대상이 생기면 여기에 추가.
_DEPRECATED_PRESET_IDS = frozenset({
    # Phase 4~6 synthSpecs
    "drum_kit",
    "lazer_pack",
    "eight_bit_jump",
    "daily_life",
    "humor_pack",
    # Phase 8: 날카로운 hybrid 파형 3종
    "arcade_pop",
    "coin_dash",
    "glass_step",
})


# ---------------------------------------------------------------------------
# freqs 빌더 (모듈 로드 시 1회 호출)
# ---------------------------------------------------------------------------

def _build_fifths_freqs():
    """BEEP_TABLE을 완전5도 진행(C→G→D→A→E→B→F) 순서로 재배열.

    각 옥타브 안에서 C major 7음 순서(C D E F G A B, 인덱스 0~6)를
    [0, 4, 1, 5, 2, 6, 3](C G D A E B F) 순서로 재배치한다. 주파수 자체는
    BEEP_TABLE과 동일하지만 슬롯 순서가 5도 진행이라 인접 슬롯이 완전5도 또는
    완전4도로 밝게 느껴져 "팡파레(fanfare)" 캐릭터가 된다.

    `B→F`는 감5도(tritone)로 예외 구간이지만 diatonic 스케일 내에서는 불가피.
    """
    fifths_order = (0, 4, 1, 5, 2, 6, 3)  # C G D A E B F
    freqs = []
    for octave_idx in range(5):  # BEEP_TABLE이 5옥타브(C3~B7)
        base = octave_idx * 7
        for offset in fifths_order:
            freqs.append(BEEP_TABLE[base + offset])
    return freqs


# Pentatonic Calm: C D E G A 5음계 × 7옥타브 = 35.
# C2(65Hz)~A8(7040Hz) 범위. 기존 BEEP_TABLE(C3~B7)보다 양쪽으로 확장된 저/고역을
# 포함하나 실제 사용자가 등록하는 앱 수는 ~20개 수준이라 극단 슬롯은 거의
# 닿지 않는다. "Calm" 캐릭터 유지.
_PENTATONIC_FREQS = [
    65, 73, 82, 98, 110,          # C2 D2 E2 G2 A2
    130, 146, 164, 196, 220,      # C3 D3 E3 G3 A3
    261, 293, 329, 392, 440,      # C4 D4 E4 G4 A4
    523, 587, 659, 784, 880,      # C5 D5 E5 G5 A5
    1047, 1175, 1319, 1568, 1760, # C6 D6 E6 G6 A6
    2093, 2349, 2637, 3136, 3520, # C7 D7 E7 G7 A7
    4186, 4698, 5274, 6271, 7040, # C8 D8 E8 G8 A8
]


# Moss Bell: A 자연단음계 7음(A B C D E F G) × 5옥타브 = 35.
# A2(110Hz) ~ G7(3136Hz). classic과 음 개수·옥타브는 같지만 시작음과 음정
# 구조가 다르다 — "밝은 도레미"에 피로한 사용자의 애조 대체재.
# 반음이 있어(B→C, E→F) pentatonic의 "중립적 차분함"과 구별된다.
_A_MINOR_FREQS = [
    110, 123, 130, 146, 164, 174, 196,       # A2 B2 C3 D3 E3 F3 G3
    220, 246, 261, 293, 329, 349, 392,       # A3 B3 C4 D4 E4 F4 G4
    440, 493, 523, 587, 659, 698, 784,       # A4 B4 C5 D5 E5 F5 G5
    880, 987, 1047, 1175, 1319, 1397, 1568,  # A5 B5 C6 D6 E6 F6 G6
    1760, 1976, 2093, 2349, 2637, 2794, 3136,  # A6 B6 C7 D7 E7 F7 G7
]


# ---------------------------------------------------------------------------
# 프리셋 dict — Phase 8 기준 5개
# (classic/pentatonic/fifths + soft_retro + moss_bell)
# ---------------------------------------------------------------------------

PRESETS = {
    "classic": {
        "id": "classic",
        "nameLabel": "Classic Tones",
        "type": "tonal",
        "slotCount": 35,
        "recommendedMaxApps": 35,
        "optIn": False,
        "previewSlots": (0, 14),  # C3, C5
        "descriptionLabel": "C 장조 35음 (도·레·미·파·솔·라·시 × 5옥타브). 현행 기본.",
        "freqs": BEEP_TABLE,  # read-only 공유 참조
        "durationMs": 50,
        "gapMs": 100,
        "suppressRepeat": False,
        "octaveVariation": False,
        "gain": 1.0,
    },
    "pentatonic": {
        "id": "pentatonic",
        "nameLabel": "Pentatonic Calm",
        "type": "tonal",
        "slotCount": 35,
        "recommendedMaxApps": 35,
        "optIn": False,
        "previewSlots": (5, 20),  # C3, C6
        "descriptionLabel": "5음계(C D E G A) × 7옥타브. 같은 창 빠른 재진입 시 탭음을 생략하고 옥타브 변주로 반복감을 완화.",
        "freqs": _PENTATONIC_FREQS,
        "durationMs": 50,
        "gapMs": 100,
        # "Calm" 캐릭터를 살리는 두 기능을 기본 on.
        #   suppressRepeat — 같은 매칭 키가 _SUPPRESS_REPEAT_SEC(0.3s) 내로 다시 오면
        #       탭음 생략(앱음만). Alt+Tab 연타/NVDA 이벤트 근접 재발화 시 피로 감소.
        #   octaveVariation — 같은 key 재진입마다 탭 idx를 ±7(=1옥타브) 토글해
        #       "같은 창인데 같은 소리"의 단조로움을 완화. 범위 밖은 clip.
        "suppressRepeat": True,
        "octaveVariation": True,
        "gain": 1.0,
    },
    "fifths": {
        "id": "fifths",
        "nameLabel": "Fifths Fanfare",
        "type": "tonal",
        "slotCount": 35,
        "recommendedMaxApps": 35,
        "optIn": False,
        "previewSlots": (0, 7),  # C3, C4
        "descriptionLabel": "완전5도 진행(C-G-D-A-E-B-F) × 5옥타브. 팡파레 느낌.",
        "freqs": _build_fifths_freqs(),
        "durationMs": 50,
        "gapMs": 100,
        "suppressRepeat": False,
        "octaveVariation": False,
        "gain": 1.0,
    },
    # Phase 3 hybrid — nvwave + synthEngine.render_wav 경로. `waveform` 키
    # 존재가 신 경로 진입 트리거. freqs는 BEEP_TABLE(C3~B7)을 공유해 음정 구조를
    # classic과 동일하게 유지하되 음색만 달라진다.
    # Phase 8: pulse50/pulse25 기반 프리셋(arcade_pop/coin_dash)은 날카로움 피드백
    # 으로 제거. soft_retro(triangle)만 유지 — triangle은 배음 감쇠가 1/n²로
    # 빠른 부드러운 파형.
    "soft_retro": {
        "id": "soft_retro",
        "nameLabel": "Soft Retro",
        "type": "hybrid",
        "slotCount": 35,
        "recommendedMaxApps": 35,
        "optIn": False,
        "previewSlots": (0, 14),
        "descriptionLabel": "삼각파. 부드럽고 따뜻한 8비트 배경음 느낌.",
        "freqs": BEEP_TABLE,
        "waveform": "triangle",
        "durationMs": 50,
        "gapMs": 100,
        "suppressRepeat": False,
        "octaveVariation": False,
        "gain": 1.0,
    },
    # Phase 7.5: 정서축(애조)을 채우는 tonal 신규. classic/pentatonic/fifths가
    # 모두 밝은 장조 또는 중립이라 애조가 비어있었다.
    # (Phase 8에서 같이 추가됐던 glass_step[saw/whole-tone]은 날카로움 피드백
    # 으로 제거.)
    "moss_bell": {
        "id": "moss_bell",
        "nameLabel": "Moss Bell",
        "type": "tonal",
        "slotCount": 35,
        "recommendedMaxApps": 35,
        "optIn": False,
        "previewSlots": (0, 14),  # A2, A4
        "descriptionLabel": "A 자연단음계 7음 × 5옥타브. 차분한 애조.",
        "freqs": _A_MINOR_FREQS,
        "durationMs": 50,
        "gapMs": 100,
        "suppressRepeat": False,
        "octaveVariation": False,
        "gain": 1.0,
    },
}


# ---------------------------------------------------------------------------
# 부팅 불변식 검증 (모듈 로드 시 1회)
# ---------------------------------------------------------------------------
#
# 프리셋 dict에 오타/누락이 생기면 ImportError로 바로 드러나게 해 런타임 KeyError
# 로 이어지지 않게 한다. 런타임 비용 없음.
for _pid, _p in PRESETS.items():
    assert _p["id"] == _pid, f"preset dict id mismatch: {_pid!r} vs {_p['id']!r}"
    assert 1 <= _p["slotCount"] <= MAX_ITEMS, (
        f"preset {_pid!r} slotCount={_p['slotCount']} out of 1..{MAX_ITEMS}"
    )
    _freqs = _p["freqs"]
    assert len(_freqs) == _p["slotCount"], (
        f"preset {_pid!r} freqs len={len(_freqs)} != slotCount={_p['slotCount']}"
    )
    for _ps in _p["previewSlots"]:
        assert 0 <= _ps < _p["slotCount"], (
            f"preset {_pid!r} previewSlot {_ps} out of 0..{_p['slotCount'] - 1}"
        )
assert CLASSIC_PRESET_ID in PRESETS, "CLASSIC_PRESET_ID fallback target missing"


# ---------------------------------------------------------------------------
# 공개 API — 다른 모듈이 프리셋을 조회/감지하는 유일한 진입점
# ---------------------------------------------------------------------------

# 미지 preset_id에 대한 경고 스팸 방지용. 같은 잘못된 id로 매 focus마다 경고가
# 쏟아지면 로그가 무용지물이 되므로 id별로 1회만 기록한다.
_warned_preset_ids: set = set()


def get_preset(preset_id: str):
    """id로 프리셋 dict 조회. 없으면 None.

    폴백이 필요한 호출부는 `get_preset_or_classic`를 쓴다. 이 함수는 None을
    그대로 반환해 호출부가 "없음"을 능동적으로 처리해야 하는 경우에만.
    """
    return PRESETS.get(preset_id)


def get_preset_or_classic(preset_id: str) -> dict:
    """id 조회 실패 시 classic 프리셋으로 폴백 + 1회 log.warning.

    matcher/beepPlayer의 핫 패스에서 호출되므로 경고는 id별 1회만. 같은 잘못된
    id가 매 매칭마다 로그 폭주하지 않도록 `_warned_preset_ids` set으로 dedup.

    호출부가 폴백 여부를 알 필요 없이 항상 정상 dict를 받는다.
    """
    preset = PRESETS.get(preset_id)
    if preset is not None:
        return preset
    if preset_id not in _warned_preset_ids:
        _warned_preset_ids.add(preset_id)
        log.warning(
            f"mtwn: unknown beepPreset={preset_id!r}, falling back to "
            f"{CLASSIC_PRESET_ID!r}"
        )
    return PRESETS[CLASSIC_PRESET_ID]


def is_deprecated(preset_id: str) -> bool:
    """Phase 4~6에서 철회된 프리셋 id 감지. 마이그레이션 진입 판정."""
    return preset_id in _DEPRECATED_PRESET_IDS


def migrate_deprecated_preset(section) -> None:
    """사용자 저장값에 폐기 프리셋 id가 남아있으면 classic으로 silent write.

    `section`은 `config.conf[ADDON_NAME]` 섹션. configobj Section 객체로
    dict-like API 제공. 호출은 `__init__.py`의 GlobalPlugin.__init__에서 한 번.
    멱등 — 이미 마이그레이션된 환경에서 재호출해도 no-op.

    `humorPackWarningShown` 같은 obsolete 키 청소는 `settings._OBSOLETE_KEYS`가
    단일 소유. 여기서는 `beepPreset` 값 치환만 담당해 책임 분리 유지.
    """
    try:
        preset_id = section.get("beepPreset")
        # preset_id가 None이면 is_deprecated는 False이지만 타입 계약 위반이므로
        # 문자열 확인 후 분기.
        if preset_id and is_deprecated(preset_id):
            log.warning(
                f"mtwn: deprecated beepPreset={preset_id!r} migrated to "
                f"{CLASSIC_PRESET_ID!r}"
            )
            section["beepPreset"] = CLASSIC_PRESET_ID
    except Exception:
        # 설정 섹션이 손상됐거나 타입이 예상과 다른 경우에도 플러그인 부팅을
        # 막지 않는다. 최악의 경우 beepPlayer/matcher의 `get_preset_or_classic`
        # 런타임 폴백이 classic으로 흡수.
        log.exception(f"mtwn: migrate_deprecated_preset failed (section={section!r})")


# 노출용 심볼 명시. 다른 모듈이 *-import를 쓰지 않아 형식적이지만 공개 표면을
# 문서로도 남긴다.
__all__ = (
    "PRESETS",
    "CLASSIC_PRESET_ID",
    "get_preset",
    "get_preset_or_classic",
    "is_deprecated",
    "migrate_deprecated_preset",
)
