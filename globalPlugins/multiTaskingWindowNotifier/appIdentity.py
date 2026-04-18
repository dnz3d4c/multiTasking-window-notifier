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
        log.debug("mtwn: getAppId appModule.appName access failed", exc_info=True)
        appId = ""
    if not appId:
        appId = getattr(obj, "windowClassName", "") or "unknown"
    return appId


def makeKey(appId: str, title: str) -> str:
    """저장·매칭용 복합키 생성 (scope=window 전용)."""
    return f"{appId}|{title}"


def makeAppKey(appId: str) -> str:
    """앱 scope 항목용 키. 단순히 appId 자체.

    splitKey와의 충돌 우려는 scope 필드(meta)로 구분하므로 여기선 발생하지 않음.
    splitKey는 scope=window 항목에 대해서만 호출한다.
    """
    return appId


def splitKey(entry: str):
    """복합키 파싱. 구형(제목만) 포맷도 처리.

    Returns:
        tuple: (appId, title). 구형 포맷이면 appId=""
    """
    if "|" in entry:
        appId, title = entry.split("|", 1)
        return appId, title
    return "", entry  # 구형: 제목만


def normalize_title(name: str) -> str:
    """창 제목에서 **선두 dirty 마커**와 **꼬리 ' - 앱명' 서픽스**를 제거해 순수 탭 제목만 남긴다.

    Alt+Tab obj.name('제목 없음 - 메모장'), editor fg.name('*룰루루 - 메모장'),
    MRU obj.name('새로운 10') 세 경로가 전부 같은 형태로 떨어지게 하려고 도입.
    appId가 `scope=window` 복합키의 1등 요소라, title에 앱명까지 중복 저장할
    이유가 없다.

    예시:
        '제목 없음 - 메모장'                 → '제목 없음'
        '*새로운 10 - Notepad++'             → '새로운 10'  (Notepad++ dirty 마커)
        '● main.py - VS Code'                → 'main.py'   (VS Code 수정됨 표시)
        'Chapter 1 - Introduction - NPP'     → 'Chapter 1 - Introduction'
        '새로운 10' (MRU, 서픽스 없음)       → '새로운 10'
        '' / None                            → ''

    구현:
        1. 선두 dirty 마커 제거 — Notepad++의 '*', VS Code의 '●' 등 "저장 안 된
           변경사항 있음" 을 나타내는 문자. editor focus 시 fg.name엔 있는데
           MRU 오버레이 같은 다른 경로 obj.name엔 없는 경우가 있어 제거 없으면
           key 불일치로 매칭 실패(실측 확인).
        2. 꼬리 ' - 앱명' 한 덩이 제거. `appModule.productName`을 쓰지 않는
           이유는 한글 Windows 메모장처럼 productName(영문 'Notepad')이 title
           bar의 한글('메모장')과 어긋나는 리소스 번역 불일치가 있기 때문.
           rsplit은 그 불일치와 무관하게 robust.

    엣지:
        - 타이틀이 실제로 '*'로 시작하는 희귀 케이스(예: 파일명 "*.py"를 그대로
          표시)는 잘못 제거될 수 있으나 매칭 소스도 같은 규칙을 거치므로 기능
          손실 없음.
        - 정상 타이틀이 ' - '를 포함("Chapter 1 - Intro")하면 마지막 덩이가
          앱명이 아니어도 제거되지만 역시 매칭 소스가 같은 규칙을 거친다.
    """
    s = (name or "").strip()
    if not s:
        return ""
    # 1) 선두 dirty 마커들 순차 제거. 공백 섞여 있어도 벗긴다.
    #    대표 예: Notepad++('*'), VS Code('●'), Sublime('●'/'◌').
    while s and (s[0] in ("*", "●", "◌", "•")):
        s = s[1:].lstrip()
    if not s:
        return ""
    # 2) 꼬리 ' - 앱명' 서픽스 제거
    if " - " in s:
        s = s.rsplit(" - ", 1)[0].rstrip()
    return s
