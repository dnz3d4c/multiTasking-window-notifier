# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""앱 목록 + 메타데이터 저장소.

파일 포맷 (`app.json`, version=4):
    {
      "version": 4,
      "appBeepMap": {"chrome": 0, "notepad": 24, ...},
      "items": [
        {"key": "appId|title", "scope": "window",
         "appId": "...", "title": "...",
         "tabBeepIdx": 0,
         "registeredAt": "YYYY-MM-DDTHH:MM:SS",
         "switchCount": 0,
         "lastSeenAt": null | "YYYY-MM-DDTHH:MM:SS"},
        {"key": "appId", "scope": "app",
         "appId": "...", "title": "",
         "registeredAt": "...", "switchCount": 0, "lastSeenAt": null}
      ]
    }

v4 변경점:
    - top-level `appBeepMap` — appId → BEEP_TABLE 인덱스. 같은 appId의 모든
      scope=window entry가 공유하는 "앱 비프"(a). scope=app entry가 없어도
      자동 할당되어 모든 appId가 항상 base 음을 가진다.
    - scope=window entry에 `tabBeepIdx` 필드 — 같은 appId 내에서 고유한 "탭
      비프"(b). scope=app entry는 tabBeepIdx를 갖지 않음(단음 재생).
    - entry 리스트 idx와 비프 idx가 완전 분리 — 중간 entry 삭제가 다른 entry의
      주파수에 영향 없음.

하위 호환:
    - v3 (appBeepMap 없음, tabBeepIdx 없음): 로드 시 거리 기반 알고리즘으로
      appBeepMap과 tabBeepIdx를 재할당. 기존 enumerate idx는 버린다. 사용자는
      주파수 재학습 필요하나 변별력이 최대화됨.
    - v2 (scope 필드 없음): v3 경유 자동 마이그레이션 후 v4로 승격.
    - `app.json`이 없고 `app.list`가 있으면 최초 `load()`에서 JSON(v4)으로 마이그레이션.
      모든 줄을 scope="window"로 등록 + 거리 기반 할당 후 `app.list.bak`으로 백업.
    - 새 설치(둘 다 없음)는 빈 목록으로 시작.

외부 API (기존 호출부 호환):
    load(path)               -> list[str]    key 리스트만 반환
    save(path, keys)         -> None          keys 순서 저장 (기존 메타 보존)
    record_switch(path, key) -> None          메모리 switchCount/lastSeenAt 갱신 (dirty 플래그)
    flush(path)              -> None          dirty 상태면 디스크 쓰기 (원자적)
    reload(path)             -> list[str]    flush 후 캐시 무효화 + 재로드
    get_meta(path, key)      -> dict|None    항목 메타 조회
    get_app_beep_idx(path, appId) -> int|None  appBeepMap 조회 (v4)
    get_tab_beep_idx(path, key)   -> int|None  scope=window entry의 tabBeepIdx (v4)
    prune_stale(path, iso)   -> list[str]    (#7 창 닫기 알림 기능 대비)

path 인자는 기존 `app.list` 경로를 그대로 받는다. 내부에서 같은 디렉터리의
`app.json`으로 변환해 사용하므로 호출부는 수정 불필요.
"""

import json
import os
from datetime import datetime

from logHandler import log

from .appIdentity import makeKey, normalize_title, splitKey
from .constants import BEEP_TABLE_SIZE, MAX_ITEMS, SCOPE_APP, SCOPE_WINDOW

# 본 모듈은 데이터 레이어다. 실패 시 `log`로만 보고하고 `ui.message`는 호출하지 않는다.
# 사용자 대면 알림은 상위 레이어(__init__.py의 script_* 등)에서 반환값으로 판단해 처리.


# path(app.list 경로) → 상태 캐시
# 상태 형태:
#   {
#     "items": list[dict],       # 각 entry 메타. scope=window는 tabBeepIdx 포함
#     "appBeepMap": dict,        # appId → BEEP_TABLE idx (v4). 같은 appId entry들이 공유
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


def _new_meta(key: str, scope: str = SCOPE_WINDOW, tabBeepIdx: int = None) -> dict:
    """새 메타 항목 생성.

    scope=SCOPE_APP이면 key는 appId 자체, title은 빈 문자열, tabBeepIdx 없음.
    scope=SCOPE_WINDOW이면 key는 'appId|title' 복합키 형식이고 splitKey로 분해.
    tabBeepIdx는 scope=window 전용 필드로, 같은 appId 내 고유 탭 비프(b) idx.
    """
    if scope == SCOPE_APP:
        appId, title = key, ""
    else:
        appId, title = splitKey(key)
    meta = {
        "key": key,
        "scope": scope,
        "appId": appId,
        "title": title,
        "registeredAt": _now_iso(),
        "switchCount": 0,
        "lastSeenAt": None,
    }
    if scope == SCOPE_WINDOW and tabBeepIdx is not None:
        meta["tabBeepIdx"] = int(tabBeepIdx)
    return meta


def _assign_distant_idx(used, size: int = BEEP_TABLE_SIZE) -> int:
    """거리 기반 인덱스 할당.

    `used`에 포함되지 않은 i in [0, size) 중 min_j|i - used_j|가 최대인 i 반환.
    동률이면 가장 작은 i. used가 비면 0.

    포화 상태(len(used) >= size)에서도 가장 먼 기존 idx와의 거리 최대값을 반환
    (중복 허용). 호출부는 포화 로그를 자체적으로 남길 수 있다.

    Args:
        used: iterable of int. BEEP_TABLE idx 집합.
        size: 팔레트 크기. 기본 BEEP_TABLE_SIZE.

    Returns:
        int: 할당된 idx (0 ≤ result < size).
    """
    used_list = [int(x) for x in used if isinstance(x, int) or str(x).lstrip("-").isdigit()]
    if not used_list:
        return 0
    best_i = 0
    best_dist = -1
    for i in range(size):
        dist = min(abs(i - u) for u in used_list)
        if dist > best_dist:
            best_dist = dist
            best_i = i
    return best_i


def _load_from_json(json_path: str):
    """Returns:
        tuple(list, dict): 정상 로드 (items, appBeepMap). 파일 없거나 비어있으면 ([], {}).
        None: 파일은 있으나 파싱/구조 실패 (손상 신호).

    None과 ([], {})를 구분하는 이유:
        호출부(`_load_state`)가 "정상적으로 비어있음(=마이그레이션/백업 가능)"과
        "손상으로 인한 빈 상태(=구형 app.list는 건드리지 말고 보존)"를 구분해야 한다.

    appBeepMap은 v4부터 디스크에 저장된다. v3 이하는 빈 dict로 반환되고 호출부가
    거리 기반 알고리즘으로 재할당한다.
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
    # 값 검증: int + BEEP_TABLE 범위. 벗어나면 버림(호출부가 재할당).
    app_beep_map = {}
    for app_id, idx in raw_app_beep_map.items():
        if not isinstance(app_id, str):
            continue
        if not isinstance(idx, int) or not (0 <= idx < BEEP_TABLE_SIZE):
            log.warning(
                f"mtwn: appBeepMap[{app_id!r}]={idx!r} invalid, will be reassigned"
            )
            continue
        app_beep_map[app_id] = idx

    # 필수 필드 보강 (옛 포맷/손상 대비).
    # v2 → v3 → v4 자동 마이그레이션:
    #   - scope 누락 → SCOPE_WINDOW로 보정 (v2는 창 단위만 등록 가능했음)
    #   - 알 수 없는 scope 값 → SCOPE_WINDOW로 보정 (손상/오타 대비)
    #   - scope=window의 tabBeepIdx 누락/무효 → 호출부가 거리 기반 재할당 (v3 이하)
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
        # 디스크 값으로 다시 덮이지 않도록 별도 처리. tabBeepIdx는 scope=window에서
        # 유효 정수일 때만 수용.
        for k, v in it.items():
            if k == "scope":
                continue
            if k == "tabBeepIdx":
                if scope == SCOPE_WINDOW and isinstance(v, int) and 0 <= v < BEEP_TABLE_SIZE:
                    meta["tabBeepIdx"] = v
                continue
            if k in meta:
                meta[k] = v
        fixed.append(meta)
    return (fixed, app_beep_map)


def _migrate_from_list(list_path: str) -> list:
    """구형 `app.list` → 메타 딕셔너리 리스트.

    v1 텍스트 포맷은 한 줄당 `appId|title` 또는 `title`만. title-only 줄은
    appId가 비게 되어 `_ensure_beep_assignments`가 appBeepMap에 등록할 수 없다.
    이런 줄은 placeholder appId("_legacy_<idx>")로 승격해 비프 할당을 받게 한다.
    """
    items = []
    try:
        with open(list_path, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f):
                k = line.strip()
                if not k:
                    continue
                meta = _new_meta(k)
                if not meta.get("appId"):
                    # "|" 없는 구형 줄 — splitKey가 ("", k)를 반환해 appId가 빔.
                    # 비프 할당을 받도록 고유 placeholder appId 부여.
                    placeholder = f"_legacy_{idx}"
                    new_key = makeKey(placeholder, k)
                    log.warning(
                        f"mtwn: legacy title-only entry {k!r} promoted to "
                        f"placeholder appId={placeholder!r}"
                    )
                    meta = _new_meta(new_key)
                items.append(meta)
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
    payload = {
        "version": 4,
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


def _normalize_items(items: list) -> tuple:
    """SCOPE_WINDOW 각 항목 title에 `normalize_title` 적용. 변경 시 key도 재구성.

    "제목 없음 - 메모장" → "제목 없음" 같이 꼬리 앱명 서픽스를 벗겨내
    Alt+Tab/editor/overlay 세 경로가 공유하는 "순수 탭 제목" 포맷으로 통일.
    항목은 복사본으로만 교체되어 호출자 원본이 변조되지 않는다.

    Returns: (new_items, changed). changed는 하나라도 title/key가 바뀌었으면 True.
    """
    changed = False
    out = []
    for it in items:
        scope = it.get("scope", SCOPE_WINDOW)
        if scope == SCOPE_WINDOW:
            old_title = it.get("title", "")
            new_title = normalize_title(old_title)
            if new_title != old_title:
                appId = it.get("appId", "")
                new_key = makeKey(appId, new_title)
                log.info(
                    f"mtwn: migrate normalize_title "
                    f"{old_title!r} → {new_title!r} key={it.get('key')!r} → {new_key!r}"
                )
                it = dict(it)
                it["title"] = new_title
                it["key"] = new_key
                changed = True
        out.append(it)
    return out, changed


def _dedup_items(items: list) -> tuple:
    """같은 key를 가진 항목 중복 제거. 먼저 나온 항목을 유지.

    `_normalize_items` 이후 호출되어야 의미가 있다. normalize 결과로 생긴
    새 key가 기존 다른 항목과 겹치면(예: "제목 없음 - 메모장"과 "제목 없음"
    둘 다 등록해둔 경우) 순서상 앞에 있던 것이 살아남는다.

    Returns: (new_items, changed). 중복이 하나라도 제거됐으면 changed=True.
    """
    changed = False
    seen = set()
    out = []
    for it in items:
        key = it.get("key", "")
        if key in seen:
            log.info(f"mtwn: migrate drop duplicate key={key!r}")
            changed = True
            continue
        seen.add(key)
        out.append(it)
    return out, changed


def _mark_dirty_if_changed(state: dict, new_items: list, changed: bool) -> bool:
    """changed=True면 state['items']를 new_items로 갱신하고 dirty=True로 표시.

    디스크 쓰기는 호출부 책임. 여기서는 메모리 상태만 반영한다.
    """
    if changed:
        state["items"] = new_items
        state["dirty"] = True
    return changed


def _ensure_beep_assignments(state: dict) -> bool:
    """appBeepMap과 tabBeepIdx를 채워 넣는다. v3→v4 마이그레이션 핵심.

    처리 순서 (결정론적):
        ① state['items'] 중 scope=window entry 순회해 appId 집합 수집
        ② appBeepMap에 빠진 appId 있으면 거리 기반 재할당 (순서: 등장 순)
        ③ scope=window entry 중 tabBeepIdx 없는 항목은 같은 appId의 기존
           tabBeepIdx 세트와 거리 최대값으로 재할당
        ④ 하나라도 추가됐으면 changed=True 반환 (호출부가 dirty/save 처리)

    이 함수는 state['appBeepMap']과 각 scope=window entry의 tabBeepIdx를 제자리
    변경한다. scope=app entry는 tabBeepIdx를 갖지 않으므로 건너뛴다.

    포화 처리 (len(used) >= BEEP_TABLE_SIZE): `_assign_distant_idx`가 이미 중복
    허용 방식으로 최대 거리 idx를 반환하므로 별도 분기 없이 동작. log.warning
    남기고 할당 진행.

    Returns: 뭐라도 추가됐으면 True.
    """
    items = state.get("items", [])
    app_beep_map = state.setdefault("appBeepMap", {})
    changed = False

    # ① + ②: appBeepMap 채우기. scope 관계없이 모든 entry의 appId에 대해 할당.
    for it in items:
        app_id = it.get("appId", "")
        if not app_id or app_id in app_beep_map:
            continue
        used = list(app_beep_map.values())
        if len(set(used)) >= BEEP_TABLE_SIZE:
            log.warning(
                f"mtwn: appBeepMap saturated (>= {BEEP_TABLE_SIZE}), "
                f"appId={app_id!r} will share existing idx"
            )
        new_idx = _assign_distant_idx(used, size=BEEP_TABLE_SIZE)
        app_beep_map[app_id] = new_idx
        changed = True
        log.info(f"mtwn: assign appBeepMap[{app_id!r}] = {new_idx}")

    # ③: scope=window entry에 tabBeepIdx 채우기. 같은 appId 내 기존 tabBeepIdx와
    # 거리 최대화. 이미 있는 항목은 건드리지 않음.
    tab_idx_by_app = {}
    for it in items:
        if it.get("scope") != SCOPE_WINDOW:
            continue
        app_id = it.get("appId", "")
        existing = it.get("tabBeepIdx")
        if isinstance(existing, int) and 0 <= existing < BEEP_TABLE_SIZE:
            tab_idx_by_app.setdefault(app_id, []).append(existing)
    for it in items:
        if it.get("scope") != SCOPE_WINDOW:
            continue
        if isinstance(it.get("tabBeepIdx"), int):
            continue
        app_id = it.get("appId", "")
        used = tab_idx_by_app.setdefault(app_id, [])
        if len(set(used)) >= BEEP_TABLE_SIZE:
            log.warning(
                f"mtwn: tabBeepIdx saturated for appId={app_id!r}, "
                f"key={it.get('key')!r} will share existing idx"
            )
        new_idx = _assign_distant_idx(used, size=BEEP_TABLE_SIZE)
        it["tabBeepIdx"] = new_idx
        used.append(new_idx)
        changed = True
        log.info(
            f"mtwn: assign tabBeepIdx key={it.get('key')!r} "
            f"appId={app_id!r} idx={new_idx}"
        )

    return changed


def _normalize_titles_in_place(state: dict) -> bool:
    """state['items']의 SCOPE_WINDOW 각 항목 title에 `normalize_title` 적용.

    3단계 서브 함수 조합:
      ① `_normalize_items` — SCOPE_WINDOW title·key 재구성
      ② `_dedup_items` — normalize 후 key 충돌 항목 제거(먼저 등록된 것 유지)
      ③ `_mark_dirty_if_changed` — 둘 중 하나라도 변경 있으면 state 갱신 + dirty

    Returns: 뭐라도 변경됐으면 True. True면 state["dirty"]=True로 표시한다
    (실제 디스크 쓰기는 호출부 책임).
    """
    items = state.get("items", [])
    if not items:
        return False

    normalized, norm_changed = _normalize_items(items)
    deduped, dedup_changed = _dedup_items(normalized)
    return _mark_dirty_if_changed(state, deduped, norm_changed or dedup_changed)


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
      ⑥ v3→v4 비프 할당 마이그레이션 (appBeepMap + tabBeepIdx 자동 채움)
      ⑦ 캐시 등록
    """
    # ① 캐시
    if list_path in _states:
        return _states[list_path]

    state = {"items": [], "appBeepMap": {}, "dirty": False, "corrupted": False}
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
            loaded_items, loaded_map = loaded
            state["items"] = loaded_items
            state["appBeepMap"] = loaded_map
            json_trustworthy = True
    elif os.path.exists(list_path):
        # 구형 app.list 마이그레이션
        migrated = _migrate_from_list(list_path)
        if migrated:
            state["items"] = migrated
            state["dirty"] = True
            # 비프 할당을 먼저 채워 두고 저장 (디스크에 v4 포맷으로 기록).
            _ensure_beep_assignments(state)
            if _save_to_disk(list_path, state):
                state["dirty"] = False
                json_trustworthy = True
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

    # ⑥ v3→v4 비프 할당 마이그레이션. 이미 v4 완결 파일이면 no-op.
    # legacy app.list 경로는 ③에서 이미 ensure한 뒤 저장했으므로 여기서는 보통
    # 변경 없다. JSON 로드 경로에서 appBeepMap/tabBeepIdx가 빠졌을 때만 채움.
    if _ensure_beep_assignments(state):
        state["dirty"] = True
        if _save_to_disk(list_path, state):
            state["dirty"] = False

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
