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

from .constants import ADDON_NAME, MAX_ITEMS

# NVDA config.conf 스키마.
# 문자열 포맷: "<type>(default=<v>, min=<v>, max=<v>)"
# - beepDuration      : 비프음 지속 시간(ms). 기존 하드코딩 값 50을 기본값으로.
# - beepVolumeLeft    : 좌측 볼륨 (0~100)
# - beepVolumeRight   : 우측 볼륨 (0~100)
# - maxItems          : 사용자 운영 상한. 실제 상한은 MAX_ITEMS(=BEEP_TABLE 길이)와 min() 결합
# - enableAllWindows  : 모든 포커스 전환에서 비프할지 여부.
#                      기본 False → Alt+Tab 오버레이(Windows.UI.Input.InputSite.WindowClass)에서만 동작.
CONFSPEC = {
    "beepDuration": "integer(default=100, min=20, max=500)",
    "beepVolumeLeft": "integer(default=50, min=0, max=100)",
    "beepVolumeRight": "integer(default=50, min=0, max=100)",
    "maxItems": f"integer(default={MAX_ITEMS}, min=1, max={MAX_ITEMS})",
    "enableAllWindows": "boolean(default=False)",
}


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
