# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""앱 목록 저장소 서브패키지.

외부 호출부는 `from . import store` 또는 `from .store import load, save, ...`
형태로 접근한다. Phase 3.7에서 `appListStore.py`를 삭제하고 모든 호출부가
이 패키지를 직접 참조하도록 전환됐다.

내부 구조:

    store/
      __init__.py                 # 공개 API 재노출 (본 파일)
      core.py                     # _load_state + 외부 API 본체
      io.py                       # JSON I/O + 원자적 저장
      assign.py                   # 순차 비프 인덱스 할당
      migrations/
        __init__.py
        legacy_list.py            # app.list → JSON
        normalize_titles.py       # title 정규화 + dedup
        v6_to_v7_beep_reassign.py # v7 재배정 clear

v8 이상 스키마가 필요할 때는 `migrations/v7_to_v8.py` 1파일 신설하고
`core._load_state`에서 호출 위치를 지정한다.
"""

from .core import (
    flush,
    get_app_beep_idx,
    get_meta,
    get_tab_beep_idx,
    is_corrupted,
    load,
    prune_stale,
    record_switch,
    reload,
    reset_cache,
    save,
)

__all__ = [
    "flush",
    "get_app_beep_idx",
    "get_meta",
    "get_tab_beep_idx",
    "is_corrupted",
    "load",
    "prune_stale",
    "record_switch",
    "reload",
    "reset_cache",
    "save",
]
