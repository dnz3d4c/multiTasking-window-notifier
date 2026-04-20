# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""애드온 전역 상수."""

ADDON_NAME = "multiTaskingWindowNotifier"

# 비프 테이블: C major 온음계(도·레·미·파·솔·라·시) 7음 × 5옥타브 = 35개 주파수.
# C3(~130Hz)부터 B7(~3951Hz)까지. v7부터 반음 64음에서 온음계 35음으로 전환.
# 이유: 반음 간격(C→C#, 1/12옥타브)은 청각적으로 색깔이 비슷해 인접 슬롯 변별이
# 어렵다는 실전 피드백. 온음계는 인접 슬롯 간격이 전음(C→D) 또는 장2도로 벌어져
# "도·레·미 …"로 확연히 구분된다.
# v4부터 app/tab 비프가 이 테이블을 공유. (app_idx, tab_idx)는 각각
# 독립적으로 0..BEEP_TABLE_SIZE-1 범위에서 배정된다.
BEEP_TABLE = [
    130, 146, 164, 174, 196, 220, 246,        # C3 D3 E3 F3 G3 A3 B3
    261, 293, 329, 349, 392, 440, 493,        # C4 D4 E4 F4 G4 A4 B4
    523, 587, 659, 698, 784, 880, 987,        # C5 D5 E5 F5 G5 A5 B5
    1047, 1175, 1319, 1397, 1568, 1760, 1976, # C6 D6 E6 F6 G6 A6 B6
    2093, 2349, 2637, 2794, 3136, 3520, 3951, # C7 D7 E7 F7 G7 A7 B7
]

# 비프 팔레트 슬롯 수. v4부터 MAX_ITEMS와 디커플. v7부터 35(7 × 5옥타브).
BEEP_TABLE_SIZE = len(BEEP_TABLE)

# 자동 할당 실사용 구간. v7부터 전 구간(0~35) 사용.
# 반음 스킴(v5~v6)에서는 청각 피로 때문에 상단을 절반 잘라 0~48만 썼으나,
# 온음계는 같은 옥타브 내 인접음 간격이 이미 벌어져 있어 고음까지 활용해도
# 변별력이 유지된다. B7(3951Hz)가 테이블 상한이며 쇳소리 영역(C8~) 자체가 제거됨.
BEEP_USABLE_START = 0
BEEP_USABLE_END = BEEP_TABLE_SIZE
BEEP_USABLE_SIZE = BEEP_USABLE_END - BEEP_USABLE_START

# 총 entry 상한 (scope=app + scope=window 합). v3까지는 BEEP_TABLE_SIZE와 강제
# 커플링되어 64였으나, v4에서 (app_idx, tab_idx) 쌍 구조가 도입되어 이론 조합이
# 현재 35×35=1225가 된다. 실용 상한으로 128을 적용. 초과 시 앱별 appBeepIdx가
# 공유될 수 있으나 청각 차원에서 탭 비프 b로 구분된다.
MAX_ITEMS = 128

# 등록 항목 scope.
#   SCOPE_WINDOW: 특정 창(appId|title 복합키). 활성 탭 제목이 일치할 때만 매칭.
#   SCOPE_APP   : 앱 전체(appId만). 같은 앱의 어떤 창/탭이든 매칭. 창 매치가
#                  우선이고 앱 매치는 fallback. v3 스키마에서 도입.
SCOPE_WINDOW = "window"
SCOPE_APP = "app"

# Alt+Tab 전환 중 Windows가 띄우는 시스템 오버레이의 windowClassName.
# Win10/Win11 공통으로 `event_gainFocus`가 후보 창별로 이 wcn을 들고 쏜다.
# 앱별 설정이 아니라 OS 차원의 고정값이라 `tabClasses` 프리셋이 아닌 constants에 둔다.
ALT_TAB_OVERLAY_WCN = "Windows.UI.Input.InputSite.WindowClass"

# Alt+Tab 오버레이의 **포그라운드(호스트) windowClassName**.
# obj.wcn(Windows.UI.Input.InputSite.WindowClass)은 UWP InputSite 공용이라
# Win+B 숨김 아이콘·시스템 트레이·알림 센터 등 다른 목록형 UI와도 겹친다.
# 따라서 Alt+Tab 진입 판정은 (obj.wcn == ALT_TAB_OVERLAY_WCN AND
# fg.wcn == ALT_TAB_HOST_FG_WCN) 두 축 AND로 묶어 오탐을 배제한다.
# Windows 11 Xaml Shell 고정값. 로케일 독립.
ALT_TAB_HOST_FG_WCN = "XamlExplorerHostIslandWindow"

# 디바운스 flush 임계치. __init__.py가 FlushScheduler를 kwargs 없이 생성하므로
# 실제 런타임 정책값이 이 두 상수다. GlobalPlugin이 필요 시 생성자 kwargs로
# 덮어쓸 수 있고, 향후 사용자 조정 옵션화도 이 상수를 기준으로 확장.
FLUSH_EVERY_N_DEFAULT = 10
FLUSH_INTERVAL_SEC_DEFAULT = 30

# 프리셋 데이터/빌더/불변식/폴백/마이그레이션은 Phase 7.1부터 `presets.py`가 단일
# 소유자. 과거 본 파일에 있던 `PRESETS` / `CLASSIC_PRESET_ID` / `_PENTATONIC_FREQS`
# / `_build_fifths_freqs` / 부팅 assert 블록은 전부 그쪽으로 이관.
# 다른 모듈이 이 파일에서 프리셋 심볼을 import하지 않도록 주의.
