# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""애드온 전역 상수."""

ADDON_NAME = "multiTaskingWindowNotifier"

# 비프 테이블: C major 온음계(도·레·미·파·솔·라·시) 7음 × 5옥타브 = 35개 주파수.
# C3(~130Hz)부터 B7(~3951Hz)까지. v7부터 반음 64음에서 온음계 35음으로 전환.
# 이유: 반음 간격(C→C#, 1/12옥타브)은 청각적으로 색깔이 비슷해 인접 슬롯 변별이
# 어렵다는 실전 피드백. 온음계는 인접 슬롯 간격이 전음(C→D) 또는 장2도로 벌어져
# "도·레·미 …"로 확연히 구분된다.
# v4부터 app/tab 비프가 이 테이블을 공유. (app_idx, tab_idx)는 각각
# 독립적으로 0..BEEP_TABLE_SIZE-1 범위에서 배정된다.
BEEP_TABLE = [
    130, 146, 164, 174, 196, 220, 246,        # C3 D3 E3 F3 G3 A3 B3
    261, 293, 329, 349, 392, 440, 493,        # C4 D4 E4 F4 G4 A4 B4
    523, 587, 659, 698, 784, 880, 987,        # C5 D5 E5 F5 G5 A5 B5
    1047, 1175, 1319, 1397, 1568, 1760, 1976, # C6 D6 E6 F6 G6 A6 B6
    2093, 2349, 2637, 2794, 3136, 3520, 3951, # C7 D7 E7 F7 G7 A7 B7
]

# 비프 팔레트 슬롯 수. v4부터 MAX_ITEMS와 디커플. v7부터 35(7 × 5옥타브).
BEEP_TABLE_SIZE = len(BEEP_TABLE)

# 자동 할당 실사용 구간. v7부터 전 구간(0~35) 사용.
# 반음 스킴(v5~v6)에서는 청각 피로 때문에 상단을 절반 잘라 0~48만 썼으나,
# 온음계는 같은 옥타브 내 인접음 간격이 이미 벌어져 있어 고음까지 활용해도
# 변별력이 유지된다. B7(3951Hz)가 테이블 상한이며 쇳소리 영역(C8~) 자체가 제거됨.
BEEP_USABLE_START = 0
BEEP_USABLE_END = BEEP_TABLE_SIZE
BEEP_USABLE_SIZE = BEEP_USABLE_END - BEEP_USABLE_START

# 총 entry 상한 (scope=app + scope=window 합). v3까지는 BEEP_TABLE_SIZE와 강제
# 커플링되어 64였으나, v4에서 (app_idx, tab_idx) 쌍 구조가 도입되어 이론 조합이
# 현재 35×35=1225가 된다. 실용 상한으로 128을 적용. 초과 시 앱별 appBeepIdx가
# 공유될 수 있으나 청각 차원에서 탭 비프 b로 구분된다.
MAX_ITEMS = 128

# 등록 항목 scope.
#   SCOPE_WINDOW: 특정 창(appId|title 복합키). 활성 탭 제목이 일치할 때만 매칭.
#   SCOPE_APP   : 앱 전체(appId만). 같은 앱의 어떤 창/탭이든 매칭. 창 매치가
#                  우선이고 앱 매치는 fallback. v3 스키마에서 도입.
SCOPE_WINDOW = "window"
SCOPE_APP = "app"

# Alt+Tab 전환 중 Windows가 띄우는 시스템 오버레이의 windowClassName.
# Win10/Win11 공통으로 `event_gainFocus`가 후보 창별로 이 wcn을 들고 쏜다.
# 앱별 설정이 아니라 OS 차원의 고정값이라 `tabClasses` 프리셋이 아닌 constants에 둔다.
ALT_TAB_OVERLAY_WCN = "Windows.UI.Input.InputSite.WindowClass"

# Alt+Tab 오버레이의 **포그라운드(호스트) windowClassName**.
# obj.wcn(Windows.UI.Input.InputSite.WindowClass)은 UWP InputSite 공용이라
# Win+B 숨김 아이콘·시스템 트레이·알림 센터 등 다른 목록형 UI와도 겹친다.
# 따라서 Alt+Tab 진입 판정은 (obj.wcn == ALT_TAB_OVERLAY_WCN AND
# fg.wcn == ALT_TAB_HOST_FG_WCN) 두 축 AND로 묶어 오탐을 배제한다.
# Windows 11 Xaml Shell 고정값. 로케일 독립.
ALT_TAB_HOST_FG_WCN = "XamlExplorerHostIslandWindow"

# 디바운스 flush 임계치. __init__.py가 FlushScheduler를 kwargs 없이 생성하므로
# 실제 런타임 정책값이 이 두 상수다. GlobalPlugin이 필요 시 생성자 kwargs로
# 덮어쓸 수 있고, 향후 사용자 조정 옵션화도 이 상수를 기준으로 확장.
FLUSH_EVERY_N_DEFAULT = 10
FLUSH_INTERVAL_SEC_DEFAULT = 30


# =====================================================================
# 프리셋 데이터 (Phase 1)
# =====================================================================
#
# 프리셋은 "비프 소리 스타일 + 슬롯 주파수 테이블 + 재생 파라미터"를 한 묶음으로
# 가지는 read-only dict. 사용자는 NVDA 설정 > 창 전환 알림 패널의 ListBox에서
# 프리셋을 고르고, 애드온은 선택된 프리셋의 `freqs`를 사용해 비프를 재생한다.
#
# 설계 원칙 (플랜 gleaming-drifting-dragonfly.md 반영):
#   - 데이터 only — 동작 로직/로깅은 beepPlayer/settings 레이어 책임.
#   - 문자열 레이블(nameLabel/descriptionLabel)은 raw. UI 레이어가 `_()`로 번역.
#   - 모든 freqs 리스트는 read-only. 런타임에 수정 금지.
#   - Phase 1에서는 slotCount=35 3개(classic/pentatonic/fifths)만. Phase 3~5에서
#     WAVEFORMS + synthSpecs 필드가 추가될 예정(현 구조는 이 확장을 이미 수용).
#   - "8비트 본질은 소리 스타일"(사용자 확정) — 다채널 PCM 믹싱은 범위 밖. voices
#     필드도 도입하지 않는다(YAGNI).
#
# 프리셋 dict 포맷:
#   id                  — 내부 식별자(settings.beepPreset에 저장되는 값)
#   nameLabel           — UI 노출 이름 (raw str; UI 레이어가 _() 번역)
#   type                — "tonal" | "hybrid" | "atonal" | "percussive"
#   slotCount           — 슬롯 수. 재생 시점 effective_idx = stored_idx % slotCount
#   recommendedMaxApps  — 이 프리셋에서 변별 가능한 앱 수 (UI 경고 기준)
#   optIn               — True면 기본 라인업 불포함(Phase 5 humor_pack에서 사용)
#   previewSlots        — "미리듣기(&P)" 버튼이 재생할 대표 슬롯 인덱스 2개
#   descriptionLabel    — ListBox focus 시 표시되는 짧은 설명 (raw str)
#   freqs               — slotCount 길이의 정수 주파수(Hz) 리스트 (tonal/hybrid 전용)
#   durationMs / gapMs  — 2음 순차 재생의 각 음 길이/간격
#   suppressRepeat      — 최근 0.3초 내 같은 키 재매칭 시 tab음 생략 (Phase 2)
#   octaveVariation     — 같은 앱 재진입 시 tab idx ±7 clip (Phase 2)
#   gain                — 재생 음량 계수(1.0=기본). Phase 3 PCM 합성에서 적용 예정.
#
# CLASSIC_PRESET_ID는 미지 프리셋 id 폴백 기본값. settings가 삭제/손상된 경우에도
# 항상 이 id의 프리셋으로 재생되어야 한다.

CLASSIC_PRESET_ID = "classic"


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
        # Phase 2: "Calm" 캐릭터를 살리는 두 기능을 기본 on.
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
    # Phase 3: Hybrid 프리셋 — nvwave + synthEngine PCM 합성 경로. `waveform` 키
    # 존재가 신 경로 진입 트리거. freqs는 BEEP_TABLE(C3~B7)을 공유해 음정 구조를
    # classic과 동일하게 유지하되 음색만 달라진다. 모든 Hybrid 프리셋은
    # slotCount=35로 modulo wrap이 no-op(향후 Phase 4에서 slotCount 가변 프리셋
    # 도입 시 modulo의 실효성이 드러난다).
    "arcade_pop": {
        "id": "arcade_pop",
        "nameLabel": "Arcade Pop",
        "type": "hybrid",
        "slotCount": 35,
        "recommendedMaxApps": 35,
        "optIn": False,
        "previewSlots": (0, 14),  # C3, C5
        "descriptionLabel": "Pulse 50% 사각파. 고전 아케이드의 경쾌한 톤.",
        "freqs": BEEP_TABLE,  # classic과 음정 동일, 파형만 교체
        "waveform": "pulse50",
        "durationMs": 50,
        "gapMs": 100,
        "suppressRepeat": False,
        "octaveVariation": False,
        "gain": 1.0,
    },
    "coin_dash": {
        "id": "coin_dash",
        "nameLabel": "Coin Dash",
        "type": "hybrid",
        "slotCount": 35,
        "recommendedMaxApps": 35,
        "optIn": False,
        "previewSlots": (0, 14),
        "descriptionLabel": "Pulse 25% 얇은 사각파. 코인 획득 느낌의 맑고 짧은 톤.",
        "freqs": BEEP_TABLE,
        "waveform": "pulse25",
        "durationMs": 50,
        "gapMs": 100,
        "suppressRepeat": False,
        "octaveVariation": False,
        "gain": 1.0,
    },
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
}


# 부팅 시 불변식 검증. 프리셋 dict에 오타/누락이 생기면 바로 ImportError로 드러나게
# 해 런타임 KeyError로 이어지지 않게 한다. 런타임 비용 없음(모듈 로드 시 1회).
for _pid, _p in PRESETS.items():
    assert _p["id"] == _pid, f"preset dict id mismatch: {_pid!r} vs {_p['id']!r}"
    assert 1 <= _p["slotCount"] <= MAX_ITEMS, (
        f"preset {_pid!r} slotCount={_p['slotCount']} out of 1..{MAX_ITEMS}"
    )
    assert len(_p["freqs"]) == _p["slotCount"], (
        f"preset {_pid!r} freqs len={len(_p['freqs'])} != slotCount={_p['slotCount']}"
    )
    for _ps in _p["previewSlots"]:
        assert 0 <= _ps < _p["slotCount"], (
            f"preset {_pid!r} previewSlot {_ps} out of 0..{_p['slotCount'] - 1}"
        )
assert CLASSIC_PRESET_ID in PRESETS, "CLASSIC_PRESET_ID fallback target missing"
