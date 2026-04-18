# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""애드온 전역 상수."""

ADDON_NAME = "multiTaskingWindowNotifier"

# 비프 테이블: 64개 주파수. C3(~130Hz)부터 B8(~4978Hz)까지 반음 단위.
# v4부터 app/tab 비프가 이 테이블을 공유한다. (app_idx, tab_idx)는 각각
# 독립적으로 0..BEEP_TABLE_SIZE-1 범위에서 배정.
BEEP_TABLE = [
    130, 138, 146, 155, 164, 174, 185, 196, 207, 220, 233, 246,  # C3–B3
    261, 277, 293, 311, 329, 349, 370, 392, 415, 440, 466, 493,  # C4–B4
    523, 554, 587, 622, 659, 698, 740, 784, 831, 880, 932, 987,  # C5–B5
    1047, 1109, 1175, 1245, 1319, 1397, 1480, 1568, 1661, 1760, 1865, 1976,  # C6–B6
    2093, 2217, 2349, 2489, 2637, 2794, 2960, 3136, 3322, 3520, 3729, 3951,  # C7–B7
    4186, 4435, 4699, 4978,  # C8–B8
]

# 비프 팔레트 슬롯 수. v4부터 MAX_ITEMS와 디커플되었고, app_idx/tab_idx 자동 할당
# 알고리즘이 이 범위 안에서 거리 기반 최적화를 수행한다.
BEEP_TABLE_SIZE = len(BEEP_TABLE)

# 총 entry 상한 (scope=app + scope=window 합). v3까지는 BEEP_TABLE_SIZE와 강제
# 커플링되어 64였으나, v4에서 (app_idx, tab_idx) 쌍 구조가 도입되어 이론 조합이
# 64×64=4096이 되었다. 실용 상한으로 128을 적용. 초과 시 앱별 appBeepIdx가
# 공유될 수 있으나 청각 차원에서 탭 비프 b로 구분된다.
MAX_ITEMS = 128

# 등록 항목 scope.
#   SCOPE_WINDOW: 특정 창(appId|title 복합키). 활성 탭 제목이 일치할 때만 매칭.
#   SCOPE_APP   : 앱 전체(appId만). 같은 앱의 어떤 창/탭이든 매칭. 창 매치가
#                  우선이고 앱 매치는 fallback. v3 스키마에서 도입.
SCOPE_WINDOW = "window"
SCOPE_APP = "app"
