# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""앱 목록 + 메타데이터 저장소 — 핫 패스 API 본체.

파일 포맷 (`app.json`, version=8):
    {
      "version": 8,
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

하위 호환:
    - v7 (aliases 필드 부재): 로드 시 모든 entry에 aliases=[] 자동 주입
      후 v8로 승격 저장. 비프 인덱스 재배정 없음 (단순 필드 확장).
    - v6 (반음 64음 테이블): 로드 시 기존 할당을 모두 버리고 v7 온음계 35음
      테이블 기준으로 순차 재할당. 1회성, 사용자는 주파수 재학습 필요.
      이어서 v8 aliases 주입까지 한 번에 승격.
    - v5 이하 (거리 최대화 할당): 같은 경로로 한 번에 v8까지 재배정.
    - v3 이하 (appBeepMap/tabBeepIdx 필드 부재): 동일 재할당 경로로 커버.
    - v2 (scope 필드 없음): v3→v7→v8 경유 자동 마이그레이션.
    - `app.json`이 없고 `app.list`가 있으면 최초 `load()`에서 JSON(v8)으로 마이그레이션.
      모든 줄을 scope="window"로 등록 + 순차 할당 + aliases=[] 후 `app.list.bak`으로 백업.
    - 새 설치(둘 다 없음)는 빈 목록으로 시작.

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

책임 분리 (Phase 3, migrations는 Phase 6.3에서 단일 파일로 통합):
    - store.io: 경로/시간/메타 헬퍼 + JSON I/O + 원자적 저장
    - store.assign: 순차 비프 인덱스 할당
    - store.migrations: app.list 마이그레이션 / title 정규화 + dedup / v7 재배정 clear
    - 본 모듈: 위 레이어를 엮는 핫 패스 API와 `_load_state` 선형 파이프라인.
"""

import os

from logHandler import log

from ..constants import (
    BEEP_TABLE_SIZE,
    MAX_ITEMS,
    SCOPE_WINDOW,
)
from .assign import _ensure_beep_assignments
from .io import _json_path, _load_from_json, _new_meta, _now_iso, _save_to_disk
from .migrations import (
    _backup_legacy_list,
    _migrate_from_list,
    _normalize_titles_in_place,
    clear_pre_v7_assignments,
    ensure_aliases_v8,
)

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
      ③ JSON 로드 또는 legacy `app.list` 마이그레이션
      ④ legacy 백업 — 신뢰 가능한 JSON이 확보된 경우만 1회
      ⑤ title normalize 마이그레이션 ("제목 없음 - 메모장" → "제목 없음")
      ⑥ v6 이하 → v7 비프 할당 재배정 + 자동 채움
      ⑥' v7 이하 → v8 aliases 필드 주입 (ensure_aliases_v8)
      ⑦ 캐시 등록
    """
    # ① 캐시
    if list_path in _states:
        return _states[list_path]

    # source_version: 디스크에서 읽어 온 원본 버전. 새 설치/legacy 마이그레이션은 0.
    # v7 이상이면 ⑥단계 clear를 건너뛴다(이미 새 테이블 기준 안정된 파일).
    state = {
        "items": [], "appBeepMap": {}, "dirty": False, "corrupted": False,
        "source_version": 0,
    }
    # ② 경로 결정
    json_path = _json_path(list_path)

    # ③ JSON 로드 또는 legacy 마이그레이션.
    # json_trustworthy: 이 로드 사이클에서 app.json이 source of truth로 확보됐는가.
    #   - JSON 존재 + 정상 로드: True (과거 마이그레이션에서 백업만 누락됐던 케이스 정리 대상)
    #   - JSON 없음 + app.list 마이그레이션 후 save 성공: True (표준 백업 타이밍)
    #   - JSON 손상 / save 실패 / 아무 파일도 없음: False (legacy 보존)
    json_trustworthy = False
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
            loaded_items, loaded_map, loaded_version = loaded
            state["items"] = loaded_items
            state["appBeepMap"] = loaded_map
            state["source_version"] = loaded_version
            json_trustworthy = True
    elif os.path.exists(list_path):
        # 구형 app.list 마이그레이션
        migrated = _migrate_from_list(list_path)
        if migrated:
            state["items"] = migrated
            state["dirty"] = True
            # 비프 할당을 먼저 채워 두고 저장 (디스크에 v8 포맷으로 기록).
            # `_migrate_from_list`는 `_new_meta`를 거치므로 각 item에 aliases=[]가
            # 이미 주입된 상태 → 별도 v8 승격 단계 불필요.
            _ensure_beep_assignments(state)
            if _save_to_disk(list_path, state):
                state["dirty"] = False
                json_trustworthy = True
            # 방금 새 순차 할당 + aliases=[] 주입을 마쳤으므로 ⑥/⑥' 단계를
            # 건너뛰도록 source_version=8로 표시. (⑤ title normalize는 아래에서
            # state["items"]에 대해 항상 실행되므로 legacy 경로도 자연 커버.)
            state["source_version"] = 8
            # 저장 실패 시 dirty 유지 → 다음 flush에서 재시도

    # ④ legacy 백업 — JSON이 신뢰 가능한 상태로 확보된 뒤 1회.
    # 과거 2곳에 흩어져 있던 호출을 여기로 모았다. 손상/save 실패 경로는
    # json_trustworthy=False라 자연스럽게 스킵되며, legacy 파일이 없는 케이스도
    # os.path.exists 가드로 no-op.
    if json_trustworthy and os.path.exists(list_path):
        _backup_legacy_list(list_path)

    # ⑤ title normalize 마이그레이션: "제목 없음 - 메모장" → "제목 없음".
    # corrupted(state["items"]==[])는 변경이 없어 자연스럽게 통과. 정상 로드/legacy
    # 마이그레이션 결과 모두에 적용된다. 변경이 있으면 디스크에 영구화.
    if _normalize_titles_in_place(state):
        if _save_to_disk(list_path, state):
            state["dirty"] = False
        # 저장 실패 시 dirty 유지 → 다음 flush/save에서 재시도

    # ⑥ 비프 할당 마이그레이션.
    #   - v7 파일: clear_pre_v7_assignments는 no-op. _ensure_beep_assignments가 누락된
    #     항목만 채움 (부분 보강).
    #   - v6 이하 파일: clear_pre_v7_assignments가 기존 할당을 전부 버리고,
    #     _ensure_beep_assignments가 순차 방식으로 1회성 재배정.
    #     v6(반음 64)과 v7(온음계 35)은 테이블 크기/주파수 의미가 동시에 바뀌어
    #     기존 인덱스 의미가 보존되지 않기 때문. 사용자 직관 모델("등록 순서대로
    #     한 음씩 위로")은 clear 후 순차 재배정이 자연스럽게 유지한다.
    #   - v5 이하 / v3 이하(appBeepMap/tabBeepIdx 부재) 모두 동일 경로로 v7까지 승격.
    clear_pre_v7_assignments(state)
    if _ensure_beep_assignments(state):
        state["dirty"] = True

    # ⑥' v7 이하 → v8 aliases 필드 주입.
    # _load_from_json이 로드 시점에 이미 aliases=[]를 주입하지만, 본 단계는
    # source_version < 8일 때 dirty=True를 세팅해 파일에 version=8을 확실히
    # 기록하게 한다. 비프 재배정/테이블 변경은 없다.
    ensure_aliases_v8(state)

    if state["dirty"]:
        if _save_to_disk(list_path, state):
            state["dirty"] = False
            state["source_version"] = 8

    # ⑦ 캐시 등록
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


def get_app_beep_idx(list_path: str, appId: str):
    """appId에 할당된 BEEP_TABLE 인덱스(앱 비프 a) 조회.

    appBeepMap에 없으면 None. 호출부는 None이면 매칭 실패로 간주하거나
    fallback 로직을 적용할 수 있다. 정상 흐름에서는 _ensure_beep_assignments가
    모든 등록 appId에 대해 채워두므로 None이 나오면 드문 타이밍 이슈일 수 있다.
    """
    state = _load_state(list_path)
    idx = state.get("appBeepMap", {}).get(appId)
    if isinstance(idx, int) and 0 <= idx < BEEP_TABLE_SIZE:
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
            if isinstance(idx, int) and 0 <= idx < BEEP_TABLE_SIZE:
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
