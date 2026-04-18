# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""구형 `app.list` 텍스트 포맷 → JSON 마이그레이션.

담당: `_load_state` ③단계 중 JSON 부재 경로. v1 텍스트 포맷(한 줄당
`appId|title` 또는 `title`만)을 메타 딕셔너리 리스트로 변환한다.

v2 이상 설치에서는 이 경로가 타지 않는다(`app.json`이 이미 존재).
신규 설치 / 옛 사용자 이관 시에만 1회 호출된다.
"""

import os

from logHandler import log

from ...appIdentity import makeKey
from ...constants import MAX_ITEMS
from ..io import _bak_path, _new_meta


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
