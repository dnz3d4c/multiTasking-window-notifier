# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""현재 화면에 열려 있는 top-level 창 목록 수집.

Windows EnumWindows API 래퍼. 튜토리얼 Step 3에서 "지금 어떤 창들이 있는지"
사용자가 훑어볼 수 있게 하기 위한 용도. 등록 대상 판단 재료.

필터 정책 (MVP 3단계):
    1. IsWindowVisible == True
    2. GetWindowTextLengthW > 0 (빈 제목 창 제외)
    3. DwmGetWindowAttribute(DWMWA_CLOAKED) == 0 (Win10+ 가상 데스크톱 숨김 창 제외)

한계: 이 필터만으로는 `WS_EX_TOOLWINDOW` 플래그가 있는 보조 창(예: 일부 앱의
오버레이/상태창)이 섞일 수 있다. Alt+Tab 목록과 완전히 일치하진 않는다.
사용자 피드백에 따라 `WS_EX_TOOLWINDOW` 제외를 추가할지는 후속 Phase에서 결정.

NVDA의 winUser 모듈 대신 ctypes 직접 사용: winUser는 Enum 계열을 래핑하지
않아 어차피 ctypes를 써야 하고, 신규 의존을 피하기 위함.
"""

import ctypes
from ctypes import wintypes

from logHandler import log


# WinAPI 바인딩. 모듈 로드 시 1회.
_user32 = ctypes.windll.user32
_dwmapi = ctypes.windll.dwmapi

# EnumWindows 콜백 시그니처: BOOL CALLBACK EnumWindowsProc(HWND hwnd, LPARAM lParam)
_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

# DwmGetWindowAttribute 상수. Win10+에서 가상 데스크톱 간 이동한 창의 "숨김" 상태 판별.
# https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/ne-dwmapi-dwmwindowattribute
_DWMWA_CLOAKED = 14

# argtypes/restype 명시 — NVDA 2026.1부터 64-bit 빌드가 기본이 돼 HWND(8바이트
# 포인터)가 기본 c_int(4바이트)로 절단될 위험이 있다. 모든 진입 함수에 명시.
_user32.EnumWindows.argtypes = [_WNDENUMPROC, wintypes.LPARAM]
_user32.EnumWindows.restype = wintypes.BOOL
_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.IsWindowVisible.restype = wintypes.BOOL
_user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
_user32.GetWindowTextLengthW.restype = ctypes.c_int
_user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.GetWindowTextW.restype = ctypes.c_int
_dwmapi.DwmGetWindowAttribute.argtypes = [
    wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD
]
_dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long  # HRESULT


def _is_cloaked(hwnd: int) -> bool:
    """DWM cloaked 상태 확인. API 실패 시 False로 가정(안전하게 표시)."""
    cloaked = ctypes.c_int(0)
    try:
        # S_OK(0)일 때 cloaked.value가 유효. 실패 코드면 값 신뢰 불가.
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
        # DwmGetWindowAttribute가 구형 Windows에서 OSError를 던질 수 있다.
        # MVP는 Win10+ 가정이지만 예외 경로에서 표시는 막지 않음.
        return False


def enum_visible_top_windows(
    limit: int = 50,
    exclude_hwnds=None,
) -> list:
    """현재 열린 top-level visible 창 리스트.

    Args:
        limit: 최대 반환 개수. 50개면 튜토리얼 ListBox로 충분.
        exclude_hwnds: 집합/iterable. 튜토리얼 다이얼로그 자신의 hwnd를 넣어
            목록에 자기 자신이 뜨는 걸 막는다.

    Returns:
        list[dict]: 각 원소는 `{"hwnd": int, "title": str}`. 제목은 이미
            strip된 상태. EnumWindows가 반환하는 Z-order 상위(최근 활성) 순서
            그대로 유지된다.
    """
    exclude = set(exclude_hwnds or ())
    results: list = []

    def _cb(hwnd, _lparam):
        # limit 도달 시 EnumWindows 조기 종료(False 반환).
        if len(results) >= limit:
            return False
        try:
            if int(hwnd) in exclude:
                return True
            if not _user32.IsWindowVisible(hwnd):
                return True
            length = _user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            if _is_cloaked(int(hwnd)):
                return True
            # length+1과 256 중 큰 값 사용 — 열거 중 창 제목이 변해 실제 길이가
            # 더 길어지는 race를 일부 완화. 길어지면 잘리되 크래시 없음.
            buf_size = max(length + 1, 256)
            buf = ctypes.create_unicode_buffer(buf_size)
            _user32.GetWindowTextW(hwnd, buf, buf_size)
            title = (buf.value or "").strip()
            if not title:
                return True
            results.append({"hwnd": int(hwnd), "title": title})
        except Exception:
            # 개별 hwnd 조회 실패가 전체 열거를 중단하지 않도록 흡수.
            log.exception(f"mtwn: windowEnum per-hwnd failed hwnd={hwnd!r}")
        return True

    # 콜백을 로컬 변수에 바인딩해 EnumWindows 실행 중 ctypes 래퍼가 파이썬
    # GC에 회수되지 않도록 보장. EnumWindows는 동기 호출이지만 ctypes 관례에
    # 따라 명시적으로 참조 유지.
    cb = _WNDENUMPROC(_cb)
    try:
        _user32.EnumWindows(cb, 0)
    except Exception:
        # EnumWindows 자체 호출 실패 — 매우 드문 케이스. 빈 목록 반환해
        # 튜토리얼 UI가 "창을 불러오지 못했어요" 안내로 폴백 가능하도록.
        log.exception("mtwn: windowEnum EnumWindows call failed")
        return []

    return results
