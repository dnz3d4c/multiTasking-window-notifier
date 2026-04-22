# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""현재 화면에 열려 있는 top-level 창 목록 수집.

NVDA 데스크탑 object 트리(`api.getDesktopObject().firstChild` → `.next` 체인)를
순회해 top-level 창을 수집한다. 과거 ctypes `EnumWindows` 직접 호출 방식은
NVDA가 내부적으로 쓰는 `isUsableWindow`(visible + !ghostWindow) 필터를 재구현
해야 했고, NVDA의 접근성 트리와 미묘하게 어긋날 위험이 있었다.

왜 NVDA object 트리인가:
    - `NVDAObjects.window.Window._get_next`가 이미 `isUsableWindow` 루프로
      unusable 창(응답 없는 ghost window 포함)을 자동 스킵
      (`NVDA/source/NVDAObjects/window/__init__.py:241-246`,
      `NVDA/source/globalCommands.py:29-34`).
    - NVDA가 실제로 접근성 트리에서 다루는 창과 일치해 튜토리얼 Step 3
      "지금 열린 창" 안내가 사용자 체감과 맞아떨어진다.
    - Win32 API 세부(HWND argtypes, 64-bit 절단 등)는 NVDA 레이어가 흡수.
    - 프로젝트 CLAUDE.md "NVDA가 이미 보장하는 조건을 재방어하지 않는다"
      원칙과 정합.

애드온이 추가로 처리하는 필터 (NVDA가 처리하지 않는 부분):
    - cloaked: Win10+ 가상 데스크톱에서 다른 데스크톱에 있는 창은
      `IsWindowVisible`이 True여도 사용자는 볼 수 없다. NVDA 소스에도 대응이
      없어 애드온이 직접 `DwmGetWindowAttribute(DWMWA_CLOAKED)`로 거른다.
    - 빈 제목: 무제목 창은 사용자가 "창"으로 인식하지 않음.
    - 중복 hwnd: `.next` 순회는 기본적으로 중복 없지만 방어용 `seen` 집합.

한계:
    `WS_EX_TOOLWINDOW` 플래그가 있는 보조 창은 NVDA 트리에도 남는다. Alt+Tab
    목록과 완전 일치시키려면 추가 플래그 체크가 필요 — 사용자 피드백 후 판단.
"""

import ctypes
from ctypes import wintypes

import api
import controlTypes
from NVDAObjects.window import Window
from logHandler import log


# DWMWA_CLOAKED 체크 — NVDA가 처리하지 않는 부분만 ctypes 직접 호출 유지.
# https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/ne-dwmapi-dwmwindowattribute
_dwmapi = ctypes.windll.dwmapi
_DWMWA_CLOAKED = 14
_dwmapi.DwmGetWindowAttribute.argtypes = [
    wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD
]
_dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long  # HRESULT

# `.next` 루프의 이론적 무한 반복 방어. 정상 환경에서 top-level 창은 30~200개.
_MAX_SIBLINGS = 500


def _is_cloaked(hwnd: int) -> bool:
    """DWM cloaked 상태 확인. API 실패 시 False로 가정(안전하게 표시)."""
    cloaked = ctypes.c_int(0)
    try:
        hr = _dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(hwnd),
            _DWMWA_CLOAKED,
            ctypes.byref(cloaked),
            ctypes.sizeof(cloaked),
        )
        if hr != 0:
            return False
        return cloaked.value != 0
    except Exception:
        # 구형 Windows에서 OSError 가능. MVP는 Win10+ 가정이나 예외 경로에서
        # 표시는 막지 않음.
        return False


def _maybe_extract_entry(obj, exclude: set, seen: set):
    """단일 NVDA Window 객체를 entry dict로 변환. 스킵 대상이면 None.

    필터 순서 (싼 것 → 비싼 것):
        1. Window 인스턴스 여부 (Desktop overlay 등 방어)
        2. windowHandle 유효성 + exclude/seen 중복
        3. role == Role.WINDOW (Desktop 등 비정규 창 제외)
        4. name 비어있지 않음
        5. cloaked 아님 (DWM API 호출로 가장 비쌈)
    """
    if not isinstance(obj, Window):
        return None
    try:
        hwnd = int(obj.windowHandle or 0)
    except Exception:
        return None
    if hwnd == 0 or hwnd in seen or hwnd in exclude:
        return None
    try:
        role = obj.role
    except Exception:
        role = None
    if role != controlTypes.Role.WINDOW:
        return None
    title = (obj.name or "").strip()
    if not title:
        return None
    if _is_cloaked(hwnd):
        return None
    return {"hwnd": hwnd, "title": title}


def enum_visible_top_windows(
    limit: int = 50,
    exclude_hwnds=None,
) -> list:
    """현재 열린 top-level visible 창 리스트.

    NVDA 데스크탑 object 트리(`api.getDesktopObject().firstChild → .next`)를
    순회해 수집. `Window._get_next`가 `isUsableWindow` 필터를 이미 적용하므로
    애드온은 cloaked + 빈 제목 + 중복 + Role.WINDOW 필터만 추가.

    Args:
        limit: 최대 반환 개수. 50개면 튜토리얼 ListBox로 충분.
        exclude_hwnds: 집합/iterable. 튜토리얼 다이얼로그 자신의 hwnd를 넣어
            목록에 자기 자신이 뜨는 걸 막는다.

    Returns:
        list[dict]: 각 원소는 `{"hwnd": int, "title": str}`. 제목은 이미
            strip된 상태. `.next` 체인의 Z-order 상위(최근 활성) 순서 유지.
    """
    exclude: set = set()
    try:
        for h in (exclude_hwnds or ()):
            exclude.add(int(h))
    except Exception:
        # 비정상 입력은 빈 exclude로 폴백해 호출 실패보다 "자기 자신 포함"을 택함.
        exclude = set()
    results: list = []
    seen: set = set()

    try:
        desktop = api.getDesktopObject()
    except Exception:
        log.exception("mtwn: windowEnum getDesktopObject failed")
        return []

    if desktop is None:
        return []

    try:
        child = desktop.firstChild
    except Exception:
        log.exception("mtwn: windowEnum desktop.firstChild failed")
        return []

    # `.next` 호출마다 `findBestAPIClass`가 도는 다소 비싼 경로 —
    # limit 도달 즉시 break해서 불필요한 객체 생성을 피한다.
    guard = 0
    while child is not None and len(results) < limit and guard < _MAX_SIBLINGS:
        guard += 1
        try:
            entry = _maybe_extract_entry(child, exclude, seen)
            if entry is not None:
                results.append(entry)
                seen.add(entry["hwnd"])
        except Exception:
            log.exception("mtwn: windowEnum per-obj failed")
        try:
            child = child.next
        except Exception:
            # `.next` 자체 실패 — 트리 파손. 현재까지 수집한 결과만 반환.
            log.exception("mtwn: windowEnum .next failed")
            break

    return results
