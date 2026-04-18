# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""앱별 탭 컨트롤 wcn 매핑 + 자동 학습.

데이터 포맷 (`tabClasses.json`, version=1):
    {
      "version": 1,
      "apps": {
        "notepad":   {"editor": ["RichEditD2DPT"], "overlay": []},
        "notepad++": {"editor": ["Scintilla"],     "overlay": ["#32770"]}
      }
    }

의미:
    - editor: 탭 전환 **확정 후** focus가 오는 자식 컨트롤의 windowClassName.
              이 wcn이 focus면 `foreground.name`을 탭 제목으로 삼아 매칭.
    - overlay: 탭 선택 **오버레이 상위창**의 windowClassName
              (= `api.getForegroundObject().windowClassName`).
              이 fgWcn이면 `obj.name`(리스트 항목 자체)을 탭 제목으로 삼아 매칭.

파일이 없으면 `DEFAULT_TAB_CLASSES`로 첫 `load()` 시 자동 생성된다.
파일이 있으면 DEFAULT와 **합집합 병합**(editor/overlay 각각) 후 변경이 있으면 저장.

외부 API:
    load(path)                       -> None   (로드 + 기본값 병합 + 캐시 채움)
    save(path)                       -> bool   (현재 캐시를 디스크에 원자적 저장)
    is_editor_class(appId, wcn)      -> bool
    is_overlay_class(appId, fg_wcn)  -> bool
    learn_editor(appId, wcn)         -> bool   (신규 추가했으면 True + save)
    reset_cache()                    -> None   (테스트 전용)

`learn_overlay`는 이번 Phase에서 노출하지 않는다. 수동 학습 단축키/UI가 별도
Phase로 다뤄질 때 함께 공개. 기본값(`#32770`)만으로 Notepad++ MRU는 즉시 동작.
"""

import json
import os

from logHandler import log


# 내장 기본값 — 최초 load 시 빈 파일에 기록되고, 기존 파일에도 합집합으로 병합된다.
# 실측 근거(Phase A 진단 로그):
#   - 메모장 Ctrl+Tab: obj.wcn='RichEditD2DPT'
#   - Notepad++ Ctrl+Tab (최종): obj.wcn='Scintilla'
#   - Notepad++ MRU 오버레이 진행 중: fgWcn='#32770'
DEFAULT_TAB_CLASSES = {
    "notepad":   {"editor": ("RichEditD2DPT",), "overlay": ()},
    "notepad++": {"editor": ("Scintilla",),     "overlay": ("#32770",)},
}


# 모듈 수준 캐시. 단일 파일(경로)만 다루므로 path-keyed 사전 대신 단일 상태로 둔다.
# _state = {"path": str, "apps": {appId: {"editor": set[str], "overlay": set[str]}}}
# set을 쓰는 이유는 is_*_class가 event_gainFocus에서 고빈도 호출되기 때문(O(1) 조회).
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
    """DEFAULT_TAB_CLASSES의 항목을 apps에 합집합으로 병합. 추가분이 있으면 True.

    사용자가 실수로 지워도 다음 로드 시 기본값이 자동으로 복원된다.
    """
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
    """디스크 파싱. 파일 없음=None (신규), 손상=빈 dict + 로그.

    None vs 빈 dict 구분: 없으면 기본값으로 초기 생성해 저장, 손상이면 캐시는
    기본값으로 채우되 덮어쓰기는 함(사용자가 뭔가 잘못 편집한 걸 정상으로 복구).
    """
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
    """원자적 저장(.tmp → os.replace). appListStore와 동일 패턴."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except Exception:
        log.error(f"mtwn: tabClasses mkdir failed path={path}", exc_info=True)
        return False

    # 안정적인 직렬화 순서(알파벳)로 diff 친화적. 기능상 영향 없음.
    payload = {
        "version": 1,
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
        # 파일 없음 — 기본값으로 초기 생성
        apps = _empty_apps_from_defaults()
        _save_to_disk(path, apps)
        log.info(f"mtwn: tabClasses.json created with defaults path={path}")
    else:
        # 파싱 성공(또는 손상이라 빈 dict) — DEFAULT 항목 누락분 병합
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
    """event_gainFocus 고빈도 호출 대응. 캐시 조회만."""
    if _state is None or not appId or not wcn:
        return False
    entry = _state["apps"].get(appId)
    if not entry:
        return False
    return wcn in entry.get("editor", set())


def is_overlay_class(appId: str, fg_wcn: str) -> bool:
    """event_gainFocus 고빈도 호출 대응. 캐시 조회만."""
    if _state is None or not appId or not fg_wcn:
        return False
    entry = _state["apps"].get(appId)
    if not entry:
        return False
    return fg_wcn in entry.get("overlay", set())


def learn_editor(appId: str, wcn: str) -> bool:
    """appId의 editor 리스트에 wcn 추가 + 저장. 신규 추가면 True, 이미 있으면 False.

    호출부(등록 성공 훅)에서 try/except로 감싸 best-effort로 쓰면 된다. 저장 실패
    시에도 예외 없이 False 반환(로그는 `_save_to_disk`가 찍는다).
    """
    if _state is None or not appId or not wcn:
        return False
    apps = _state["apps"]
    entry = apps.setdefault(appId, {"editor": set(), "overlay": set()})
    editor = entry.setdefault("editor", set())
    if wcn in editor:
        return False
    editor.add(wcn)
    if _save_to_disk(_state["path"], apps):
        log.info(f"mtwn: tabClasses learned editor appId={appId!r} wcn={wcn!r}")
        return True
    # 저장 실패 시 메모리 상태는 롤백
    editor.discard(wcn)
    return False
