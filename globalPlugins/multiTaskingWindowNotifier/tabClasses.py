# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""앱별 탭 컨트롤 window_class_name 매핑.

eventRouter.dispatch_focus의 분기 판정에 쓰이는 **상수 테이블**이다. 과거에는
`tabClasses.json` 파일로 외재화해 사용자가 NVDA+Shift+T 등록 시 editor wcn을
자동 학습할 수 있게 했으나, 실사용에서 학습 경로가 한 번도 쓰이지 않아 JSON
I/O를 제거하고 상수 조회로 되돌렸다. 새 앱(예: VSCode)의 window_class_name 추가는 소스
수정 + 재배포로 처리.

의미:
    - editor: Ctrl+Tab 확정 후 포커스가 오는 자식 컨트롤의 windowClassName.
              같은 탭 제목(예: 메모장 "제목 없음" 여러 개)을 구분하려면
              foreground.name만으로는 불가능하고 자식 컨트롤의 hwnd가 탭마다 다르다는
              점을 이용해야 한다. 이 wcn이 focus면 `foreground.name`을 탭 제목,
              `obj.windowHandle`(자식)을 tab_signature로 삼아 매칭한다.
              **중요 게이트**: `window_class_name != foreground_class_name` 조건이 필수. Firefox처럼 자식
              wcn이 최상위와 같은 앱은 이 분기에서 자동 제외되어 "모든 포커스
              이동마다 매칭" 병리가 재발하지 않는다.
    - overlay: 탭 선택 오버레이 상위창의 windowClassName
              (= `api.getForegroundObject().windowClassName`).
              이 foregroundClassName이면 `obj.name`(리스트 항목 자체)을 탭 제목으로 삼아 매칭.

탭 확정 전환은 **두 경로로 분업**한다:
    1. `event_nameChange` — 대부분의 앱(Firefox/Notepad++ 포함). 창의 title bar
       자체가 바뀌므로 foreground의 name 변경으로 직접 감지.
    2. editor 분기 — 메모장처럼 **같은 제목의 여러 탭**이 일상적인 앱. title이
       안 바뀌어 nameChange가 못 잡는 전환을 자식 hwnd 변경으로 포착.

외부 API:
    is_editor_class(appId, window_class_name)      -> bool
    is_overlay_class(appId, foreground_class_name)  -> bool
"""


# 실측 근거(진단 로그):
#   - 메모장 Ctrl+Tab: obj.window_class_name='RichEditD2DPT' (자식), foregroundClassName='Notepad' (상위)
#   - Notepad++ MRU 오버레이 진행 중: foregroundClassName='#32770'
#   - Chrome Ctrl+Tab: obj.window_class_name='Chrome_RenderWidgetHostHWND' (자식),
#     foregroundClassName='Chrome_WidgetWin_1' (상위), foregroundName='<탭 제목> - Chrome'
# editor 등재 기준(둘 중 하나라도 해당하면 등재 후보):
#   1) **같은 제목의 여러 탭**이 정상 케이스인 앱 — foreground.name만으로 탭
#      구분이 불가능하므로 자식 hwnd로 구분해야 한다. 메모장이 대표.
#   2) Ctrl+Tab이 **event_nameChange를 쏘지 않는** 앱 — title bar가 바뀌어도
#      NVDA가 그 변경을 nameChange로 전파하지 않아 editor 분기가 유일한 매칭
#      경로가 된다. Chrome이 대표(실측).
# Notepad++는 파일명 기반이라 title 중복이 드물고 nameChange를 쏴서 편집기
# 분기 불필요. Firefox는 자식==최상위 wcn이라 editor 분기에 등재하면 안 되고
# nameChange가 담당.
# **CEF 임베디드 앱 경계**: Spotify/Slack 등도 obj.windowClassName이 동일한
# 'Chrome_RenderWidgetHostHWND'로 관측되지만, 해당 앱들의 appId는 'spotify'/
# 'slack'이라 `DEFAULT_TAB_CLASSES.get(appId)` 단계에서 None → editor 분기에
# 진입하지 않는다. `"chrome"` 키는 독립 Chrome 브라우저에만 적용된다.
DEFAULT_TAB_CLASSES = {
    "notepad":   {"editor": ("RichEditD2DPT",),            "overlay": ()},
    "notepad++": {"editor": (),                            "overlay": ("#32770",)},
    "chrome":    {"editor": ("Chrome_RenderWidgetHostHWND",), "overlay": ()},
}


def is_editor_class(appId: str, window_class_name: str) -> bool:
    """event_gainFocus 고빈도 호출 대응. 상수 dict 조회만."""
    if not appId or not window_class_name:
        return False
    spec = DEFAULT_TAB_CLASSES.get(appId)
    if not spec:
        return False
    return window_class_name in spec.get("editor", ())


def is_overlay_class(appId: str, foreground_class_name: str) -> bool:
    """event_gainFocus 고빈도 호출 대응. 상수 dict 조회만."""
    if not appId or not foreground_class_name:
        return False
    spec = DEFAULT_TAB_CLASSES.get(appId)
    if not spec:
        return False
    return foreground_class_name in spec.get("overlay", ())
