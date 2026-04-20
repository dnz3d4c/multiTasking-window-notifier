# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""애드온 설정 스키마와 등록 헬퍼.

NVDA의 config 모듈에 `confspec`을 등록해
`config.conf[ADDON_NAME][...]`로 접근 가능하도록 한다.

UI는 settingsPanel.py(Phase 3)에서 별도 제공. 본 모듈은 스키마만 담당.
"""

import re

import config
from logHandler import log

from .constants import ADDON_NAME

# NVDA config.conf 스키마.
# 문자열 포맷: "<type>(default=<v>, min=<v>, max=<v>)"
# - beepDuration      : 비프음 지속 시간(ms). v4부터 2음 재생이 기본이므로 각 음 50ms.
# - beepGapMs         : 앱 비프 a와 탭 비프 b 사이 간격(ms). v4 신설.
#                      100ms가 기본 — 15→60→100으로 두 차례 상향. 60에서도 두 음이
#                      한 덩어리로 뭉쳐 들린다는 피드백 후 재조정.
# - debugLogging      : event_gainFocus 진단 로그. Ctrl+Tab/오버레이 classname 추적용.
#                      기본 False. 켜면 NVDA 로그(%APPDATA%\\nvda\\nvda.log)에 한 줄씩 기록.
# - beepPreset        : 비프 프리셋 id (Phase 1 신설). constants.PRESETS의 key.
#                      미지 id 지정 시 beepPlayer가 CLASSIC_PRESET_ID로 폴백.
#                      설치 직후/롤백 시 "classic"으로 현행 소리 그대로 유지.
CONFSPEC = {
    "beepDuration": "integer(default=50, min=20, max=500)",
    "beepGapMs": "integer(default=100, min=0, max=200)",
    "debugLogging": "boolean(default=False)",
    "beepPreset": 'string(default="classic")',
}

# 과거 버전 confspec에 있었으나 의미가 사라져 제거된 키 목록.
# - beepVolumeLeft/Right : 좌/우 채널 볼륨(0~100). 사용자가 항상 50/50로 운용 →
#                          tones SDK 기본값과 동일 동작이라 제거.
# - maxItems             : 사용자 운영 상한(1~128). v7 BEEP_TABLE_SIZE(35) ↔
#                          MAX_ITEMS(128) 디커플 + 비프 변별이 BEEP_TABLE 안에서
#                          끝나서 사용자가 줄일 실용 이유 없음. MAX_ITEMS 상수만으로
#                          하드 상한 충분.
# register()에서 1회성으로 nvda.ini 잔재를 정리한다(다음 NVDA 종료 시 디스크 반영).
_OBSOLETE_KEYS = ("beepVolumeLeft", "beepVolumeRight", "maxItems")


# 스펙 타입 → 파이썬 변환기. CONFSPEC에서 새 타입을 도입하면 여기도 확장.
_TYPE_PARSERS = {
    "integer": int,
    "boolean": lambda v: v.strip().lower() in ("true", "yes", "1"),
    "string": lambda v: v.strip().strip('"').strip("'"),
}


def _parse_default(spec_str: str):
    """CONFSPEC 값 문자열에서 default를 파싱해 파이썬 값으로 반환.

    NVDA/configobj는 시작 시 한 번만 spec을 validate하므로, 애드온이 런타임에
    spec을 등록해도 live config에는 기본값이 들어오지 않는다. 이를 보완하려고
    register()에서 이 함수로 직접 기본값을 채워 넣는다.

    Raises:
        ValueError: default가 없거나 지원하지 않는 타입인 경우.
    """
    type_name = spec_str.split("(", 1)[0].strip()
    m = re.search(r"default\s*=\s*([^,\)]+)", spec_str)
    if not m:
        raise ValueError(f"CONFSPEC에 default가 없다: {spec_str}")
    raw = m.group(1).strip()
    parser = _TYPE_PARSERS.get(type_name)
    if parser is None:
        raise ValueError(f"지원하지 않는 spec 타입: {type_name}")
    return parser(raw)


def register() -> None:
    """스키마를 `config.conf.spec`에 등록하고 live config에 기본값 주입.

    NVDA는 시작 시 config.conf 전체를 한 번 validate하며, 이때 spec에 없던
    섹션/키는 defaults로 채워진다. 그러나 애드온이 `GlobalPlugin.__init__`에서
    spec을 추가하면 그 시점엔 validate가 다시 돌지 않아 `config.conf[ADDON]`
    조회가 KeyError를 던진다 (패널 미표시/비프 회귀의 원인).

    본 함수는 spec 등록 직후 섹션이 없으면 만들고, 빠진 키만 CONFSPEC의
    default로 채운다. 기존 값은 건드리지 않아 프로필 전환/반복 호출에 멱등.
    """
    config.conf.spec[ADDON_NAME] = CONFSPEC
    if ADDON_NAME not in config.conf:
        config.conf[ADDON_NAME] = {}
    section = config.conf[ADDON_NAME]
    for key, spec_str in CONFSPEC.items():
        if key not in section:
            section[key] = _parse_default(spec_str)
    # 과거 버전에서 박힌 obsolete 키 제거. configobj가 spec 외 키를 무시하긴 하지만
    # nvda.ini에는 그대로 남아 지원 인력이 봤을 때 혼란을 준다. 명시 리스트만
    # 처리해 다른 도구/사용자 수동 추가 키는 보호한다. 멱등.
    purged = []
    for key in _OBSOLETE_KEYS:
        if key in section:
            try:
                del section[key]
                purged.append(key)
            except KeyError:
                pass
    if purged:
        log.info(f"mtwn: purged obsolete config keys: {purged}")


def get(key: str):
    """설정값 조회 단축 헬퍼. 섹션/키가 누락되면 CONFSPEC default로 폴백.

    정상 흐름에서는 register()가 기본값을 주입해두므로 KeyError가 날 일이 없다.
    다만 사용자가 nvda.ini를 수동 편집하거나 프로필 전환 시 섹션이 비어 있는
    순간 조회가 들어오면 KeyError가 터질 수 있다. 이런 경계 상황에서
    event_gainFocus가 조용히 죽어 비프가 회귀했던 이력이 있어 방어적으로
    CONFSPEC의 default를 반환한다.

    Args:
        key: CONFSPEC 키 (예: "beepDuration")
    """
    try:
        return config.conf[ADDON_NAME][key]
    except KeyError:
        # CONFSPEC에 없는 키면 ValueError/KeyError로 그대로 승격.
        spec_str = CONFSPEC[key]
        log.warning(
            f"mtwn: settings.get fallback key={key!r} "
            f"— config.conf[{ADDON_NAME!r}] section/key missing, using CONFSPEC default"
        )
        return _parse_default(spec_str)
