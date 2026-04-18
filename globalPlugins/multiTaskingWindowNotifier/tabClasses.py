# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""앱별 탭 컨트롤 wcn 매핑.

데이터 포맷 (`tabClasses.json`, version=2):
    {
      "version": 2,
      "apps": {
        "notepad":   {"editor": ["RichEditD2DPT"], "overlay": []},
        "notepad++": {"overlay": ["#32770"]}
      }
    }

의미:
    - editor: Ctrl+Tab 확정 후 포커스가 오는 자식 컨트롤의 windowClassName.
              같은 탭 제목(예: 메모장 "제목 없음" 여러 개)을 구분하려면
              fg.name만으로는 불가능하고 자식 컨트롤의 hwnd가 탭마다 다르다는
              점을 이용해야 한다. 이 wcn이 focus면 `foreground.name`을 탭 제목,
              `obj.windowHandle`(자식)을 tab_sig로 삼아 매칭한다.
              **중요 게이트**: `wcn != fg_wcn` 조건이 필수. Firefox처럼 자식
              wcn이 최상위와 같은 앱은 이 분기에서 자동 제외되어 "모든 포커스
              이동마다 매칭" 병리가 재발하지 않는다.
    - overlay: 탭 선택 오버레이 상위창의 windowClassName
              (= `api.getForegroundObject().windowClassName`).
              이 fgWcn이면 `obj.name`(리스트 항목 자체)을 탭 제목으로 삼아 매칭.

탭 확정 전환은 **두 경로로 분업**한다:
    1. `event_nameChange` — 대부분의 앱(Firefox/Notepad++ 포함). 창의 title bar
       자체가 바뀌므로 foreground의 name 변경으로 직접 감지.
    2. editor 분기 — 메모장처럼 **같은 제목의 여러 탭**이 일상적인 앱. title이
       안 바뀌어 nameChange가 못 잡는 전환을 자식 hwnd 변경으로 포착.

파일이 없으면 `DEFAULT_TAB_CLASSES`로 첫 `load()` 시 자동 생성된다.
파일이 있으면 DEFAULT와 합집합 병합(editor/overlay 각각) 후 변경이 있으면 저장.

외부 API:
    load(path)                       -> None   (로드 + 기본값 병합 + 캐시 채움)
    save(path)                       -> bool   (현재 캐시를 디스크에 원자적 저장)
    is_editor_class(appId, wcn)      -> bool
    is_overlay_class(appId, fg_wcn)  -> bool
    reset_cache()                    -> None   (테스트 전용)
"""

import json
import os

from logHandler import log


# 내장 기본값. 최초 load 시 빈 파일에 기록되고, 기존 파일에도 합집합으로 병합된다.
# 실측 근거(진단 로그):
#   - 메모장 Ctrl+Tab: obj.wcn='RichEditD2DPT' (자식), fgWcn='Notepad' (상위)
#   - Notepad++ MRU 오버레이 진행 중: fgWcn='#32770'
# editor 등재 기준: **같은 제목의 여러 탭**이 정상 케이스인 앱. 메모장이
# 대표. Notepad++는 파일명 기반이라 title 중복이 드물어 nameChange만으로
# 충분(필요시 추후 추가). Firefox는 자식==최상위 wcn이라 editor 분기에
# 등재하면 안 되고 nameChange가 담당.
DEFAULT_TAB_CLASSES = {
    "notepad":   {"editor": ("RichEditD2DPT",), "overlay": ()},
    "notepad++": {"editor": (),                 "overlay": ("#32770",)},
}


# 모듈 수준 캐시.
# _state = {"path": str, "apps": {appId: {"editor": set[str], "overlay": set[str]}}}
_state = None


def reset_cache() -> None:
    """테스트 격리용. 런타임 코드는 호출하지 않는다."""
    global _state
    _state = None


# ------------ 내부 헬퍼 ------------


def _empty_apps_from_defaults() -> dict:
    """DEFAULT_TAB_CLASSES를 복사해서 set 기반 사전 생성."""
    apps = {}
    for appId, spec in DEFAULT_TAB_CLASSES.items():
        apps[appId] = {
            "editor": set(spec.get("editor", ())),
            "overlay": set(spec.get("overlay", ())),
        }
    return apps


def _merge_defaults_into(apps: dict) -> bool:
    """DEFAULT_TAB_CLASSES의 editor/overlay 항목을 apps에 합집합으로 병합."""
    changed = False
    for appId, spec in DEFAULT_TAB_CLASSES.items():
        entry = apps.setdefault(appId, {"editor": set(), "overlay": set()})
        entry.setdefault("editor", set())
        entry.setdefault("overlay", set())
        for field in ("editor", "overlay"):
            current = entry[field]
            for cls in spec.get(field, ()):
                if cls not in current:
                    current.add(cls)
                    changed = True
    return changed


def _load_from_disk(path: str):
    """디스크 파싱. 파일 없음=None (신규), 손상=빈 dict + 로그."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        log.error(f"mtwn: tabClasses load failed (JSON parse) path={path}", exc_info=True)
        return {}

    if not isinstance(data, dict):
        log.warning(f"mtwn: tabClasses root is not dict path={path}")
        return {}
    apps_raw = data.get("apps", {})
    if not isinstance(apps_raw, dict):
        log.warning(f"mtwn: tabClasses 'apps' not dict path={path}")
        return {}

    apps = {}
    for appId, spec in apps_raw.items():
        if not isinstance(appId, str) or not appId:
            continue
        if not isinstance(spec, dict):
            continue
        editor_list = spec.get("editor", [])
        overlay_list = spec.get("overlay", [])
        apps[appId] = {
            "editor": {
                e for e in (editor_list if isinstance(editor_list, list) else [])
                if isinstance(e, str) and e
            },
            "overlay": {
                o for o in (overlay_list if isinstance(overlay_list, list) else [])
                if isinstance(o, str) and o
            },
        }
    return apps


def _save_to_disk(path: str, apps: dict) -> bool:
    """원자적 저장(.tmp → os.replace). version=2 포맷."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except Exception:
        log.error(f"mtwn: tabClasses mkdir failed path={path}", exc_info=True)
        return False

    payload = {
        "version": 2,
        "apps": {
            appId: {
                "editor": sorted(entry.get("editor", set())),
                "overlay": sorted(entry.get("overlay", set())),
            }
            for appId, entry in sorted(apps.items())
        },
    }
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except Exception:
        log.error(f"mtwn: tabClasses save failed path={path}", exc_info=True)
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return False


# ------------ 외부 API ------------


def load(path: str) -> None:
    """파일 로드 + 기본값 병합. 변경이 있었거나 신규 생성이면 디스크에 저장."""
    global _state
    disk_apps = _load_from_disk(path)

    if disk_apps is None:
        apps = _empty_apps_from_defaults()
        _save_to_disk(path, apps)
        log.info(f"mtwn: tabClasses.json created with defaults path={path}")
    else:
        apps = disk_apps
        if _merge_defaults_into(apps):
            _save_to_disk(path, apps)

    _state = {"path": path, "apps": apps}


def save(path: str) -> bool:
    """현재 캐시를 디스크에 저장. 캐시 없으면 False."""
    if _state is None or _state.get("path") != path:
        return False
    return _save_to_disk(path, _state["apps"])


def is_editor_class(appId: str, wcn: str) -> bool:
    """event_gainFocus 고빈도 호출 대응. 캐시 set 조회만."""
    if _state is None or not appId or not wcn:
        return False
    entry = _state["apps"].get(appId)
    if not entry:
        return False
    return wcn in entry.get("editor", set())


def is_overlay_class(appId: str, fg_wcn: str) -> bool:
    """event_gainFocus 고빈도 호출 대응. 캐시 set 조회만."""
    if _state is None or not appId or not fg_wcn:
        return False
    entry = _state["apps"].get(appId)
    if not entry:
        return False
    return fg_wcn in entry.get("overlay", set())
