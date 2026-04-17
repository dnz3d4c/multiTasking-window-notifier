# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""앱 목록 + 메타데이터 저장소.

파일 포맷 (`app.json`, version=3):
    {
      "version": 3,
      "items": [
        {"key": "appId|title", "scope": "window",
         "appId": "...", "title": "...",
         "registeredAt": "YYYY-MM-DDTHH:MM:SS",
         "switchCount": 0,
         "lastSeenAt": null | "YYYY-MM-DDTHH:MM:SS"},
        {"key": "appId", "scope": "app",
         "appId": "...", "title": "",
         "registeredAt": "...", "switchCount": 0, "lastSeenAt": null}
      ]
    }

하위 호환:
    - v2 (scope 필드 없음): 모든 항목을 scope="window"로 자동 마이그레이션.
      다음 save() 시점에 version=3로 기록되며 원본은 그대로 덮어쓰기.
    - `app.json`이 없고 `app.list`가 있으면 최초 `load()`에서 JSON(v3)으로 마이그레이션.
      모든 줄을 scope="window"로 등록 후 `app.list.bak`으로 백업.
    - 새 설치(둘 다 없음)는 빈 목록으로 시작.

외부 API (기존 호출부 호환):
    load(path)               -> list[str]    key 리스트만 반환
    save(path, keys)         -> None          keys 순서 저장 (기존 메타 보존)
    record_switch(path, key) -> None          메모리 switchCount/lastSeenAt 갱신 (dirty 플래그)
    flush(path)              -> None          dirty 상태면 디스크 쓰기 (원자적)
    reload(path)             -> list[str]    flush 후 캐시 무효화 + 재로드
    get_meta(path, key)      -> dict|None    항목 메타 조회
    prune_stale(path, iso)   -> list[str]    (#7 창 닫기 알림 기능 대비)

path 인자는 기존 `app.list` 경로를 그대로 받는다. 내부에서 같은 디렉터리의
`app.json`으로 변환해 사용하므로 호출부는 수정 불필요.
"""

import json
import os
from datetime import datetime

from logHandler import log

from .appIdentity import splitKey
from .constants import MAX_ITEMS, SCOPE_APP, SCOPE_WINDOW

# 본 모듈은 데이터 레이어다. 실패 시 `log`로만 보고하고 `ui.message`는 호출하지 않는다.
# 사용자 대면 알림은 상위 레이어(__init__.py의 script_* 등)에서 반환값으로 판단해 처리.


# path(app.list 경로) → 상태 캐시
# 상태 형태: {"items": list[dict], "dirty": bool, "corrupted": bool}
#   corrupted: 최근 _load_state가 손상된 app.json을 만나 빈 상태로 초기화한 경우 True.
#              사용자 안내용 플래그. save() 성공 시 False로 리셋.
_states = {}


def reset_cache() -> None:
    """테스트 격리용: 모듈 전역 `_states` 캐시를 비운다.

    런타임 코드는 이 함수를 호출하지 않는다. pytest autouse fixture 전용.
    """
    _states.clear()


# ------------ 경로 변환 헬퍼 ------------


def _json_path(list_path: str) -> str:
    """`.../app.list` → `.../app.json`"""
    directory = os.path.dirname(list_path)
    return os.path.join(directory, "app.json")


def _bak_path(list_path: str) -> str:
    return list_path + ".bak"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ------------ 내부 상태 로드/저장 ------------


def _new_meta(key: str, scope: str = SCOPE_WINDOW) -> dict:
    """새 메타 항목 생성.

    scope=SCOPE_APP이면 key는 appId 자체, title은 빈 문자열.
    scope=SCOPE_WINDOW이면 key는 'appId|title' 복합키 형식이고 splitKey로 분해.
    """
    if scope == SCOPE_APP:
        appId, title = key, ""
    else:
        appId, title = splitKey(key)
    return {
        "key": key,
        "scope": scope,
        "appId": appId,
        "title": title,
        "registeredAt": _now_iso(),
        "switchCount": 0,
        "lastSeenAt": None,
    }


def _load_from_json(json_path: str):
    """Returns:
        list: 정상 로드(파일 없거나 비어있으면 빈 리스트).
        None: 파일은 있으나 파싱/구조 실패 (손상 신호).

    None과 빈 리스트를 구분하는 이유:
        호출부(`_load_state`)가 "정상적으로 비어있음(=마이그레이션/백업 가능)"과
        "손상으로 인한 빈 상태(=구형 app.list는 건드리지 말고 보존)"를 구분해야 한다.
    """
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return []
    except Exception:
        log.error(f"mtwn: app.json load failed (JSON parse) path={json_path}", exc_info=True)
        return None

    if not isinstance(data, dict):
        log.warning(f"mtwn: app.json root is not dict path={json_path}")
        return None
    items = data.get("items", [])
    if not isinstance(items, list):
        log.warning(f"mtwn: app.json 'items' field is not list path={json_path}")
        return None
    if len(items) > MAX_ITEMS:
        log.warning(
            f"mtwn: app.json has {len(items)} items, exceeds limit({MAX_ITEMS}). "
            f"Only first {MAX_ITEMS} will be loaded."
        )
    # 필수 필드 보강 (옛 포맷/손상 대비).
    # v2 → v3 자동 마이그레이션:
    #   - scope 누락 → SCOPE_WINDOW로 보정 (v2는 창 단위만 등록 가능했음)
    #   - 알 수 없는 scope 값 → SCOPE_WINDOW로 보정 (손상/오타 대비)
    fixed = []
    for it in items[:MAX_ITEMS]:
        if not isinstance(it, dict) or "key" not in it:
            continue
        scope = it.get("scope", SCOPE_WINDOW)
        if scope not in (SCOPE_APP, SCOPE_WINDOW):
            log.warning(
                "mtwn: unknown scope %r in app.json item key=%r — coerced to %r",
                scope, it.get("key"), SCOPE_WINDOW,
            )
            scope = SCOPE_WINDOW
        meta = _new_meta(it["key"], scope=scope)
        # 디스크 값으로 메타 덮어쓰기. 단 scope는 위에서 정규화한 값이 우선이므로
        # 디스크 값으로 다시 덮이지 않도록 별도 처리.
        for k, v in it.items():
            if k == "scope":
                continue
            if k in meta:
                meta[k] = v
        fixed.append(meta)
    return fixed


def _migrate_from_list(list_path: str) -> list:
    """구형 `app.list` → 메타 딕셔너리 리스트."""
    items = []
    try:
        with open(list_path, "r", encoding="utf-8") as f:
            for line in f:
                k = line.strip()
                if k:
                    items.append(_new_meta(k))
    except Exception:
        log.error(f"mtwn: app.list migration load failed path={list_path}", exc_info=True)
        return []
    return items[:MAX_ITEMS]


def _save_to_disk(list_path: str, state: dict) -> bool:
    """원자적 저장(.tmp → os.replace). 성공 시 True, 실패 시 False.

    사용자 알림은 호출부의 책임. 본 함수는 log만 남긴다.
    """
    json_path = _json_path(list_path)
    try:
        os.makedirs(os.path.dirname(json_path), exist_ok=True)
    except Exception:
        log.error(f"mtwn: app.json mkdir failed path={json_path}", exc_info=True)
        return False

    tmp = json_path + ".tmp"
    payload = {"version": 3, "items": state["items"][:MAX_ITEMS]}
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, json_path)
        return True
    except Exception:
        log.error(f"mtwn: app.json save failed path={json_path}", exc_info=True)
        # 남은 임시 파일 정리 (실패해도 조용히 무시)
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return False


def _backup_legacy_list(list_path: str) -> None:
    if not os.path.exists(list_path):
        return
    try:
        os.replace(list_path, _bak_path(list_path))
        log.info(f"mtwn: app.list backed up to {_bak_path(list_path)}")
    except Exception:
        log.warning("mtwn: app.list backup failed", exc_info=True)


def _load_state(list_path: str) -> dict:
    """캐시를 우선 반환. 캐시 미스 시 JSON → app.list 마이그레이션 순으로 로드."""
    if list_path in _states:
        return _states[list_path]

    state = {"items": [], "dirty": False, "corrupted": False}
    json_path = _json_path(list_path)

    if os.path.exists(json_path):
        loaded = _load_from_json(json_path)
        if loaded is None:
            # JSON 파싱/구조 실패 — 구형 app.list는 건드리지 않고 보존.
            # 사용자는 손상된 app.json을 복구하거나 삭제할 기회를 가진다.
            log.warning(
                f"mtwn: app.json corrupted, memory state reset to empty list. "
                f"app.list backup skipped path={json_path}"
            )
            state["corrupted"] = True
            # state["items"]는 기본값 [] 유지. dirty=False도 유지(손상을 덮어쓰지 않도록).
        else:
            state["items"] = loaded
            # 정상 로드 시에만 지연 백업: 과거 마이그레이션에서 저장은 성공했으나
            # 백업은 실패했던 경우 app.json과 app.list가 공존할 수 있다. 이번에 정리.
            if os.path.exists(list_path):
                _backup_legacy_list(list_path)
    elif os.path.exists(list_path):
        # 구형 app.list 마이그레이션
        state["items"] = _migrate_from_list(list_path)
        if state["items"]:
            state["dirty"] = True
            if _save_to_disk(list_path, state):
                state["dirty"] = False
                _backup_legacy_list(list_path)
            # 저장 실패 시 dirty 유지 → 다음 flush에서 재시도

    _states[list_path] = state
    return state


# ------------ 외부 API ------------


def load(list_path: str) -> list:
    """app.json(또는 app.list 마이그레이션)에서 key 리스트 반환."""
    state = _load_state(list_path)
    return [it["key"] for it in state["items"]]


def save(list_path: str, keys, scopes=None) -> bool:
    """keys 순서대로 저장. 기존 key의 메타는 보존, 새 key는 기본 메타 생성.

    원자적 쓰기 후 메모리 갱신: 디스크 쓰기가 성공했을 때만 `_states`를 반영.
    실패 시 메모리 상태는 이전 그대로 유지되어 호출부 롤백과 일관성이 보장된다.

    Args:
        keys: 저장할 key 리스트 (순서 보존, 최대 MAX_ITEMS).
        scopes: 신규 키 한정 scope 매핑 `{key: SCOPE_APP | SCOPE_WINDOW}`.
            기존 항목은 메타에서 scope를 보존. 미지정 신규 키는 SCOPE_WINDOW.
            None을 넘기면 모든 신규 키가 SCOPE_WINDOW (기존 호환).

    Returns:
        bool: 디스크 쓰기 성공 여부. 실패 시 호출부가 사용자에게 알릴 책임.
    """
    scopes = scopes or {}
    state = _load_state(list_path)
    existing = {it["key"]: it for it in state["items"]}
    new_items = []
    for k in list(keys)[:MAX_ITEMS]:
        if k in existing:
            new_items.append(existing[k])
        else:
            new_items.append(_new_meta(k, scope=scopes.get(k, SCOPE_WINDOW)))
    # 임시 상태로 먼저 디스크 쓰기 시도. 성공 시에만 메모리 반영.
    temp_state = {"items": new_items, "dirty": True}
    if not _save_to_disk(list_path, temp_state):
        return False
    state["items"] = new_items
    state["dirty"] = False
    # 저장 성공 시 손상 플래그 해소. 사용자가 빈 상태를 인지한 뒤 새 항목을 추가해
    # 정상 파일로 전환된 상태.
    state["corrupted"] = False
    return True


def record_switch(list_path: str, key: str) -> None:
    """매칭된 항목의 switchCount++, lastSeenAt=now. 메모리만 갱신.

    디스크 저장은 호출부가 `flush()`로 디바운스 제어.
    매칭 실패(존재하지 않는 key)는 디버그 로그만 남기고 무시 — 이론상
    event_gainFocus에서 appLookup이 먼저 매칭되므로 여기에 도달했다면
    캐시 정합성 문제일 가능성 있음.
    """
    state = _load_state(list_path)
    for it in state["items"]:
        if it.get("key") == key:
            it["switchCount"] = int(it.get("switchCount", 0)) + 1
            it["lastSeenAt"] = _now_iso()
            state["dirty"] = True
            return
    log.debug(f"mtwn: record_switch key mismatch ({key!r}) — possible appLookup/state drift")


def flush(list_path: str) -> bool:
    """dirty 상태일 때만 디스크에 저장.

    Returns:
        bool: 성공(혹은 dirty 아님 — 저장할 필요 없음)이면 True.
    """
    state = _states.get(list_path)
    if state is None or not state["dirty"]:
        return True
    if _save_to_disk(list_path, state):
        state["dirty"] = False
        return True
    return False


def reload(list_path: str) -> list:
    """미저장 변경분을 flush한 뒤 캐시 무효화 + 디스크에서 재로드."""
    flush(list_path)
    _states.pop(list_path, None)
    return load(list_path)


def is_corrupted(list_path: str) -> bool:
    """최근 로드에서 app.json 손상이 감지되었으면 True.

    GlobalPlugin 초기화 시 1회 호출해 사용자에게 "목록 파일이 손상되어
    빈 상태로 시작합니다"를 지연 안내하는 용도.
    `save()` 성공 시 자동으로 False로 리셋된다.
    """
    state = _states.get(list_path)
    if state is None:
        return False
    return bool(state.get("corrupted", False))


def get_meta(list_path: str, key: str):
    """단일 항목 메타 조회. 없으면 None."""
    state = _load_state(list_path)
    for it in state["items"]:
        if it.get("key") == key:
            # 얕은 복사본 반환 (외부에서 실수로 변조 방지)
            return dict(it)
    return None


def prune_stale(list_path: str, before_iso: str) -> list:
    """`lastSeenAt`이 `before_iso`보다 오래되거나 None인 항목을 제거.

    Phase 2에서는 호출하지 않음. 이후 "창 닫기 알림"(#7) 기능 대비.
    비교는 문자열 기반이지만 `_now_iso()`가 naive datetime `YYYY-MM-DDTHH:MM:SS`
    포맷을 균일하게 쓰므로 문자열 정렬 == 시간 정렬. 타임존 표기가 섞이면 깨질
    수 있으니 추후 tz-aware로 바꿀 때는 비교 방식도 함께 갱신.

    Returns: 제거된 key 리스트.
    """
    state = _load_state(list_path)
    kept, removed = [], []
    for it in state["items"]:
        last = it.get("lastSeenAt")
        if last is not None and last >= before_iso:
            kept.append(it)
        else:
            removed.append(it.get("key", ""))
    if removed:
        state["items"] = kept
        state["dirty"] = True
    return removed
