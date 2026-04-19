# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""매칭용 룩업 인덱스.

등록된 앱/창 목록(appList)을 `event_gainFocus` / `event_nameChange`의 핫 패스
매칭에 쓸 수 있게 2종의 dict로 펼친다.

- windowLookup: scope=window entry + **alias를 가진 scope=app entry**의
  title-only 역매핑 테이블.
  1) 복합키(`appId|title`) → idx  (scope=window 정확 매치)
  2) title-only 역매핑 → idx  (Alt+Tab 오버레이에서 obj.appId가 explorer로
     찍혀 정확 매치가 깨질 때 fallback)
  3) 구형 entry(`|` 없음)는 자기 자신이 그대로 등록됨
  4) **aliases 필드(v8)** — scope=window/app 양쪽 entry의 alias 각각도
     setdefault로 역매핑 추가. 카카오톡처럼 Alt+Tab title("링키지접근성")과
     foreground title("카카오톡")이 다른 앱을 단일 entry로 매칭.
  5) title/alias 충돌 시 먼저 등록된 idx 우선 (`setdefault`)

- appLookup: scope=app entry용. appId → idx. windowLookup이 모두 미스일 때
  마지막 fallback. 매칭 우선순위는 창 > 앱. **단, Alt+Tab 오버레이 분기는
  match_appId=""를 넘기므로 이 fallback에 도달 못 함** → scope=app 항목의
  Alt+Tab 매칭은 aliases 역매핑이 유일한 경로.

메타 조회는 생성자에 주입된 `meta_provider(entry) -> dict` 콜백에 위임한다.
반환 dict는 최소 `scope`, `aliases` 키를 포함해야 한다(부재 시 기본값 적용).
GlobalPlugin의 `_meta_for`가 주입되며 내부에서 store.get_meta를 호출.
"""

from __future__ import annotations

from logHandler import log

from .appIdentity import splitKey
from .constants import SCOPE_APP, SCOPE_WINDOW


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
            meta = self._meta_provider(entry) or {}
            scope = meta.get("scope", SCOPE_WINDOW)
            aliases = meta.get("aliases") or []
            if scope == SCOPE_APP:
                app.setdefault(entry, idx)
                # scope=app에도 alias 전개 — Alt+Tab 오버레이는 match_appId=""
                # 경유라 appLookup fallback에 못 닿는다. title-only 역매핑 경유가
                # 유일한 매칭 경로이므로 alias가 있으면 windowLookup에도 주입.
                for alias in aliases:
                    if alias:
                        window.setdefault(alias, idx)
                continue
            # SCOPE_WINDOW
            window[entry] = idx
            _, title = splitKey(entry)
            if title and title != entry:
                window.setdefault(title, idx)
            # aliases 역매핑. primary title과 중복이면 setdefault가 자동 무시.
            for alias in aliases:
                if alias:
                    window.setdefault(alias, idx)
        # 원자적 교체: 중간 상태를 외부에 노출하지 않음.
        self.windowLookup = window
        self.appLookup = app
        log.debug(
            f"mtwn: LookupIndex.rebuild entries={len(app_list)} "
            f"window_keys={len(window)} app_keys={len(app)}"
        )
