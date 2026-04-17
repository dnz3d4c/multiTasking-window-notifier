# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""앱/창 식별 및 저장용 키 생성·파싱 유틸."""

from logHandler import log


def getAppId(obj) -> str:
    """앱 식별자 결정: 기본은 appModule.appName. 비어 있으면 windowClassName."""
    appId = ""
    try:
        appId = getattr(getattr(obj, "appModule", None), "appName", "") or ""
    except Exception:
        log.debug("appModule.appName 접근 실패", exc_info=True)
        appId = ""
    if not appId:
        appId = getattr(obj, "windowClassName", "") or "unknown"
    return appId


def makeKey(appId: str, title: str) -> str:
    """저장·매칭용 복합키 생성."""
    return f"{appId}|{title}"


def splitKey(entry: str):
    """복합키 파싱. 구형(제목만) 포맷도 처리.

    Returns:
        tuple: (appId, title). 구형 포맷이면 appId=""
    """
    if "|" in entry:
        appId, title = entry.split("|", 1)
        return appId, title
    return "", entry  # 구형: 제목만
