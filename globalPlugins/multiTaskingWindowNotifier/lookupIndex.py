# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""매칭용 룩업 인덱스.

등록된 앱/창 목록(appList)을 `event_gainFocus` / `event_nameChange`의 핫 패스
매칭에 쓸 수 있게 2종의 dict로 펼친다.

- windowLookup: scope=window entry용.
  1) 복합키(`appId|title`) → idx
  2) title-only 역매핑 → idx  (Alt+Tab 오버레이에서 obj.appId가 explorer로
     찍혀 정확 매치가 깨질 때 fallback)
  3) 구형 entry(`|` 없음)는 자기 자신이 그대로 등록됨
  4) title 충돌 시 먼저 등록된 idx 우선 (`setdefault`)

- appLookup: scope=app entry용. appId → idx. windowLookup이 모두 미스일 때
  마지막 fallback. 매칭 우선순위는 창 > 앱.

scope 판정은 생성자에 주입된 `meta_provider(entry) -> scope` 콜백에 위임한다.
GlobalPlugin의 `_meta_for`가 주입되며 내부에서 store.get_meta를 조회.
"""

from __future__ import annotations

from logHandler import log

from .appIdentity import splitKey
from .constants import SCOPE_APP


class LookupIndex:
    """매칭용 두 dict를 보유하며 rebuild()로 일괄 재구성."""

    def __init__(self, meta_provider):
        self._meta_provider = meta_provider
        self.windowLookup: dict = {}
        self.appLookup: dict = {}

    def rebuild(self, app_list) -> None:
        """appList 변경 시 호출. 두 dict를 통째로 새로 만든다."""
        window: dict = {}
        app: dict = {}
        for idx, entry in enumerate(app_list):
            scope = self._meta_provider(entry)
            if scope == SCOPE_APP:
                app.setdefault(entry, idx)
                continue
            # SCOPE_WINDOW
            window[entry] = idx
            _, title = splitKey(entry)
            if title and title != entry:
                window.setdefault(title, idx)
        # 원자적 교체: 중간 상태를 외부에 노출하지 않음.
        self.windowLookup = window
        self.appLookup = app
        log.debug(
            f"mtwn: LookupIndex.rebuild entries={len(app_list)} "
            f"window_keys={len(window)} app_keys={len(app)}"
        )
