# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""창/경로 정보 헬퍼."""

import os

import api
import globalVars

from .constants import ADDON_NAME
from .appIdentity import getAppId, makeKey


def config_addon_dir() -> str:
    """사용자 설정 경로 하위의 애드온 디렉터리 경로 계산."""
    base = globalVars.appArgs.configPath
    return os.path.join(base, "addons", ADDON_NAME, "globalPlugins", ADDON_NAME)


def get_current_window_info():
    """포커스된 창의 정보 추출.

    Returns:
        tuple: (fg, appId, title, key). title이 없으면 (None, None, None, None).
    """
    fg = api.getForegroundObject()
    title = (getattr(fg, "name", "") or "").strip()
    if not title:
        return None, None, None, None
    appId = getAppId(fg)
    key = makeKey(appId, title)
    return fg, appId, title, key
