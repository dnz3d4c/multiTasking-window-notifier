# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""매칭 + 비프 재생 + 시그니처 dedup.

event_gainFocus / event_nameChange가 (appId, title, tab_sig)를 뽑아내면
Matcher.match_and_beep으로 넘겨 LookupIndex 조회 → 비프 재생까지 처리한다.
핫 패스에서 매 호출 파일 I/O는 피하고, 카운트만 FlushScheduler로 위임.

Matcher는 GlobalPlugin 인스턴스를 참조해 다음을 조회한다:
    - plugin.appList            (idx → entry 역변환용)
    - plugin._lookup            (windowLookup / appLookup)
    - plugin._flush_scheduler   (notify_switch / maybe_flush)
    - plugin.appListFile        (store.record_switch 경로)

역방향(Matcher → GlobalPlugin) 의존은 이 4개뿐. 반대는 없다.
"""

from __future__ import annotations

from logHandler import log

from . import beepPlayer
from . import store
from . import settings
from .appIdentity import makeKey, splitKey
from .constants import SCOPE_APP, SCOPE_WINDOW

# beepPlayer 모듈 자체를 import하고 호출 시점에 속성 lookup한다.
# `from .beepPlayer import play_beep`로 바인딩하면 테스트에서 beepPlayer 모듈에
# monkeypatch해도 본 모듈의 참조는 안 바뀌어 fake 비프가 작동 안 한다.


class Matcher:
    """매칭 로직과 비프 재생을 캡슐화.

    dedup 상태(`last_event_sig`)는 인스턴스 속성으로 보유한다. 테스트/복귀
    시나리오에서는 `matcher.last_event_sig = None` 직접 대입으로 초기화.
    """

    def __init__(self, plugin):
        self._plugin = plugin
        # 시그니처 기반 dedup — (appId, title, tab_sig)가 연속으로 같으면 skip.
        # 확정 탭 전환은 title 또는 tab_sig(hwnd)가 바뀌므로 자연 통과하고,
        # 같은 탭 자식 컨트롤 재진입 같은 이벤트 중복 폭주만 흡수한다.
        self.last_event_sig = None

    def _resolve_beep_pair(self, matched_key, scope, appId):
        """v4 (app_idx, tab_idx) 쌍 결정.

        Returns:
            tuple: (app_idx, tab_idx_or_none).
                - scope=app: (appBeepMap[real_appId], None). 단음 재생.
                - scope=window: (appBeepMap[real_appId], entry.tabBeepIdx). 2음 재생.

        title 역매핑 케이스(Alt+Tab 오버레이에서 obj.appId='explorer'로 들어왔는데
        정작 등록된 entry는 'notepad|Memo')에 대비해 호출 인자 `appId` 대신
        matched_key에서 추출한 real_app_id로 appBeepMap을 조회한다.

        appBeepMap이나 tabBeepIdx가 미설정인 드문 케이스는 0으로 폴백해 무음은
        피한다(할당은 _ensure_beep_assignments가 보장하지만 race 방어).
        """
        app_list_file = self._plugin.appListFile
        if scope == SCOPE_APP:
            real_app_id = matched_key
        else:
            real_app_id, _ = splitKey(matched_key)
        app_idx = store.get_app_beep_idx(app_list_file, real_app_id)
        if app_idx is None:
            log.warning(
                f"mtwn: appBeepMap miss appId={real_app_id!r} — falling back to 0"
            )
            app_idx = 0
        if scope == SCOPE_APP:
            return app_idx, None
        # SCOPE_WINDOW
        tab_idx = store.get_tab_beep_idx(app_list_file, matched_key)
        if tab_idx is None:
            log.warning(
                f"mtwn: tabBeepIdx miss key={matched_key!r} — falling back to 0"
            )
            tab_idx = 0
        return app_idx, tab_idx

    def match_and_beep(self, appId, title, tab_sig=0):
        """공통 매칭 루틴. 이벤트 훅(event_gainFocus / event_nameChange)이
        매칭 소스를 결정한 뒤 호출.

        매칭 우선순위:
            1. windowLookup 정확 매치 (key=appId|title) → 창 비프
            2. windowLookup title-only 역매핑 → 창 비프 (Alt+Tab 오버레이 호환)
            3. appLookup (appId) → 앱 비프
            4. 미스 → no-op

        Args:
            tab_sig: 탭/창 구분용 이벤트 식별자(보통 obj.windowHandle). 시그니처
                dedup sig에 포함되어 같은 (appId, title)이라도 다른 탭이면 통과
                시킨다. 0은 hwnd 미확보 상태 — 탭 구분 없는 기존 동작과 동치.
        """
        plugin = self._plugin
        app_list = plugin.appList
        window_lookup = plugin._lookup.windowLookup
        app_lookup = plugin._lookup.appLookup

        key = makeKey(appId, title)
        matched_key = None
        scope = None
        if key in window_lookup:
            matched_key, scope = key, SCOPE_WINDOW
        elif title in window_lookup:
            # title 역매핑 → 실제 entry 문자열로 변환 (record_switch는 entry 키가 필요)
            idx = window_lookup[title]
            matched_key, scope = app_list[idx], SCOPE_WINDOW
        elif appId and appId in app_lookup:
            # appId="" → Alt+Tab 오버레이 후보처럼 obj.appId가 실제 앱이 아닌 케이스.
            # focusDispatcher가 신뢰 불가 표시로 빈 문자열을 넘기므로 app_lookup skip.
            matched_key, scope = appId, SCOPE_APP

        if matched_key is None:
            # 비매칭 이벤트도 sig 연속성을 끊는다. 등록 안 된 창을 경유한 뒤
            # 등록 창으로 복귀할 때 직전 sig가 stale로 남아 sig_guard에 오 skip
            # 되는 버그 방지. 자식 컨트롤 재진입은 matched_key 확정 경로에서만
            # 발생하므로 이 리셋의 영향권 밖.
            self.last_event_sig = None
            return

        # 시그니처 dedup: (appId, title, tab_sig) 동일이면 skip.
        # 같은 탭의 자식 컨트롤 재진입(hwnd 동일)만 차단. 다른 창으로의 이동은
        # 위 matched_key=None 분기에서 sig가 None으로 리셋되므로, 등록 여부와
        # 무관하게 복귀 시 sig 동일성 비교가 어긋나 자연 통과한다.
        event_sig = (appId, title, tab_sig)
        if event_sig == self.last_event_sig:
            if settings.get("debugLogging"):
                log.info(f"mtwn: DBG sig_guard skip sig={event_sig!r}")
            return
        self.last_event_sig = event_sig

        app_idx, tab_idx = self._resolve_beep_pair(matched_key, scope, appId)
        beepPlayer.play_beep(
            app_idx, tab_idx, scope,
            duration=settings.get("beepDuration"),
            gap_ms=settings.get("beepGapMs"),
        )
        store.record_switch(plugin.appListFile, matched_key)
        plugin._flush_scheduler.notify_switch()
        plugin._flush_scheduler.maybe_flush()
