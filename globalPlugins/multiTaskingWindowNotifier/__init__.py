# -*- coding: utf-8 -*-
# multiTasking window notifier
# GNU General Public License v2.0-or-later
#
# 📝 보류/고려 아이디어 메모(기억용)
# - 프로필 전환(업무/개인 등): 프로필별 app.list 분리 후 단축키로 전환
# - 포커스 전환 로깅/간단 통계: 오늘 가장 많이 쓴 앱 등 요약 안내
#   ※ 위 두 항목은 아직 미구현. 구조 영향 적음. 추후 필요 시 추가.

import os
import time
import ui
import gui
import globalPluginHandler
from logHandler import log

from . import store
from . import settings
from .constants import FLUSH_EVERY_N_DEFAULT, FLUSH_INTERVAL_SEC_DEFAULT
from .windowInfo import config_addon_dir
from .settingsPanel import MultiTaskingSettingsPanel
from .matcher import LookupIndex, Matcher
from .scripts import ScriptsMixin
from . import eventRouter

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
    이벤트 훅 본문은 eventRouter에 위임 (handle_foreground / handle_name_change /
    dispatch_focus 3-way).
    """

    def __init__(self):
        super().__init__()
        # 설정 스키마 등록 + 설정 대화상자 패널 등록은 하나의 원자적 묶음으로 처리.
        # 한쪽만 성공하면 다른 쪽이 KeyError를 유발(패널이 등록됐는데 스키마 없음 등).
        # in 체크로 재로드 시 고아 엔트리로 인한 중복 등록도 방어.
        try:
            settings.register()
            # 폐기 프리셋 id가 nvda.ini에 남아있어도 get_preset_or_classic 폴백이
            # 런타임에 classic으로 흡수하므로 별도 silent write 단계 불필요.
            category_classes = gui.settingsDialogs.NVDASettingsDialog.categoryClasses
            if MultiTaskingSettingsPanel not in category_classes:
                category_classes.append(MultiTaskingSettingsPanel)
        except Exception:
            log.exception("mtwn: settings init failed")

        self.appDir = config_addon_dir()
        # 첫 부팅 시점에 데이터 디렉토리를 선생성해 둔다. store가 자체 makedirs를
        # 수행하긴 하지만, 사용자가 수동으로 경로를 열어보거나 로그에서 참조할 때
        # 폴더가 즉시 보이도록.
        try:
            os.makedirs(self.appDir, exist_ok=True)
        except Exception:
            log.exception("mtwn: user data dir ensure failed: %s", self.appDir)
        self.appListFile = os.path.join(self.appDir, "app.list")
        # 초기 1회만 로드
        self.appList = store.load(self.appListFile)

        # 매칭용 룩업 인덱스. windowLookup/appLookup 두 dict는 LookupIndex가 소유하고,
        # GlobalPlugin은 property로 read-only 노출(기존 테스트 호환).
        self._lookup = LookupIndex(meta_provider=self._meta_for)
        self._rebuild_lookup()
        # 전환 카운트 디바운스 상태: 매칭 성공마다 _pending++, 임계치 넘으면 flush.
        # Matcher가 flush를 몰라도 되도록 레이어 분리 유지(매칭 후 기록은 플러그인 책임).
        self._pending_switches = 0
        self._last_flush_at = time.monotonic()
        # 매칭 + 비프 재생 + 시그니처 dedup 캡슐화. dedup 상태는
        # Matcher.last_event_signature가 직접 소유(외부에서는 plugin._matcher로 접근).
        self._matcher = Matcher(self)

        # 손상된 app.json을 만났을 때 한 번만 사용자에게 안내.
        # ui.delayedMessage는 부팅 시 UI 변화에 묻히지 않도록 NVDA가 제공하는
        # 전용 헬퍼로, 기본 speechPriority가 Spri.NOW라 다른 음성 뒤에도 인터럽트
        # 로 반드시 전달된다.
        if store.is_corrupted(self.appListFile):
            log.info(f"mtwn: corruption alert queued path={self.appListFile!r}")
            ui.delayedMessage(
                _("앱 목록 파일이 손상되어 빈 상태로 시작했어요. "
                  "이전 목록은 자동 복구되지 않으니 필요하면 백업을 확인해 주세요."),
            )

        # 첫 실행 튜토리얼 안내 — tutorialShown=False인 신규 사용자에게 NVDA
        # welcome 종료 후 확인 다이얼로그 1회 노출. 이미 본 사용자는 즉시 no-op.
        # 예외는 흡수 — 튜토리얼 안내 실패가 비프 기능 본체를 막으면 더 큰 손해.
        try:
            from .tutorial.prompt import maybe_show_first_run_prompt
            maybe_show_first_run_prompt(self)
        except Exception:
            log.exception("mtwn: tutorial first-run prompt failed")

    def terminate(self):
        """애드온 재로드/NVDA 종료 시 미저장 변경분 저장 + 설정 패널 해제.

        튜토리얼 첫 실행 프롬프트가 `core.postNvdaStartup`에 등록해둔 핸들러도
        여기서 해제한다. 해제하지 않으면 재로드 시 구 인스턴스 참조가
        `postNvdaStartup`에 남아 누수.
        """
        try:
            store.flush(self.appListFile)
        except Exception:
            log.exception("mtwn: terminate flush")
        try:
            from .tutorial.prompt import unregister_first_run_prompt
            unregister_first_run_prompt()
        except Exception:
            log.exception("mtwn: tutorial prompt unregister failed")
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
        """디스크 메타를 얕은 dict로 반환. 미존재 시 빈 dict.

        반환 dict는 최소 `scope`와 `aliases` 키가 있어야 호출부가 안전하게
        동작한다. `store.get_meta`는 이미 두 필드를 포함하거나 None을
        반환하므로 여기서는 None 방어만 한다.

        호출부 (dict.get 기반 안전 접근):
            - LookupIndex.rebuild: scope + aliases 둘 다 필요
            - Matcher.match_and_beep: scope만 필요 (title-only 역매핑 분기)
        """
        return store.get_meta(self.appListFile, entry) or {}

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

    # ---- 디바운스 flush ----

    def _notify_switch(self):
        """매칭 성공 1회 = 미저장 전환 카운트 +1."""
        self._pending_switches += 1

    def _maybe_flush(self):
        """임계치(FLUSH_EVERY_N_DEFAULT/FLUSH_INTERVAL_SEC_DEFAULT) 충족 시 디스크 반영.

        실패해도 이벤트 체인을 막지 않도록 예외 흡수. 시간 기준/횟수 기준 중
        하나만 충족해도 flush가 수행된다.
        """
        now = time.monotonic()
        if (
            self._pending_switches >= FLUSH_EVERY_N_DEFAULT
            or (now - self._last_flush_at) >= FLUSH_INTERVAL_SEC_DEFAULT
        ):
            try:
                store.flush(self.appListFile)
            except Exception:
                log.exception("mtwn: switch flush failed")
            self._last_flush_at = now
            self._pending_switches = 0

    def _reset_flush_schedule(self):
        """reload 후 카운터/타이머 초기화."""
        self._last_flush_at = time.monotonic()
        self._pending_switches = 0

    # ---- matcher 위임 ----

    def _match_and_beep(self, appId, title, tab_signature=0):
        """공통 매칭 루틴. 실제 로직은 Matcher.match_and_beep."""
        self._matcher.match_and_beep(appId, title, tab_signature=tab_signature)

    # -------- 이벤트 훅 --------

    def event_gainFocus(self, obj, nextHandler):
        """모든 포커스 전환에서 호출. 3분기 매칭은 eventRouter.dispatch_focus에 위임.

        try/except + finally로 nextHandler() 보장은 여기 유지 — 애드온 예외가
        NVDA 이벤트 체인을 끊지 않도록 진입점 레이어에서 흡수.
        """
        try:
            eventRouter.dispatch_focus(self, obj)
        except Exception:
            log.exception("mtwn: event_gainFocus failed")
        finally:
            nextHandler()

    def event_nameChange(self, obj, nextHandler):
        """탭 확정 전환 감지. 로직은 eventRouter.handle_name_change에 위임.

        try/except + finally로 nextHandler() 보장은 진입점 레이어에서 유지 —
        애드온 예외가 NVDA 이벤트 체인을 끊지 않도록.
        """
        try:
            eventRouter.handle_name_change(self, obj)
        except Exception:
            log.exception("mtwn: event_nameChange failed")
        finally:
            nextHandler()

    def event_foreground(self, obj, nextHandler):
        """foreground 윈도우 전환 시 1회 발화. NVDA가 hwnd dedup 보장.

        SCOPE_APP 매칭의 표준 진입로. obj는 새 foreground 본체로 appId 신뢰 가능.
        같은 앱 내 포커스 이동에는 발화하지 않음 → 내부 메뉴/버튼 클릭 폭주 자동 차단.

        try/except + finally로 nextHandler() 보장은 다른 훅과 동일 패턴.
        """
        try:
            eventRouter.handle_foreground(self, obj)
        except Exception:
            log.exception("mtwn: event_foreground failed")
        finally:
            nextHandler()
