# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""창/경로 정보 헬퍼."""

import os

import api
import globalVars

from logHandler import log

from .constants import ADDON_NAME
from .appIdentity import getAppId, makeKey


def config_addon_dir() -> str:
    """사용자 설정 경로 하위의 애드온 디렉터리 경로 계산."""
    base = globalVars.appArgs.configPath
    return os.path.join(base, "addons", ADDON_NAME, "globalPlugins", ADDON_NAME)


def get_current_window_info():
    """포커스된 창의 정보 추출.

    Returns:
        tuple: (fg, appId, title, key). 추출 실패 시 (None, None, None, None).

    예외는 모두 내부에서 삼키고 None 튜플로 반환한다. 호출부(스크립트)에서
    사용자 안내를 처리하므로 본 함수는 `log`로만 진단 정보를 남긴다.
    """
    try:
        fg = api.getForegroundObject()
    except Exception:
        log.exception("get_current_window_info: getForegroundObject 실패")
        return None, None, None, None
    if fg is None:
        return None, None, None, None
    try:
        title = (getattr(fg, "name", "") or "").strip()
    except Exception:
        log.exception("get_current_window_info: 포커스 창 이름 읽기 실패")
        return None, None, None, None
    if not title:
        return None, None, None, None
    appId = getAppId(fg)
    key = makeKey(appId, title)
    return fg, appId, title, key
