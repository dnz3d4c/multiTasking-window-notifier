# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""title 정규화 + dedup 마이그레이션.

담당: `_load_state` ⑤단계. 꼬리 " - 앱명" 서픽스를 벗겨내 Alt+Tab / editor /
overlay 3경로가 같은 키로 매칭되게 만든다.

처리 단계 (진입점은 `_normalize_titles_in_place`):
    ① `_normalize_items`       — SCOPE_WINDOW title·key 재구성
    ② `_dedup_items`           — normalize 결과 key 충돌 항목 제거
    ③ `_mark_dirty_if_changed` — 둘 중 하나라도 변경 있으면 state 갱신 + dirty
"""

from logHandler import log

from ...appIdentity import makeKey, normalize_title
from ...constants import SCOPE_WINDOW


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
