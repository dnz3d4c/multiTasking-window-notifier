# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""창/경로 정보 헬퍼."""

import os

import api
import globalVars

from logHandler import log

from .constants import ADDON_NAME
from .appIdentity import getAppId, makeKey, normalize_title


def config_addon_dir() -> str:
    """사용자 데이터 디렉터리 경로. %APPDATA%\\nvda\\multiTaskingWindowNotifier\\.

    애드온 패키지 트리(%APPDATA%\\nvda\\addons\\...) 바깥에 저장해
    재설치 시 app.json / tabClasses.json이 함께 지워지는 것을 방지한다.
    portable NVDA에서는 globalVars.appArgs.configPath가 자동으로
    portable 경로로 바뀐다.
    """
    base = globalVars.appArgs.configPath
    return os.path.join(base, ADDON_NAME)


def get_current_window_info():
    """포커스된 창의 정보 추출.

    Returns:
        tuple: (foreground, appId, title, key). 추출 실패 시 (None, None, None, None).

    예외는 모두 내부에서 삼키고 None 튜플로 반환한다. 호출부(스크립트)에서
    사용자 안내를 처리하므로 본 함수는 `log`로만 진단 정보를 남긴다.
    """
    try:
        foreground = api.getForegroundObject()
    except Exception:
        log.exception("mtwn: get_current_window_info getForegroundObject failed")
        return None, None, None, None
    if foreground is None:
        return None, None, None, None
    try:
        raw_title = (getattr(foreground, "name", "") or "").strip()
    except Exception:
        log.exception("mtwn: get_current_window_info read foreground name failed")
        return None, None, None, None
    if not raw_title:
        return None, None, None, None
    # 등록/삭제 단일 진입점에서 title을 정규화해 event_gainFocus 매칭과 포맷을 맞춘다.
    # "제목 없음 - 메모장" → "제목 없음". appId가 복합키의 1등 요소라 title에는
    # 앱명 서픽스를 저장하지 않는다.
    title = normalize_title(raw_title)
    if not title:
        return None, None, None, None
    appId = getAppId(foreground)
    key = makeKey(appId, title)
    return foreground, appId, title, key
