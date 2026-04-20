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
    - 마이그레이션 (store.migrations)
    - 비프 인덱스 할당 (store.assign)
    - 핫 패스 API (store.core)

Phase 3.2 시점: 본 모듈은 `appListStore.py`에서 이 6개 함수만 분리한 상태.
기존 `appListStore.py`는 이 모듈을 재export해 외부 호출부 호환을 유지한다.
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


def _bak_path(list_path: str) -> str:
    return list_path + ".bak"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ------------ 메타 스켈레톤 ------------


def _new_meta(key: str, scope: str = SCOPE_WINDOW, tabBeepIdx: int = None,
              aliases: list = None) -> dict:
    """새 메타 항목 생성.

    scope=SCOPE_APP이면 key는 appId 자체, title은 빈 문자열, tabBeepIdx 없음.
    scope=SCOPE_WINDOW이면 key는 'appId|title' 복합키 형식이고 splitKey로 분해.
    tabBeepIdx는 scope=window 전용 필드로, 같은 appId 내 고유 탭 비프(b) idx.
    aliases는 v8부터 scope 무관 추가 필드로, title-only 역매핑에 쓰일 대체 제목
    배열. 카카오톡처럼 Alt+Tab 오버레이 name과 foreground name이 다른 앱을
    단일 entry로 매칭하기 위한 보조 키. 기본값은 빈 리스트.
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
        "aliases": list(aliases) if aliases else [],
        "registeredAt": _now_iso(),
        "switchCount": 0,
        "lastSeenAt": None,
    }
    if scope == SCOPE_WINDOW and tabBeepIdx is not None:
        meta["tabBeepIdx"] = int(tabBeepIdx)
    return meta


# ------------ JSON 역직렬화 ------------


def _load_from_json(json_path: str):
    """Returns:
        tuple(list, dict, int): 정상 로드 (items, appBeepMap, version).
            파일 없거나 비어있으면 ([], {}, 0).
        None: 파일은 있으나 파싱/구조 실패 (손상 신호).

    None과 ([], {}, 0)를 구분하는 이유:
        호출부(`_load_state`)가 "정상적으로 비어있음(=마이그레이션/백업 가능)"과
        "손상으로 인한 빈 상태(=구형 app.list는 건드리지 말고 보존)"를 구분해야 한다.

    appBeepMap은 v4부터 디스크에 저장된다. v3 이하는 빈 dict로 반환되고 호출부가
    거리 기반 알고리즘으로 재할당한다. version은 `_load_state`가 v4→v5
    강제 재배정 판단에 사용한다.
    """
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return ([], {}, 0)
    except Exception:
        log.error(f"mtwn: app.json load failed (JSON parse) path={json_path}", exc_info=True)
        return None

    if not isinstance(data, dict):
        log.warning(f"mtwn: app.json root is not dict path={json_path}")
        return None
    version = data.get("version", 0)
    if not isinstance(version, int):
        version = 0
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

    # 필수 필드 보강 (옛 포맷/손상 대비).
    # v2 → v3 → v4 → v8 자동 마이그레이션:
    #   - scope 누락 → SCOPE_WINDOW로 보정 (v2는 창 단위만 등록 가능했음)
    #   - 알 수 없는 scope 값 → SCOPE_WINDOW로 보정 (손상/오타 대비)
    #   - scope=window의 tabBeepIdx 누락/무효 → 호출부가 거리 기반 재할당 (v3 이하)
    #   - aliases 필드 부재 → []로 보정 (v7 이하). 타입 불량/요소 비문자열은 필터링.
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
    return (fixed, app_beep_map, version)


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
    # v9: normalize_title 파이프라인 확장(em-dash 1순위 + 카운트 토큰 흡수)에
    # 따른 일관성 보강. 데이터 스키마 자체는 v8과 동일(aliases 배열 보존)이며
    # _load_state ⑥'' 단계가 aliases 재정규화 + 백업 1회 처리. 비프 인덱스
    # 재배정/테이블 변경 없음. v7 이하 파일은 ⑥' ensure_aliases_v8를 거쳐
    # 여기 도달.
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
