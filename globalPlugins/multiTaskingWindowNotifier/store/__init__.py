# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""앱 목록 저장소 서브패키지.

Phase 3에서 `appListStore.py`(806줄)를 역할별로 분해하기 위해 도입됐다.
최종 형태:

    store/
      __init__.py                 # 공개 API 재노출
      core.py                     # _load_state + 외부 API 본체
      io.py                       # JSON I/O + 원자적 저장
      assign.py                   # 순차 비프 인덱스 할당
      migrations/
        __init__.py               # 마이그레이션 진입점
        legacy_list.py            # app.list → JSON
        normalize_titles.py       # title 정규화 + dedup
        v6_to_v7_beep_reassign.py # v7 재배정

Phase 3.1 시점: 빈 스캐폴딩. 기존 호출부는 여전히 `appListStore.py`를 import.
각 파일은 후속 커밋에서 순차 이관된다.
"""
