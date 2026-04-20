# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""비프 인덱스 할당 레이어.

담당:
    - 순차 인덱스 할당 (`_assign_next_idx`)
    - 자동 할당 루프 (`_ensure_beep_assignments`) — appBeepMap + tabBeepIdx

할당 규칙 (v6부터 유지, v7 전환에서 테이블 크기만 변경):
    - appBeepMap[appId]: 앱 등록 순서대로 BEEP_USABLE_START부터 0, 1, 2, ...
      한 슬롯씩 상승.
    - tabBeepIdx: appId별 독립 카운터로 각 앱마다 0부터.
    - 중간 gap은 재사용하지 않고 항상 max+1. 포화 시 구간 내 wrap + log.warning.

비담당:
    - I/O (store.io), 마이그레이션 (store.migrations), 핫 패스 (store.core).

Phase 1 후속 예고 (Phase 3):
    가변 slotCount 프리셋(Phase 4 Drum Kit/Lazer Pack 등) 도입을 위해 할당 공간을
    항상 `MAX_ITEMS=128`로 고정하고, 재생 시점에만 `effective_idx = stored_idx %
    preset.slotCount` modulo wrap으로 처리한다. 이때 이 모듈의 `_assign_next_idx`
    기본값 `size`가 BEEP_USABLE_SIZE → MAX_ITEMS로, 호출부 명시값이 일관되게
    MAX_ITEMS로 전환된다. 이 모듈은 `settings`를 import하지 않는 순수 함수 레이어로
    유지되며, 프리셋/슬롯 카운트 조회 책임은 `matcher`/`__init__.py`에 둔다.
    Phase 1(현재)은 구조 보존 — 주석만 예고를 남긴다.
"""

from logHandler import log

from ..constants import (
    BEEP_TABLE_SIZE,
    BEEP_USABLE_SIZE,
    BEEP_USABLE_START,
    SCOPE_WINDOW,
)


def _assign_next_idx(used, size: int = BEEP_TABLE_SIZE, start: int = 0) -> int:
    """순차 인덱스 할당. used의 [start, start+size) 구간 값의 max+1 반환.

    used에 구간 내 값이 없으면 start. 포화(max+1 >= start+size)면 구간 내 wrap
    후 log.warning. 중간 idx가 삭제로 비어도 gap을 채우지 않고 항상 증가 —
    "등록 순서대로 반음씩 위로"라는 사용자 인지 모델을 유지하기 위함이다.

    Args:
        used: BEEP_TABLE idx 집합. 구간 밖 값/비정수는 무시.
        size: 할당 구간 크기 (기본 BEEP_TABLE_SIZE).
        start: 할당 구간 시작 idx (기본 0). v5부터 BEEP_USABLE_START 전달.

    Returns:
        int: 할당된 idx (start ≤ result < start+size).
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
    """appBeepMap과 tabBeepIdx를 채워 넣는다. v3→v6 마이그레이션 핵심.

    처리 순서 (결정론적):
        ① state['items'] 순회해 appId 집합을 등장 순으로 수집
        ② appBeepMap에 빠진 appId 있으면 순차 할당(`_assign_next_idx`) —
           등장 순서대로 BEEP_USABLE_START부터 반음씩 위로
        ③ scope=window entry 중 tabBeepIdx 없는 항목은 같은 appId 내 기존
           tabBeepIdx의 max+1로 할당 (앱별 독립 0부터)
        ④ 하나라도 추가됐으면 changed=True 반환 (호출부가 dirty/save 처리)

    이 함수는 state['appBeepMap']과 각 scope=window entry의 tabBeepIdx를 제자리
    변경한다. scope=app entry는 tabBeepIdx를 갖지 않으므로 건너뛴다.

    포화 처리 (max+1 >= BEEP_USABLE_SIZE): `_assign_next_idx`가 구간 내 wrap 후
    log.warning 후 반환. 중복 허용 방식이라 예외는 발생하지 않는다.

    Returns: 뭐라도 추가됐으면 True.
    """
    items = state.get("items", [])
    app_beep_map = state.setdefault("appBeepMap", {})
    changed = False

    # ① + ②: appBeepMap 채우기. scope 관계없이 모든 entry의 appId에 대해 할당.
    # v5부터 할당 구간을 [BEEP_USABLE_START, BEEP_USABLE_END)로 축소.
    for it in items:
        app_id = it.get("appId", "")
        if not app_id or app_id in app_beep_map:
            continue
        used = list(app_beep_map.values())
        if len(set(used)) >= BEEP_USABLE_SIZE:
            log.warning(
                f"mtwn: appBeepMap saturated (>= {BEEP_USABLE_SIZE} usable slots), "
                f"appId={app_id!r} will share existing idx"
            )
        new_idx = _assign_next_idx(used, size=BEEP_USABLE_SIZE, start=BEEP_USABLE_START)
        app_beep_map[app_id] = new_idx
        changed = True
        log.info(f"mtwn: assign appBeepMap[{app_id!r}] = {new_idx}")

    # ③: scope=window entry에 tabBeepIdx 채우기. 같은 appId 내 기존 tabBeepIdx의
    # max+1로 순차 할당 (앱별 독립 카운터). 이미 있는 항목은 건드리지 않음.
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
        if len(set(used)) >= BEEP_USABLE_SIZE:
            log.warning(
                f"mtwn: tabBeepIdx saturated for appId={app_id!r} "
                f"(>= {BEEP_USABLE_SIZE} usable slots), "
                f"key={it.get('key')!r} will share existing idx"
            )
        new_idx = _assign_next_idx(used, size=BEEP_USABLE_SIZE, start=BEEP_USABLE_START)
        it["tabBeepIdx"] = new_idx
        used.append(new_idx)
        changed = True
        log.info(
            f"mtwn: assign tabBeepIdx key={it.get('key')!r} "
            f"appId={app_id!r} idx={new_idx}"
        )

    return changed
