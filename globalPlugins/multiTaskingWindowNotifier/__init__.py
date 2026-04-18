# -*- coding: utf-8 -*-
# multiTasking window notifier
# GNU General Public License v2.0-or-later
#
# 📝 보류/고려 아이디어 메모(기억용)
# - 프로필 전환(업무/개인 등): 프로필별 app.list 분리 후 단축키로 전환
# - 포커스 전환 로깅/간단 통계: 오늘 가장 많이 쓴 앱 등 요약 안내
#   ※ 위 두 항목은 아직 미구현. 구조 영향 적음. 추후 필요 시 추가.

import os
import ui
import gui
import globalPluginHandler
from logHandler import log

from .constants import SCOPE_WINDOW
from . import store
from . import settings
from . import tabClasses
from .windowInfo import config_addon_dir
from .settingsPanel import MultiTaskingSettingsPanel
from .switchFlusher import FlushScheduler
from .lookupIndex import LookupIndex
from .matcher import Matcher
from .scripts import ScriptsMixin
from . import focusDispatcher
from . import nameChangeWatcher

# 번역 초기화(선택)
try:
    import addonHandler
    addonHandler.initTranslation()
    _  # noqa: F401
except Exception:
    def _(s):
        return s


class GlobalPlugin(ScriptsMixin, globalPluginHandler.GlobalPlugin):
    """전역 플러그인: 지정한 창(appName|제목)에 포커스가 오면 비프음 알림.

    책임: 설정 스키마 등록 / 저장소 로드 / 이벤트 훅 진입점 / 모듈 결합.
    단축키 4종과 보조 헬퍼는 ScriptsMixin이 담당 (scripts.py).
    이벤트 훅 본문은 focusDispatcher / nameChangeWatcher에 위임.
    """

    def __init__(self):
        super().__init__()
        # 설정 스키마 등록 + 설정 대화상자 패널 등록은 하나의 원자적 묶음으로 처리.
        # 한쪽만 성공하면 다른 쪽이 KeyError를 유발(패널이 등록됐는데 스키마 없음 등).
        # in 체크로 재로드 시 고아 엔트리로 인한 중복 등록도 방어.
        try:
            settings.register()
            category_classes = gui.settingsDialogs.NVDASettingsDialog.categoryClasses
            if MultiTaskingSettingsPanel not in category_classes:
                category_classes.append(MultiTaskingSettingsPanel)
        except Exception:
            log.exception("mtwn: settings init failed")

        self.appDir = config_addon_dir()
        self.appListFile = os.path.join(self.appDir, "app.list")
        # 초기 1회만 로드
        self.appList = store.load(self.appListFile)

        # 앱별 탭 컨트롤 wcn 매핑 로드. 파일이 없으면 DEFAULT_TAB_CLASSES로 자동 생성된다.
        # 로드 실패해도 애드온 기본 동작(Alt+Tab 매칭)은 유지되어야 하므로 예외는 삼킴.
        self.tabClassesFile = os.path.join(self.appDir, "tabClasses.json")
        try:
            tabClasses.load(self.tabClassesFile)
        except Exception:
            log.exception("mtwn: tabClasses load failed — overlay branch disabled")
        # 매칭용 룩업 인덱스. windowLookup/appLookup 두 dict는 LookupIndex가 소유하고,
        # GlobalPlugin은 property로 read-only 노출(기존 테스트 호환).
        self._lookup = LookupIndex(meta_provider=self._meta_for)
        self._rebuild_lookup()
        # 전환 카운트 디바운스 저장: switchFlusher가 카운터/타이머 상태 캡슐화.
        self._flush_scheduler = FlushScheduler(store.flush, self.appListFile)
        # 매칭 + 비프 재생 + 시그니처 dedup 캡슐화. dedup 상태(_last_event_sig)는
        # Matcher.last_event_sig에 있으며 아래 property로 테스트 호환 유지.
        self._matcher = Matcher(self)

        # 손상된 app.json을 만났을 때 한 번만 사용자에게 안내.
        # ui.delayedMessage는 부팅 시 UI 변화에 묻히지 않도록 NVDA가 제공하는
        # 전용 헬퍼로, 기본 speechPriority가 Spri.NOW라 다른 음성 뒤에도 인터럽트
        # 로 반드시 전달된다.
        if store.is_corrupted(self.appListFile):
            log.info(f"mtwn: corruption alert queued path={self.appListFile!r}")
            ui.delayedMessage(
                "앱 목록 파일이 손상되어 빈 상태로 시작했어요. "
                "이전 목록은 자동 복구되지 않으니 필요하면 백업을 확인해 주세요.",
            )

    def terminate(self):
        """애드온 재로드/NVDA 종료 시 미저장 변경분 저장 + 설정 패널 해제."""
        try:
            store.flush(self.appListFile)
        except Exception:
            log.exception("mtwn: terminate flush")
        try:
            gui.settingsDialogs.NVDASettingsDialog.categoryClasses.remove(
                MultiTaskingSettingsPanel
            )
        except ValueError:
            # 이미 제거됐거나 등록 실패 상태 — 조용히 무시
            pass
        except Exception:
            log.exception("mtwn: settings panel unregister failed")
        super().terminate()

    def _meta_for(self, entry):
        """디스크 메타에서 scope를 조회. 메타 없으면 기본 SCOPE_WINDOW로 간주.

        store가 아직 로드 안 됐거나(부팅 직후) entry가 막 추가되어 메타가
        없을 수 있다. 그런 케이스에서도 안전하게 동작하도록 fallback.
        """
        meta = store.get_meta(self.appListFile, entry) or {}
        return meta.get("scope", SCOPE_WINDOW)

    @property
    def windowLookup(self):
        """호환용 read-only 노출. 실제 소유자는 self._lookup."""
        return self._lookup.windowLookup

    @property
    def appLookup(self):
        """호환용 read-only 노출. 실제 소유자는 self._lookup."""
        return self._lookup.appLookup

    def _rebuild_lookup(self):
        """appList 변경 시 lookup 재구성. 실제 로직은 LookupIndex.rebuild."""
        self._lookup.rebuild(self.appList)

    # ---- matcher 위임 (테스트 호환 + 기존 호출부 유지) ----

    @property
    def _last_event_sig(self):
        """호환용 pass-through. 실제 소유자는 Matcher."""
        return self._matcher.last_event_sig

    @_last_event_sig.setter
    def _last_event_sig(self, value):
        self._matcher.last_event_sig = value

    def _match_and_beep(self, appId, title, tab_sig=0):
        """공통 매칭 루틴. 실제 로직은 Matcher.match_and_beep."""
        self._matcher.match_and_beep(appId, title, tab_sig=tab_sig)

    # -------- 이벤트 훅 --------

    def event_gainFocus(self, obj, nextHandler):
        """모든 포커스 전환에서 호출. 3분기 매칭은 focusDispatcher에 위임.

        try/except + finally로 nextHandler() 보장은 여기 유지 — 애드온 예외가
        NVDA 이벤트 체인을 끊지 않도록 진입점 레이어에서 흡수.
        """
        try:
            focusDispatcher.dispatch(self, obj)
        except Exception:
            log.exception("mtwn: event_gainFocus failed")
        finally:
            nextHandler()

    def event_nameChange(self, obj, nextHandler):
        """탭 확정 전환 감지. 로직은 nameChangeWatcher.handle에 위임.

        try/except + finally로 nextHandler() 보장은 진입점 레이어에서 유지 —
        애드온 예외가 NVDA 이벤트 체인을 끊지 않도록.
        """
        try:
            nameChangeWatcher.handle(self, obj)
        except Exception:
            log.exception("mtwn: event_nameChange failed")
        finally:
            nextHandler()
