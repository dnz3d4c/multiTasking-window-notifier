# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""앱 목록 + 메타데이터 저장소 (store 단일 파일).

파일 포맷 (`app.json`, version=9 고정):
    {
      "version": 9,
      "appBeepMap": {"chrome": 0, "notepad": 1, ...},
      "items": [
        {"key": "appId|title", "scope": "window",
         "appId": "...", "title": "...",
         "aliases": ["대화창제목"],
         "tabBeepIdx": 0,
         "registeredAt": "YYYY-MM-DDTHH:MM:SS",
         "switchCount": 0,
         "lastSeenAt": null | "YYYY-MM-DDTHH:MM:SS"},
        {"key": "appId", "scope": "app",
         "appId": "...", "title": "", "aliases": [],
         "registeredAt": "...", "switchCount": 0, "lastSeenAt": null}
      ]
    }

손상 처리:
    v9가 아닌 파일(버전 불일치, scope 누락/무효, 구조 파손)은 손상으로
    취급. 호출부는 `corrupted=True` + 빈 목록으로 시작하며 조용한 자동
    보정은 없다. 사용자가 파일을 인지하고 복구/삭제할 기회를 갖는다.
    v1~v8 자동 마이그레이션 경로는 전부 제거되고 v9 고정 스펙만 수용한다.

path 인자는 기존 `app.list` 경로를 그대로 받는다. 내부에서 같은 디렉터리의
`app.json`으로 변환해 사용하므로 호출부는 수정 불필요.

본 모듈은 데이터 레이어다. 실패 시 `log`로만 보고하고 `ui.message`는 호출
하지 않는다. 사용자 대면 알림은 상위 레이어(__init__.py의 script_* 등)에서
반환값으로 판단해 처리.

내부 구조 (top-down 실행 순서):
    1. JSON I/O — 경로·시간·메타·역직렬화·원자 저장
    2. 비프 인덱스 할당 — appBeepMap + tabBeepIdx 순차 배정
    3. 상태 파이프라인 — 모듈 캐시 + `_load_state` 6단계
    4. 공개 API 10개 — `__all__`에 명시
"""

import json
import os
from datetime import datetime

from logHandler import log

from .appIdentity import splitKey
from .constants import (
    MAX_ITEMS,
    SCOPE_APP,
    SCOPE_WINDOW,
)

__all__ = [
    "flush",
    "get_app_beep_idx",
    "get_meta",
    "get_tab_beep_idx",
    "is_corrupted",
    "load",
    "move_item",
    "record_switch",
    "reload",
    "save",
    "set_aliases",
]
# reset_cache는 테스트 격리 전용 유틸 — __all__에서 격리되나 명시 import는 가능.


# ================================================================
# 1. JSON I/O (경로 변환 / 시간 / 메타 / 역직렬화 / 원자적 저장)
# ================================================================


def _json_path(list_path: str) -> str:
    """`.../app.list` → `.../app.json`"""
    directory = os.path.dirname(list_path)
    return os.path.join(directory, "app.json")


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_meta(key: str, scope: str = SCOPE_WINDOW, aliases: list = None) -> dict:
    """새 메타 항목 생성.

    scope=SCOPE_APP이면 key는 appId 자체, title은 빈 문자열.
    scope=SCOPE_WINDOW이면 key는 'appId|title' 복합키고 splitKey로 분해.
    tabBeepIdx는 scope=window에서 나중에 `_ensure_beep_assignments`가 채운다.
    aliases는 title-only 역매핑용 대체 제목 배열. Alt+Tab 오버레이 이름과
    foreground title이 다른 앱을 단일 entry로 매칭하기 위한 보조 키.
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
        "aliases": list(aliases) if aliases else [],
        "registeredAt": _now_iso(),
        "switchCount": 0,
        "lastSeenAt": None,
    }


def _load_from_json(json_path: str):
    """v9 엄격 로드.

    Returns:
        tuple(list, dict): 정상 로드 (items, appBeepMap).
            파일이 없으면 ([], {}) — 정상적 빈 상태.
        None: v9 스펙 이탈 (손상).

    version!=9 / scope 누락·무효 / 구조 파손은 전부 None. tabBeepIdx 누락은
    손상이 아니라 `_ensure_beep_assignments`로 복구. aliases 타입 불량이면
    [] 폴백 (타입 보강).
    """
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return ([], {})
    except Exception:
        log.error(f"mtwn: app.json load failed (JSON parse) path={json_path}", exc_info=True)
        return None

    if not isinstance(data, dict):
        log.warning(f"mtwn: app.json root is not dict path={json_path}")
        return None
    version = data.get("version")
    if not isinstance(version, int) or version != 9:
        log.warning(
            f"mtwn: app.json version={version!r} is not 9, treated as corrupted "
            f"path={json_path}"
        )
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

    raw_app_beep_map = data.get("appBeepMap", {})
    if not isinstance(raw_app_beep_map, dict):
        log.warning(f"mtwn: app.json 'appBeepMap' field is not dict path={json_path}")
        raw_app_beep_map = {}
    app_beep_map = {}
    for app_id, idx in raw_app_beep_map.items():
        if not isinstance(app_id, str):
            continue
        if not isinstance(idx, int) or not (0 <= idx < MAX_ITEMS):
            log.warning(
                f"mtwn: appBeepMap[{app_id!r}]={idx!r} invalid, will be reassigned"
            )
            continue
        app_beep_map[app_id] = idx

    fixed = []
    for it in items[:MAX_ITEMS]:
        if not isinstance(it, dict) or "key" not in it:
            continue
        scope = it.get("scope")
        if scope not in (SCOPE_APP, SCOPE_WINDOW):
            log.warning(
                "mtwn: invalid scope %r in app.json item key=%r — file treated as corrupted",
                scope, it.get("key"),
            )
            return None
        meta = _new_meta(it["key"], scope=scope)
        for k, v in it.items():
            if k == "scope":
                continue
            if k == "tabBeepIdx":
                if scope == SCOPE_WINDOW and isinstance(v, int) and 0 <= v < MAX_ITEMS:
                    meta["tabBeepIdx"] = v
                continue
            if k == "aliases":
                if isinstance(v, list):
                    meta["aliases"] = [s for s in v if isinstance(s, str) and s]
                continue
            if k in meta:
                meta[k] = v
        fixed.append(meta)
    return (fixed, app_beep_map)


def _save_to_disk(list_path: str, state: dict) -> bool:
    """원자적 저장(.tmp → os.replace). 성공 시 True, 실패 시 False.

    사용자 알림은 호출부 책임. 본 함수는 log만 남긴다.
    """
    json_path = _json_path(list_path)
    try:
        os.makedirs(os.path.dirname(json_path), exist_ok=True)
    except Exception:
        log.error(f"mtwn: app.json mkdir failed path={json_path}", exc_info=True)
        return False

    tmp = json_path + ".tmp"
    payload = {
        "version": 9,
        "appBeepMap": dict(state.get("appBeepMap", {})),
        "items": state["items"][:MAX_ITEMS],
    }
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, json_path)
        return True
    except Exception:
        log.error(f"mtwn: app.json save failed path={json_path}", exc_info=True)
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return False


# ================================================================
# 2. 비프 인덱스 할당 (순차 배정)
# ================================================================


def _assign_next_idx(used, size: int = MAX_ITEMS, start: int = 0) -> int:
    """순차 인덱스 할당. used의 [start, start+size) 구간 값의 max+1 반환.

    used에 구간 내 값이 없으면 start. 포화(max+1 >= start+size)면 구간 내 wrap
    후 log.warning. 중간 idx가 삭제로 비어도 gap을 채우지 않고 항상 증가 —
    "등록 순서대로 반음씩 위로"라는 사용자 인지 모델 유지.
    """
    in_range = []
    for x in used:
        if isinstance(x, bool):
            continue
        if isinstance(x, int):
            n = x
        elif isinstance(x, str) and x.lstrip("-").isdigit():
            n = int(x)
        else:
            continue
        if start <= n < start + size:
            in_range.append(n)
    if not in_range:
        return start
    nxt = max(in_range) + 1
    if nxt >= start + size:
        nxt = start + ((nxt - start) % size)
        log.warning(
            f"mtwn: _assign_next_idx saturated, wrapping to {nxt} "
            f"(start={start}, size={size})"
        )
    return nxt


def _ensure_beep_assignments(state: dict) -> bool:
    """appBeepMap과 tabBeepIdx를 채워 넣는다.

    처리 순서 (결정론적):
        ① state['items'] 순회해 appId 집합을 등장 순으로 수집
        ② appBeepMap에 빠진 appId 있으면 순차 할당 — 등장 순서대로 0부터
        ③ scope=window entry 중 tabBeepIdx 없는 항목은 같은 appId 내 기존
           tabBeepIdx의 max+1로 할당 (앱별 독립 0부터)
        ④ 하나라도 추가됐으면 changed=True 반환

    포화(max+1 >= MAX_ITEMS): `_assign_next_idx`가 wrap 후 log.warning.
    중복 허용 방식이라 예외는 발생하지 않는다.
    """
    items = state.get("items", [])
    app_beep_map = state.setdefault("appBeepMap", {})
    changed = False

    # ①②: appBeepMap 채우기. scope 관계없이 모든 entry의 appId에 할당.
    for it in items:
        app_id = it.get("appId", "")
        if not app_id or app_id in app_beep_map:
            continue
        used = list(app_beep_map.values())
        if len(set(used)) >= MAX_ITEMS:
            log.warning(
                f"mtwn: appBeepMap saturated (>= {MAX_ITEMS} slots), "
                f"appId={app_id!r} will share existing idx"
            )
        new_idx = _assign_next_idx(used, size=MAX_ITEMS, start=0)
        app_beep_map[app_id] = new_idx
        changed = True
        log.info(f"mtwn: assign appBeepMap[{app_id!r}] = {new_idx}")

    # ③: scope=window entry에 tabBeepIdx 채우기. 앱별 독립 카운터.
    tab_idx_by_app = {}
    for it in items:
        if it.get("scope") != SCOPE_WINDOW:
            continue
        app_id = it.get("appId", "")
        existing = it.get("tabBeepIdx")
        if isinstance(existing, int) and 0 <= existing < MAX_ITEMS:
            tab_idx_by_app.setdefault(app_id, []).append(existing)
    for it in items:
        if it.get("scope") != SCOPE_WINDOW:
            continue
        if isinstance(it.get("tabBeepIdx"), int):
            continue
        app_id = it.get("appId", "")
        used = tab_idx_by_app.setdefault(app_id, [])
        if len(set(used)) >= MAX_ITEMS:
            log.warning(
                f"mtwn: tabBeepIdx saturated for appId={app_id!r} "
                f"(>= {MAX_ITEMS} slots), "
                f"key={it.get('key')!r} will share existing idx"
            )
        new_idx = _assign_next_idx(used, size=MAX_ITEMS, start=0)
        it["tabBeepIdx"] = new_idx
        used.append(new_idx)
        changed = True
        log.info(
            f"mtwn: assign tabBeepIdx key={it.get('key')!r} "
            f"appId={app_id!r} idx={new_idx}"
        )

    return changed


# ================================================================
# 3. 상태 파이프라인 (모듈 캐시 + _load_state)
# ================================================================


# path(app.list 경로) → 상태 캐시.
# 동시성: NVDA main thread(wx GUI) 단일 소유 가정. 이벤트 훅/@script/설정 패널
# 모두 같은 스레드에서 순차 호출되므로 GIL 보호되는 단일 연산으로 충분.
# threading.Thread 도입 시 threading.Lock 또는 copy-on-read 전략 검토할 것.
_states = {}


def reset_cache() -> None:
    """테스트 격리용: 모듈 전역 `_states` 캐시를 비운다.

    런타임 코드는 이 함수를 호출하지 않는다. pytest autouse fixture 전용.
    """
    _states.clear()


def _load_state(list_path: str) -> dict:
    """캐시를 우선 반환. 캐시 미스 시 아래 선형 단계로 상태 복원.

    입력: 사용자가 넘긴 `app.list` 경로.
    실제 저장은 같은 디렉터리의 `app.json` (내부 `_json_path` 변환).

    단계:
      ① 캐시 체크
      ② 경로 결정 (list_path → json_path)
      ③ JSON 로드 — 손상이면 `corrupted=True` + 빈 목록 유지
      ④ `_ensure_beep_assignments` — 누락 필드 보강
      ⑤ dirty면 `_save_to_disk`로 영구화
      ⑥ 캐시 등록

    실패 정책 (멱등 재시도): `_save_to_disk` 실패 시 `dirty=True`가 유지되어
    다음 `flush()`에서 자연스럽게 재시도. `_ensure_beep_assignments`는 멱등
    이라 N회 재시도해도 안전. 트랜잭션/롤백 경로는 의도적으로 두지 않는다.
    """
    # ①
    if list_path in _states:
        return _states[list_path]

    state = {"items": [], "appBeepMap": {}, "dirty": False, "corrupted": False}
    # ②
    json_path = _json_path(list_path)

    # ③ 손상 시 빈 목록을 유지해 사용자가 파일을 복구/삭제할 기회를 준다
    # (덮어쓰지 않음).
    if os.path.exists(json_path):
        loaded = _load_from_json(json_path)
        if loaded is None:
            log.warning(
                f"mtwn: app.json corrupted, memory state reset to empty list "
                f"path={json_path}"
            )
            state["corrupted"] = True
        else:
            loaded_items, loaded_map = loaded
            state["items"] = loaded_items
            state["appBeepMap"] = loaded_map

    # ④ 정상 로드된 v9 파일에서는 대부분 no-op. 손상 직후(빈 목록)에도 no-op.
    if _ensure_beep_assignments(state):
        state["dirty"] = True

    # ⑤
    if state["dirty"]:
        if _save_to_disk(list_path, state):
            state["dirty"] = False

    # ⑥
    _states[list_path] = state
    return state


# ================================================================
# 4. 공개 API (__all__에 명시한 10개)
# ================================================================


def load(list_path: str) -> list:
    """app.json에서 key 리스트 반환."""
    state = _load_state(list_path)
    return [it["key"] for it in state["items"]]


def save(list_path: str, keys, scopes=None) -> bool:
    """keys 순서대로 저장. 기존 key 메타는 보존, 새 key는 기본 메타 생성.

    원자적 쓰기 후 메모리 갱신: 디스크 쓰기가 성공했을 때만 `_states` 반영.
    실패 시 메모리 상태는 이전 그대로 유지되어 호출부 롤백과 일관성 보장.

    Args:
        keys: 저장할 key 리스트 (순서 보존, 최대 MAX_ITEMS).
        scopes: 신규 키 한정 scope 매핑 `{key: SCOPE_APP | SCOPE_WINDOW}`.
            기존 항목은 메타의 scope 보존. 미지정 신규 키는 SCOPE_WINDOW.

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
    # appBeepMap은 기존 상태 복사 — 새 appId가 있으면 _ensure_beep_assignments가 할당.
    temp_state = {
        "items": new_items,
        "appBeepMap": dict(state.get("appBeepMap", {})),
        "dirty": True,
    }
    _ensure_beep_assignments(temp_state)
    if not _save_to_disk(list_path, temp_state):
        return False
    state["items"] = new_items
    state["appBeepMap"] = temp_state["appBeepMap"]
    state["dirty"] = False
    # save 성공 시 손상 플래그 해소 — is_corrupted 안내는 부팅 직후 한 번만.
    state["corrupted"] = False
    return True


def record_switch(list_path: str, key: str) -> None:
    """매칭된 항목의 switchCount++, lastSeenAt=now. 메모리만 갱신.

    디스크 저장은 호출부가 `flush()`로 디바운스 제어.
    매칭 실패(존재하지 않는 key)는 디버그 로그만 남기고 무시.
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
    """dirty 상태일 때만 디스크에 저장."""
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
    """단일 항목 메타 조회. 없으면 None. 얕은 복사본 반환(외부 변조 방지)."""
    state = _load_state(list_path)
    for it in state["items"]:
        if it.get("key") == key:
            return dict(it)
    return None


def get_app_beep_idx(list_path: str, appId: str):
    """appId에 할당된 BEEP_TABLE 인덱스(앱 비프 a) 조회.

    appBeepMap에 없으면 None. 정상 흐름에선 _ensure_beep_assignments가 모든
    등록 appId를 채우므로 None이면 드문 타이밍 이슈일 수 있다.
    """
    state = _load_state(list_path)
    idx = state.get("appBeepMap", {}).get(appId)
    if isinstance(idx, int) and 0 <= idx < MAX_ITEMS:
        return idx
    return None


def get_tab_beep_idx(list_path: str, key: str):
    """scope=window entry의 tabBeepIdx(탭 비프 b) 조회.

    scope=app entry이거나 key가 없거나 tabBeepIdx가 비어 있으면 None.
    None이면 2음이 아닌 단음 재생이 호출부 정책.
    """
    state = _load_state(list_path)
    for it in state["items"]:
        if it.get("key") == key:
            if it.get("scope") != SCOPE_WINDOW:
                return None
            idx = it.get("tabBeepIdx")
            if isinstance(idx, int) and 0 <= idx < MAX_ITEMS:
                return idx
            return None
    return None


def set_aliases(list_path: str, key: str, aliases) -> bool:
    """entry의 aliases 배열을 업데이트하고 즉시 디스크에 저장.

    정규화된 alias 목록을 통으로 교체 (append 아님).

    입력 필터링:
        - list/tuple/set 이외 타입은 빈 리스트로 간주
        - 각 요소는 str + non-empty만 수용
        - 저장 순서는 입력 순서 유지 (dedup 없음 — 호출부 책임)

    Args:
        list_path: 기존 app.list 경로 (내부에서 app.json으로 변환)
        key: 타깃 entry의 key. scope=window는 "appId|title", scope=app은 "appId".
        aliases: 새 alias 리스트. None/빈 리스트면 alias 제거.

    Returns:
        bool: 저장 성공 시 True. key 미존재/디스크 실패 시 False.
    """
    state = _load_state(list_path)
    if isinstance(aliases, (list, tuple, set)):
        clean = [s for s in aliases if isinstance(s, str) and s]
    else:
        clean = []
    found = None
    for it in state["items"]:
        if it.get("key") == key:
            found = it
            break
    if found is None:
        log.warning(f"mtwn: set_aliases key not found {key!r}")
        return False
    found["aliases"] = clean
    state["dirty"] = True
    if _save_to_disk(list_path, state):
        state["dirty"] = False
        return True
    return False


def move_item(list_path: str, key: str, direction: str) -> bool:
    """items 배열에서 key 항목을 한 칸 위/아래로 이동하고 즉시 저장.

    등록 순서가 곧 표시 순서. 이동 성공 시 배열의 인접 두 요소를 swap하고
    원자적 `.tmp → replace`로 디스크 반영.

    Args:
        list_path: 기존 app.list 경로 (내부에서 app.json으로 변환)
        key: 이동할 entry key. scope=window는 "appId|title", scope=app은 "appId".
        direction: "up" 또는 "down".

    Returns:
        True: 이동 + 저장 성공.
        False: key 미존재 / 경계(up인데 idx=0, down인데 마지막) / direction 오값 /
            디스크 저장 실패.
    """
    if direction not in ("up", "down"):
        return False
    state = _load_state(list_path)
    items = state["items"]
    idx = None
    for i, it in enumerate(items):
        if it.get("key") == key:
            idx = i
            break
    if idx is None:
        log.warning(f"mtwn: move_item key not found {key!r}")
        return False
    if direction == "up":
        if idx == 0:
            return False
        swap_idx = idx - 1
    else:  # "down"
        if idx >= len(items) - 1:
            return False
        swap_idx = idx + 1
    items[idx], items[swap_idx] = items[swap_idx], items[idx]
    state["dirty"] = True
    if _save_to_disk(list_path, state):
        state["dirty"] = False
        return True
    return False
