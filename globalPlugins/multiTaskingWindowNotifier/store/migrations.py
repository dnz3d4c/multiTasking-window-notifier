# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""store 마이그레이션 통합 모듈.

과거 `store/migrations/` 서브패키지(legacy_list / normalize_titles /
v6_to_v7_beep_reassign 3파일)를 단일 파일로 통합. 각 함수는 `_load_state`
선형 단계 중 하나를 담당한다:

    _migrate_from_list       → ③ 구형 app.list 텍스트 → JSON
    _backup_legacy_list      → ③ 마이그레이션 완료 후 .bak 이동
    _normalize_titles_in_place → ⑤ title 정규화 + dedup
    clear_pre_v7_assignments → ⑥ v6 이하 비프 인덱스 clear (재배정은 assign.py)
    ensure_aliases_v8        → ⑥' v7 이하 모든 entry에 aliases=[] 주입 + v8 승격

v8는 scope=window/app 양쪽 entry에 aliases 배열을 추가하는 단순 필드
확장이라 비프 재배정/테이블 변경은 없다. `_load_from_json`이 이미 로드
시점에 aliases 부재 필드를 []로 채우므로 ensure_aliases_v8는 주로 dirty
플래그 세팅과 저장 트리거 역할을 맡아 파일에 `version=8`이 확실히 기록되게
한다.
"""

import os

from logHandler import log

from ..appIdentity import makeKey, normalize_title
from ..constants import BEEP_USABLE_SIZE, BEEP_USABLE_START, MAX_ITEMS, SCOPE_WINDOW
from .io import _bak_path, _new_meta


# ---------------- legacy app.list → JSON ----------------


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


def _backup_legacy_list(list_path: str) -> None:
    """app.list → app.list.bak 이름 변경. 정상 JSON 확보 후 1회 호출."""
    if not os.path.exists(list_path):
        return
    try:
        os.replace(list_path, _bak_path(list_path))
        log.info(f"mtwn: app.list backed up to {_bak_path(list_path)}")
    except Exception:
        log.warning("mtwn: app.list backup failed", exc_info=True)


# ---------------- title 정규화 + dedup ----------------


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


# ---------------- v6 이하 비프 인덱스 clear ----------------


def clear_pre_v7_assignments(state: dict) -> bool:
    """source_version < 7인 state의 appBeepMap과 tabBeepIdx를 모두 제거.

    제거 후 호출부가 `_ensure_beep_assignments`로 새 [BEEP_USABLE_START,
    BEEP_USABLE_START + BEEP_USABLE_SIZE) 구간에 순차 재배정해야 한다.
    dirty 플래그는 True로 세팅 — 호출부가 save로 영구화.

    Args:
        state: `_load_state`가 구성한 상태 dict. `source_version`, `items`,
            `appBeepMap` 키를 소비한다.

    Returns:
        bool: 실제 clear가 수행됐으면 True (source_version >= 7이면 False).
            테스트/디버그 목적이며 호출부는 반환값을 무시해도 동작 동일.
    """
    if state.get("source_version", 0) >= 7:
        return False

    has_legacy = state.get("appBeepMap") or any(
        "tabBeepIdx" in it
        for it in state.get("items", [])
        if it.get("scope") == SCOPE_WINDOW
    )
    if has_legacy:
        log.info(
            f"mtwn: migrate v{state.get('source_version', 0)}→v7, "
            f"clearing legacy beep assignments for sequential reassignment "
            f"in [{BEEP_USABLE_START}, {BEEP_USABLE_START + BEEP_USABLE_SIZE})"
        )

    state["appBeepMap"] = {}
    for it in state.get("items", []):
        if it.get("scope") == SCOPE_WINDOW and "tabBeepIdx" in it:
            del it["tabBeepIdx"]
    state["dirty"] = True
    return True


# ---------------- v7 이하 → v8 aliases 필드 주입 ----------------


def ensure_aliases_v8(state: dict) -> bool:
    """source_version < 8인 state의 모든 entry에 aliases 필드 확보 + dirty 표시.

    `_load_from_json`이 로드 시점에 이미 aliases 부재 필드를 []로 채우므로
    대부분의 entry는 아무 변경 없이 넘어간다. 본 함수의 실질 효과는:
      1) 혹시 _new_meta 경로를 거치지 않은 잔여 item에 대한 최종 방어
      2) source_version < 8 조건에서 dirty=True로 표시해 `version=8` 기록 유도

    Args:
        state: `_load_state`가 구성한 상태 dict.

    Returns:
        bool: 승격이 필요했으면 True (source_version >= 8이면 False, no-op).
    """
    if state.get("source_version", 0) >= 8:
        return False

    for it in state.get("items", []):
        aliases = it.get("aliases")
        if not isinstance(aliases, list):
            it["aliases"] = []
        else:
            # 비문자열/빈 문자열 요소 정리. list 타입 보존.
            it["aliases"] = [s for s in aliases if isinstance(s, str) and s]

    state["dirty"] = True
    log.info(
        f"mtwn: migrate v{state.get('source_version', 0)}→v8, "
        "aliases field ensured on all items"
    )
    return True
