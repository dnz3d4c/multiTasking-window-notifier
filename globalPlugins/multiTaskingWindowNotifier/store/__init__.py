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
    record_switch,
    reload,
    reset_cache,  # 내부 유틸: 테스트 전용. __all__에서 격리됨.
    save,
)

# 런타임 코드가 실제로 쓰는 9개만 공개. reset_cache는 conftest.py 등 테스트
# 코드가 명시 import로 쓰므로 재export는 유지하되 `from store import *`의
# 공개 표면에서는 빠진다. prune_stale은 Phase 2~6 기간 동안 Phase 8(창 닫기
# 알림) 대비로 남아 있었으나 실사용 0건 + Phase 8 착수 시 신규 설계 가능성이
# 높아 함수 본체/테스트와 함께 제거됨 (git log로 과거 구현 복원 가능).
__all__ = [
    "flush",
    "get_app_beep_idx",
    "get_meta",
    "get_tab_beep_idx",
    "is_corrupted",
    "load",
    "record_switch",
    "reload",
    "save",
]
