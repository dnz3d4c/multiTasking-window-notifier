# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""앱/창 식별 및 저장용 키 생성·파싱 유틸."""

import re

from logHandler import log


# 모듈 레벨 상수 (1회 컴파일/정의)
_LEADING_DIRTY = ("*", "●", "◌", "•")
# 변동 카운트 토큰: (N), [N], {N}, (N+) 형태. N은 1~4자리 정수.
# 점을 허용하지 않아 dotted version (3.11) 등은 보존.
# alternation으로 여는·닫는 괄호 종류를 짝 맞춰 mismatch(`(5]`) 매칭 차단.
_RE_COUNT_TOKEN = re.compile(r"^(\(\d{1,4}\+?\)|\[\d{1,4}\+?\]|\{\d{1,4}\+?\})$")
# 단독 구분자 토큰 — 선두/꼬리에서만 dangling으로 정리.
_SEPARATOR_TOKENS = frozenset({"·", "•", "●", "-", "—"})


def getAppId(obj) -> str:
    """앱 식별자 결정.

    NVDA 공식 진입점 `appModuleHandler.getAppModuleForNVDAObject(obj)` 경유로
    얻은 `appModule.appName`을 사용한다. NVDA가 appModule을 캐싱·override하는
    경로를 존중하기 위함. 실패 시 `windowClassName`, 그마저 비면 `"unknown"`.

    import는 함수 내부: `appModuleHandler`가 `config`/`winUser`를 끌어오는
    무거운 모듈이라 모듈 로드 시점 순환 위험이 있다. Python 캐시가 2회 이후
    호출을 처리하므로 고빈도 경로 오버헤드는 미미.
    """
    appId = ""
    try:
        import appModuleHandler  # noqa: WPS433 (의도적 지역 import)

        appModule = appModuleHandler.getAppModuleForNVDAObject(obj)
        if appModule is not None:
            appId = getattr(appModule, "appName", "") or ""
    except Exception:
        log.debug("mtwn: getAppModuleForNVDAObject failed", exc_info=True)
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


def _strip_dirty_markers(s: str) -> str:
    """1단계: 선두 dirty 마커(`*`, `●`, `◌`, `•`)를 순차 제거.

    Notepad++의 '*', VS Code의 '●' 등 "저장 안 된 변경사항" 표시. editor focus
    시 fg.name에는 있는데 MRU 오버레이의 obj.name에는 없는 경우가 있어 제거
    없으면 key 불일치(실측 확인).
    """
    while s and s[0] in _LEADING_DIRTY:
        s = s[1:].lstrip()
    return s


def _strip_app_suffix(s: str) -> str:
    """2단계: 꼬리 앱 서픽스 제거. em-dash(' — ') 1순위, hyphen(' - ') 2순위.

    브라우저 탭은 em-dash로 앱명을 분리하는 게 표준(`tab title — Mozilla
    Firefox`). hyphen은 콘텐츠 본문에 흔히 등장하므로 후순위. em-dash가 있으면
    그것만 사용해 hyphen을 잘못 자르는 회귀를 막는다.

    `appModule.productName`을 쓰지 않는 이유: 한글 Windows 메모장처럼
    productName(영문 'Notepad')이 title bar의 한글('메모장')과 어긋나는 리소스
    번역 불일치가 있기 때문. rsplit은 그 불일치와 무관하게 robust.
    """
    if " — " in s:
        return s.rsplit(" — ", 1)[0].rstrip()
    if " - " in s:
        return s.rsplit(" - ", 1)[0].rstrip()
    return s


def _strip_volatile_tokens(s: str) -> str:
    """3·4단계: 변동 카운트 토큰 제거 + 선두/꼬리 dangling 구분자 정리.

    카운트 토큰: `(N)`, `[N]`, `{N}`, `(N+)`. N은 1~4자리 정수. 위치 무관(선두/
    인라인 모두). 사용자 핵심 요구는 "(79)→(3) 변동에도 같은 키 유지".

    dotted version `(3.11)`은 점 포함이라 정규식 비매칭으로 보존. 5자리 이상
    `(12345)`도 보존(실측상 알림 카운트는 4자리 이내, 99+ 형태로 truncate).

    dangling 정리는 선두/꼬리만. 본문 중간의 `Chapter 1 — Introduction` 같은
    em-dash는 보존(콘텐츠 일부일 수 있음).
    """
    tokens = s.split()
    if not tokens:
        return ""
    kept = [t for t in tokens if not _RE_COUNT_TOKEN.match(t)]
    while kept and kept[0] in _SEPARATOR_TOKENS:
        kept.pop(0)
    while kept and kept[-1] in _SEPARATOR_TOKENS:
        kept.pop()
    return " ".join(kept)


def normalize_title(name: str) -> str:
    """창 제목에서 변동/장식 요소를 제거해 안정 매칭 키만 남긴다.

    4단계 파이프라인 (등록 시점과 매칭 시점 모두 같은 함수 통과 → 자기 일관성):
        1. `_strip_dirty_markers` — 선두 `*●◌•`
        2. `_strip_app_suffix`    — 꼬리 ` — 앱명` (em-dash 1순위) / ` - 앱명`
        3·4. `_strip_volatile_tokens` — `(N)` 카운트 + 선두/꼬리 dangling 구분자

    예시:
        '제목 없음 - 메모장'                                  → '제목 없음'
        '*새로운 10 - Notepad++'                              → '새로운 10'
        '● main.py - VS Code'                                 → 'main.py'
        '(12) · news_Healing — Mozilla Firefox'               → 'news_Healing'
        '받은편지함 (79) - x@y.com - Gmail — Mozilla Firefox' → '받은편지함 - x@y.com - Gmail'
        'Python (3.11) Release Notes — Mozilla Firefox'       → 'Python (3.11) Release Notes'
        '' / None                                              → ''

    엣지(허용):
        - '*.py' 같은 파일명 선두 '*'는 잘못 벗겨지나 매칭 소스도 같은 규칙.
        - 콘텐츠에 ' - '가 들어가도 마지막 덩이는 잘림(매칭 자기 일관성 우선).
        - 이메일/계정명은 변동값 아니므로 보존(사용자 동의 없는 마스킹 회피).
    """
    s = (name or "").strip()
    if not s:
        return ""
    s = _strip_dirty_markers(s)
    if not s:
        return ""
    s = _strip_app_suffix(s)
    s = _strip_volatile_tokens(s)
    return s
