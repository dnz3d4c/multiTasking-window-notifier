# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""store 마이그레이션 서브패키지.

각 파일은 `_load_state` 선형 단계 중 하나를 담당한다:

    legacy_list.py           → ③ 구형 app.list 텍스트 포맷 → JSON
    normalize_titles.py      → ⑤ title 정규화 + dedup
    v6_to_v7_beep_reassign.py → ⑥ v6 이하 파일의 비프 인덱스 전면 재배정

v8 이상이 필요할 때는 `v7_to_v8.py` 1파일만 신설하고 `_load_state`에서 호출 위치를 지정한다.
"""
