# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""저장소 I/O 레이어.

담당:
    - 경로 변환 (list_path → json_path, bak_path)
    - 시간 헬퍼 (`_now_iso`)
    - 메타 스켈레톤 (`_new_meta`)
    - JSON 역직렬화 (`_load_from_json`) — 정상/빈/손상 3상태 분기
    - 원자적 저장 (`_save_to_disk`) — `.tmp` → `os.replace`

비담당:
    - 비프 인덱스 할당 (store.assign)
    - 핫 패스 API (store.core)
"""

import json
import os
from datetime import datetime

from logHandler import log

from ..appIdentity import splitKey
from ..constants import (
    MAX_ITEMS,
    SCOPE_APP,
    SCOPE_WINDOW,
)


# ------------ 경로 변환 헬퍼 ------------


def _json_path(list_path: str) -> str:
    """`.../app.list` → `.../app.json`"""
    directory = os.path.dirname(list_path)
    return os.path.join(directory, "app.json")


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ------------ 메타 스켈레톤 ------------


def _new_meta(key: str, scope: str = SCOPE_WINDOW, aliases: list = None) -> dict:
    """새 메타 항목 생성.

    scope=SCOPE_APP이면 key는 appId 자체, title은 빈 문자열.
    scope=SCOPE_WINDOW이면 key는 'appId|title' 복합키 형식이고 splitKey로 분해.
    tabBeepIdx는 scope=window에서 나중에 `_ensure_beep_assignments`가 채운다 —
    여기서는 필드를 만들지 않는다.
    aliases는 scope 무관 추가 필드로, title-only 역매핑에 쓰일 대체 제목 배열.
    카카오톡처럼 Alt+Tab 오버레이 name과 foreground name이 다른 앱을 단일
    entry로 매칭하기 위한 보조 키. 기본값은 빈 리스트.
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


# ------------ JSON 역직렬화 ------------


def _load_from_json(json_path: str):
    """Returns:
        tuple(list, dict): 정상 로드 (items, appBeepMap).
            파일이 없으면 ([], {}) — 정상적 빈 상태.
        None: 파일은 있으나 v9 스펙을 벗어남 (손상 신호).

    손상 처리 정책 (Phase 1 마이그레이션 제거):
        v9 고정 스펙만 수용한다. version!=9, scope 누락/무효, 구조 파손 등은
        전부 None 반환으로 "손상"으로 취급되며, 호출부(`_load_state`)가
        `corrupted=True` + 빈 목록으로 시작한다. 조용한 자동 보정 경로는
        의도적으로 없다 — 사용자가 손상된 파일을 인지하고 수동 복구/삭제할
        기회를 갖는다.

        다만 tabBeepIdx 누락은 손상으로 보지 않는다. `_ensure_beep_assignments`
        가 신규 등록과 동일하게 채우는 "정상 복구 경로"다. aliases 역시 타입
        불량이면 `_new_meta` 기본값 `[]`로 폴백하는 타입 보강 수준.
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
    # 값 검증: int + BEEP_TABLE 범위. 벗어나면 버림(호출부가 재할당).
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

    # 필드 검증 (v9 스펙 엄수):
    #   - key 부재 / dict 아님 → 단일 항목 무시 (항목 skip)
    #   - scope 누락 / SCOPE_APP·SCOPE_WINDOW 외 값 → 전체 파일 손상으로 간주 → None
    #   - tabBeepIdx 누락/무효 → `_ensure_beep_assignments`가 채움 (정상 복구)
    #   - aliases 필드 타입 불량 → `_new_meta` 기본값 `[]`로 폴백 (타입 보강)
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
        # 디스크 값으로 메타 덮어쓰기. 단 scope는 위에서 정규화한 값이 우선이므로
        # 디스크 값으로 다시 덮이지 않도록 별도 처리. tabBeepIdx는 scope=window에서
        # 유효 정수일 때만 수용. aliases는 list + str 요소만 수용, 나머지는 []로 폴백.
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
                # list 아닌 값이면 _new_meta 기본값 [] 유지
                continue
            if k in meta:
                meta[k] = v
        fixed.append(meta)
    return (fixed, app_beep_map)


# ------------ 원자적 저장 ------------


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
    # v9는 현재 유일 스펙. 이전 버전의 자동 마이그레이션 경로는 Phase 1에서
    # 전부 제거됐고, 로드 시점에 version!=9는 손상으로 취급된다.
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
        # 남은 임시 파일 정리 (실패해도 조용히 무시)
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return False
