# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""애드온 설정 스키마와 등록 헬퍼.

NVDA의 config 모듈에 `confspec`을 등록해
`config.conf[ADDON_NAME][...]`로 접근 가능하도록 한다.

UI는 settingsPanel.py(Phase 3)에서 별도 제공. 본 모듈은 스키마만 담당.
"""

import config

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
    "beepDuration": "integer(default=50, min=20, max=500)",
    "beepVolumeLeft": "integer(default=30, min=0, max=100)",
    "beepVolumeRight": "integer(default=30, min=0, max=100)",
    "maxItems": f"integer(default={MAX_ITEMS}, min=1, max={MAX_ITEMS})",
    "enableAllWindows": "boolean(default=False)",
}


def register() -> None:
    """스키마를 `config.conf.spec`에 등록.

    GlobalPlugin.__init__에서 호출. 동일 `CONFSPEC` 재대입은 멱등이므로
    프로필 전환 등으로 여러 번 호출되더라도 안전.
    """
    config.conf.spec[ADDON_NAME] = CONFSPEC


def get(key: str):
    """설정값 조회 단축 헬퍼.

    Args:
        key: CONFSPEC 키 (예: "beepDuration")
    """
    return config.conf[ADDON_NAME][key]
