# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""앱 목록 + 메타데이터 저장소 — 핫 패스 API 본체.

파일 포맷 (`app.json`, version=9 고정):
    {
      "version": 9,
      "appBeepMap": {"chrome": 0, "notepad": 1, ...},
      "items": [
        {"key": "appId|title", "scope": "window",
         "appId": "...", "title": "...",
         "aliases": ["링키지접근성"],
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
    v9가 아닌 파일(버전 불일치, scope 누락/무효, 구조 파손 등)은 손상으로
    취급한다. 호출부는 `corrupted=True` + 빈 목록으로 시작하며, 조용한 자동
    보정은 없다. 사용자가 파일을 인지하고 복구/삭제할 기회를 갖는다.

    Phase 1 이전까지 존재하던 v1~v8 자동 마이그레이션 경로(app.list 텍스트
    포맷, scope 보정, 비프 재배정, aliases 주입/재정규화)는 전부 제거됐다.
    실 환경은 이미 v9로 수렴됐고, 잔존 마이그레이션은 no-op이었다.

외부 API:
    load(path)               -> list[str]    key 리스트만 반환
    save(path, keys, scopes) -> bool         keys 순서 저장 (기존 메타 보존)
    record_switch(path, key) -> None         메모리 switchCount/lastSeenAt 갱신
    flush(path)              -> bool         dirty 상태면 디스크 쓰기 (원자적)
    reload(path)             -> list[str]    flush 후 캐시 무효화 + 재로드
    get_meta(path, key)      -> dict|None    항목 메타 조회
    get_app_beep_idx(path, appId) -> int|None  appBeepMap 조회
    get_tab_beep_idx(path, key)   -> int|None  scope=window entry의 tabBeepIdx
    set_aliases(path, key, aliases) -> bool  entry의 aliases 필드 즉시 업데이트
    is_corrupted(path)       -> bool         app.json 손상 감지 플래그
    reset_cache()            -> None         pytest autouse fixture 전용 (__all__ 격리)

path 인자는 기존 `app.list` 경로를 그대로 받는다. 내부에서 같은 디렉터리의
`app.json`으로 변환해 사용하므로 호출부는 수정 불필요.

책임 분리:
    - store.io: 경로/시간/메타 헬퍼 + JSON I/O + 원자적 저장
    - store.assign: 순차 비프 인덱스 할당
    - 본 모듈: 위 레이어를 엮는 핫 패스 API와 `_load_state` 선형 파이프라인.
"""

import os

from logHandler import log

from ..constants import (
    MAX_ITEMS,
    SCOPE_WINDOW,
)
from .assign import _ensure_beep_assignments
from .io import _json_path, _load_from_json, _new_meta, _now_iso, _save_to_disk

# 본 모듈은 데이터 레이어다. 실패 시 `log`로만 보고하고 `ui.message`는 호출하지 않는다.
# 사용자 대면 알림은 상위 레이어(__init__.py의 script_* 등)에서 반환값으로 판단해 처리.


# path(app.list 경로) → 상태 캐시
# 상태 형태:
#   {
#     "items": list[dict],       # 각 entry 메타. scope=window는 tabBeepIdx 포함
#     "appBeepMap": dict,        # appId → BEEP_TABLE idx. 같은 appId entry들이 공유
#     "dirty": bool,             # 미저장 변경 유무
#     "corrupted": bool,         # 손상된 app.json 감지 플래그
#   }
#   corrupted: 최근 _load_state가 손상된 app.json을 만나 빈 상태로 초기화한 경우 True.
#              사용자 안내용 플래그. save() 성공 시 False로 리셋.
#
# 동시성 가정: NVDA main thread(= wx GUI 스레드) 단일 소유. 이벤트 훅·@script
# 핸들러·설정 패널 모두 같은 스레드에서 순차 호출되므로 `_states[k]=v`와
# `_states.get(k)` 모두 GIL 보호되는 단일 연산으로 충분. threading.Thread를
# 도입하는 시점이 오면 `threading.Lock`으로 접근부 감싸거나 copy-on-read
# 전략을 검토할 것. 현재는 Lock 선제 도입 = YAGNI.
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
      ② 경로 결정(list_path → json_path)
      ③ JSON 로드 — 손상이면 `corrupted=True` + 빈 목록 유지, 정상이면
         items/appBeepMap 채움
      ④ `_ensure_beep_assignments` — 누락된 필드만 보강 (손상 복구 후 또는
         신규 등록 경로에서 필요)
      ⑤ dirty면 `_save_to_disk`로 영구화
      ⑥ 캐시 등록

    실패 정책 (트랜잭션 대신 멱등 재시도):
        `_save_to_disk` 성공 시에만 `state["dirty"]=False`를 세팅한다.
        디스크 쓰기가 실패하면 `dirty=True`가 유지되어 다음 `flush()`에서
        자연스럽게 재시도된다. `_ensure_beep_assignments`는 멱등이므로 N회
        재시도해도 결과 동일. 트랜잭션/롤백 경로는 의도적으로 두지 않는다 —
        향후 유지보수 시 "부분 실패 방어"를 이유로 복잡한 상태 머신을 도입
        하지 말 것. `_save_to_disk` 실패는 극저 빈도이고 사용자 체감 영향 0.
    """
    # ① 캐시
    if list_path in _states:
        return _states[list_path]

    state = {"items": [], "appBeepMap": {}, "dirty": False, "corrupted": False}
    # ② 경로 결정
    json_path = _json_path(list_path)

    # ③ JSON 로드. version!=9, scope 누락/무효 등 v9 스펙 이탈은 전부
    # _load_from_json에서 None 반환으로 손상 취급. 손상 시 빈 목록을 유지해
    # 사용자가 파일을 복구/삭제할 기회를 준다(덮어쓰지 않음).
    if os.path.exists(json_path):
        loaded = _load_from_json(json_path)
        if loaded is None:
            log.warning(
                f"mtwn: app.json corrupted, memory state reset to empty list "
                f"path={json_path}"
            )
            state["corrupted"] = True
            # state["items"]는 기본값 [] 유지. dirty=False로 손상 파일을 덮어쓰지 않음.
        else:
            loaded_items, loaded_map = loaded
            state["items"] = loaded_items
            state["appBeepMap"] = loaded_map

    # ④ 비프 할당 보강. 누락된 appBeepMap/tabBeepIdx를 순차 할당으로 채운다.
    # 정상 로드된 v9 파일에서는 대부분 no-op. 손상 직후(빈 목록)에도 no-op.
    if _ensure_beep_assignments(state):
        state["dirty"] = True

    # ⑤ dirty면 디스크 영구화. 실패 시 dirty 유지 → 다음 flush에서 재시도.
    if state["dirty"]:
        if _save_to_disk(list_path, state):
            state["dirty"] = False

    # ⑥ 캐시 등록
    _states[list_path] = state
    return state


# ------------ 외부 API ------------


def load(list_path: str) -> list:
    """app.json에서 key 리스트 반환."""
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
    # appBeepMap은 기존 상태에서 복사 — 새 appId가 있으면 _ensure_beep_assignments가 할당.
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
    # save 성공 시(경로 무관) 손상 플래그 해소. is_corrupted 안내는 부팅 직후
    # 한 번만 띄우고, 다음 부팅부터는 정상 파일로 인지된다.
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


def get_app_beep_idx(list_path: str, appId: str):
    """appId에 할당된 BEEP_TABLE 인덱스(앱 비프 a) 조회.

    appBeepMap에 없으면 None. 호출부는 None이면 매칭 실패로 간주하거나
    fallback 로직을 적용할 수 있다. 정상 흐름에서는 _ensure_beep_assignments가
    모든 등록 appId에 대해 채워두므로 None이 나오면 드문 타이밍 이슈일 수 있다.
    """
    state = _load_state(list_path)
    idx = state.get("appBeepMap", {}).get(appId)
    if isinstance(idx, int) and 0 <= idx < MAX_ITEMS:
        return idx
    return None


def get_tab_beep_idx(list_path: str, key: str):
    """scope=window entry의 tabBeepIdx(탭 비프 b) 조회.

    scope=app entry이거나 해당 key가 없거나 tabBeepIdx가 비어 있으면 None.
    None이면 2음 재생이 아닌 단음 재생(scope=app과 동일)이 호출부 정책.
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

    정규화된 alias 목록을 통으로 교체한다 (append 아님). 등록/편집 UI가
    "이 창의 대체 제목은 지금 이것"을 한 번에 설정하는 용도.

    입력 필터링:
        - list/tuple/set 이외 타입은 빈 리스트로 간주
        - 각 요소는 str + non-empty만 수용, 나머지는 드롭
        - 저장되는 순서는 입력 순서 유지 (dedup 없음 — 호출부 책임)

    Args:
        list_path: 기존 app.list 경로 (내부에서 app.json으로 변환)
        key: 타깃 entry의 key. scope=window는 "appId|title", scope=app은 "appId".
        aliases: 새 alias 리스트. None/빈 리스트면 alias 제거.

    Returns:
        bool: 저장 성공 시 True. key 미존재나 디스크 쓰기 실패 시 False.
            호출부가 False를 보면 사용자에게 알린다.
    """
    state = _load_state(list_path)
    if isinstance(aliases, (list, tuple, set)):
        clean = [s for s in aliases if isinstance(s, str) and s]
    else:
        clean = []
    # 타깃 entry 찾기
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
