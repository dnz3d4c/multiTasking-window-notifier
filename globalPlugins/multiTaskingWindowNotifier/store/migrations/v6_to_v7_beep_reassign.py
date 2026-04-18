# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""v6 이하 → v7 비프 인덱스 전면 재배정 마이그레이션.

담당: `_load_state` ⑥단계 전반부. v6(반음 64) → v7(C major 온음계 35) 전환에서
테이블 크기와 주파수 의미가 동시에 바뀌었기 때문에, 기존 appBeepMap/tabBeepIdx
인덱스가 가리키던 음과 새 테이블의 음이 다르다. 이 불일치를 해소하려면 **기존
할당을 전부 버리고** `_ensure_beep_assignments`로 순차 재배정한다.

`clear_pre_v7_assignments`는 clear만 담당한다. 실제 재배정은 `store.assign.
_ensure_beep_assignments`가 이어서 수행한다 — 이 분리는 테스트에서 clear와
재배정 단계를 개별적으로 검증할 수 있게 해준다.

호출 조건: source_version < 7 (v3 이하 appBeepMap/tabBeepIdx 부재 케이스도 커버).
1회성: save 성공 직후 source_version=7로 승격되어 다음 로드부터 건너뜀.
"""

from logHandler import log

from ...constants import BEEP_USABLE_SIZE, BEEP_USABLE_START, SCOPE_WINDOW


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
