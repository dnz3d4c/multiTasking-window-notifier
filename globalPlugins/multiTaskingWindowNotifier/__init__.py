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
import wx
import api
import ui
import gui
import speech
import globalPluginHandler
from logHandler import log
from scriptHandler import script

from .constants import ADDON_NAME, MAX_ITEMS
from .appIdentity import getAppId, makeKey, splitKey
from . import appListStore
from . import settings
from .windowInfo import config_addon_dir, get_current_window_info
from .beepPlayer import play_window_beep
from .listDialog import AppListDialog
from .settingsPanel import MultiTaskingSettingsPanel

# 번역 초기화(선택)
try:
    import addonHandler
    addonHandler.initTranslation()
    _  # noqa: F401
except Exception:
    def _(s):
        return s


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    """전역 플러그인: 지정한 창(appName|제목)에 포커스가 오면 비프음 알림"""

    # 전환 카운트 디바운스 저장 임계치
    _FLUSH_INTERVAL_SEC = 30
    _FLUSH_EVERY_N = 10

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
        self.appList = appListStore.load(self.appListFile)
        self.appLookup = {}  # {key: index} 빠른 검색용
        self._rebuild_lookup()
        # 전환 카운트 디바운스 저장 상태
        self._lastFlushAt = time.monotonic()
        self._switchesSinceFlush = 0

        # 손상된 app.json을 만났을 때 한 번만 사용자에게 안내.
        # ui.delayedMessage는 부팅 시 UI 변화에 묻히지 않도록 NVDA가 제공하는
        # 전용 헬퍼로, 기본 speechPriority가 Spri.NOW라 다른 음성 뒤에도 인터럽트
        # 로 반드시 전달된다.
        if appListStore.is_corrupted(self.appListFile):
            log.info(f"mtwn: corruption alert queued path={self.appListFile!r}")
            ui.delayedMessage(
                "앱 목록 파일이 손상되어 빈 상태로 시작했어요. "
                "이전 목록은 자동 복구되지 않으니 필요하면 백업을 확인해 주세요.",
            )

    def terminate(self):
        """애드온 재로드/NVDA 종료 시 미저장 변경분 저장 + 설정 패널 해제."""
        try:
            appListStore.flush(self.appListFile)
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

    def _maybe_flush_switches(self):
        """디바운스: N회 전환 또는 일정 시간 경과 시 디스크 반영."""
        now = time.monotonic()
        if (self._switchesSinceFlush >= self._FLUSH_EVERY_N
                or (now - self._lastFlushAt) >= self._FLUSH_INTERVAL_SEC):
            try:
                appListStore.flush(self.appListFile)
            except Exception:
                log.exception("mtwn: switch flush failed")
            self._lastFlushAt = now
            self._switchesSinceFlush = 0

    def _rebuild_lookup(self):
        """appList 변경 시 검색용 딕셔너리 재구성.

        Alt+Tab 오버레이에서 오는 포커스 객체의 appId는 실제 대상 앱이 아니라
        Alt+Tab UI 호스트(예: `explorer`, `windowsterminal`)로 찍힌다. 따라서
        신형 복합키(`notepad|제목 없음 - 메모장`)는 event_gainFocus 경로에서
        정확 매치가 사실상 불가능하다 — appId 컴포넌트가 무조건 달라진다.

        해결: 복합키 entry를 title 컴포넌트로도 역매핑해 두면 기존 title-only
        fallback이 그대로 먹는다. title이 충돌하면 먼저 등록된 idx가 우선
        (`setdefault`). 구형 entry(title == entry)는 이미 원본으로 등록됐으니
        별도 역매핑은 skip.
        """
        self.appLookup = {}
        for idx, entry in enumerate(self.appList):
            self.appLookup[entry] = idx
            _, title = splitKey(entry)
            if title and title != entry:
                self.appLookup.setdefault(title, idx)
        log.debug(
            f"mtwn: _rebuild_lookup entries={len(self.appList)} "
            f"lookup_keys={len(self.appLookup)}"
        )

    def _get_registration_order(self, key, appId):
        """
        같은 appId를 가진 항목들 중에서 현재 키가 몇 번째로 등록되었는지 반환

        @param key: 현재 창의 복합키 (appId|title)
        @param appId: 앱 식별자
        @return: 등록 순서 (1부터 시작)
        """
        order = 0
        for entry in self.appList:
            entry_appId, _entry_title = splitKey(entry)
            if entry_appId == appId:
                order += 1
                if entry == key:
                    return order
        return 1  # 기본값

    # -------- 스크립트 --------
    # 기본 제스처는 데코레이터 gesture 파라미터로 선언

    @script(
        description=_("Add current window title to notifier list"),
        category=_("Multi-tasking notifier"),
        gesture="kb:NVDA+shift+t",
    )
    def script_addCurrentWindowTitle(self, gesture=None):
        fg, appId, title, key = get_current_window_info()
        if not title:
            ui.message("창 제목을 확인할 수 없어요.", speechPriority=speech.Spri.NEXT)
            return

        # 중복 체크: 신형 키 또는 구형 제목만 항목 모두 고려 (O(1) 딕셔너리 조회)
        if key in self.appLookup or title in self.appLookup:
            ui.message("이미 목록에 있어요.", speechPriority=speech.Spri.NEXT)
            return
        # 사용자 설정 상한과 하드 상한(BEEP_TABLE 길이) 중 작은 값을 적용
        effective_max = min(settings.get("maxItems"), MAX_ITEMS)
        if len(self.appList) >= effective_max:
            ui.message(
                "목록이 가득 찼어요. 몇 개 지우고 다시 시도해 주세요.",
                speechPriority=speech.Spri.NEXT,
            )
            return

        self.appList.append(key)
        if not appListStore.save(self.appListFile, self.appList):
            # 저장 실패 → 메모리 롤백 후 사용자 안내
            self.appList.pop()
            ui.message(
                "앱 목록을 저장하는 중 문제가 생겼어요. 다시 시도해 주세요.",
                speechPriority=speech.Spri.NOW,
            )
            return
        self._rebuild_lookup()
        ui.message(f"추가했어요: {appId} | {title}", speechPriority=speech.Spri.NEXT)
        log.info(f"mtwn: add succeeded key={key!r} total={len(self.appList)}")

    @script(
        description=_("Remove current window title from notifier list"),
        category=_("Multi-tasking notifier"),
        gesture="kb:NVDA+shift+d",
    )
    def script_removeCurrentWindowTitle(self, gesture=None):
        fg, appId, title, key = get_current_window_info()
        if not title:
            ui.message("창 제목을 확인할 수 없어요.", speechPriority=speech.Spri.NEXT)
            return

        # 신형 키 우선 제거. 없으면 title 역매핑으로 해당 entry 인덱스를 찾아 pop.
        # appLookup에 title이 신형 entry의 역매핑으로 등록돼 있을 수 있어서,
        # list.remove(title)은 entry 문자열과 일치하지 않으면 ValueError. 대신
        # 역매핑이 가리키는 idx로 pop해 안전 처리.
        original = list(self.appList)
        if key in self.appLookup:
            self.appList.remove(key)
        elif title in self.appLookup:
            idx = self.appLookup[title]
            self.appList.pop(idx)
        else:
            ui.message("목록에 없는 항목이에요.", speechPriority=speech.Spri.NEXT)
            return

        if not appListStore.save(self.appListFile, self.appList):
            # 저장 실패 → 메모리 롤백 후 사용자 안내
            self.appList = original
            ui.message(
                "앱 목록을 저장하는 중 문제가 생겼어요. 다시 시도해 주세요.",
                speechPriority=speech.Spri.NOW,
            )
            return
        self._rebuild_lookup()
        ui.message("목록에서 삭제했어요.", speechPriority=speech.Spri.NEXT)
        log.info(f"mtwn: remove succeeded total={len(self.appList)}")

    @script(
        description=_("Reload app list from disk"),
        category=_("Multi-tasking notifier"),
        gesture="kb:NVDA+shift+r",
    )
    def script_reloadAppList(self, gesture=None):
        # reload는 미저장 변경분을 먼저 flush한 뒤 캐시 무효화 후 재로드한다.
        items = appListStore.reload(self.appListFile)
        self.appList = items
        self._rebuild_lookup()
        self._lastFlushAt = time.monotonic()
        self._switchesSinceFlush = 0
        ui.message(
            f"목록을 다시 불러왔어요. 지금 {len(items)}개예요.",
            speechPriority=speech.Spri.NEXT,
        )
        log.info(f"mtwn: reload loaded={len(items)}")

    @script(
        description=_("Show all registered entries"),
        category=_("Multi-tasking notifier"),
        gesture="kb:NVDA+shift+i",
    )
    def script_showAllEntries(self, gesture=None):
        # 파일 I/O 없이 메모리 목록 사용
        if not self.appList:
            ui.message("등록된 창이 없어요.", speechPriority=speech.Spri.NEXT)
            return

        # wxPython 다이얼로그 표시 (GUI 스레드에서 실행)
        def show_dialog():
            gui.mainFrame.prePopup()
            dlg = AppListDialog(gui.mainFrame, self.appList)
            dlg.ShowModal()
            dlg.Destroy()
            gui.mainFrame.postPopup()

        wx.CallAfter(show_dialog)
        # 간단 음성 요약
        ui.message(
            f"총 {len(self.appList)}개를 표시했어요.",
            speechPriority=speech.Spri.NEXT,
        )

    # -------- 이벤트 훅 --------

    def event_gainFocus(self, obj, nextHandler):
        # 창 전환 시 파일 I/O 없음. 메모리 목록만 참조.
        # event_gainFocus는 모든 포커스 전환마다 호출되므로, 본 애드온 예외가
        # NVDA 이벤트 체인을 끊지 않도록 try/except + finally로 nextHandler() 보장.
        try:
            o = api.getFocusObject()
            if not o:
                return

            # 기본값: Alt+Tab 오버레이(Windows.UI.Input.InputSite.WindowClass)에서만 동작.
            # enableAllWindows=True면 윈도우 클래스 제한 없이 모든 포커스 전환에서 비프.
            enable_all = settings.get("enableAllWindows")
            in_alt_tab = getattr(o, "windowClassName", "") == "Windows.UI.Input.InputSite.WindowClass"
            if not (enable_all or in_alt_tab):
                return

            title = (getattr(o, "name", "") or "").strip()
            if not title:
                return

            appId = getAppId(o)
            key = makeKey(appId, title)

            # O(1) 딕셔너리 검색: 신형 키 우선, 없으면 title 역매핑 시도
            # (_rebuild_lookup이 복합키 entry의 title 컴포넌트도 역매핑해둠).
            matched_key = key if key in self.appLookup else (
                title if title in self.appLookup else None
            )
            if matched_key is not None:
                idx = self.appLookup[matched_key]
                # 같은 appId 중 몇 번째 창인지 계산해 순서에 맞는 비프음 재생
                order = self._get_registration_order(matched_key, appId)
                play_window_beep(
                    idx,
                    order,
                    duration=settings.get("beepDuration"),
                    left=settings.get("beepVolumeLeft"),
                    right=settings.get("beepVolumeRight"),
                )
                # 전환 메타 기록 + 디바운스 저장
                appListStore.record_switch(self.appListFile, matched_key)
                self._switchesSinceFlush += 1
                self._maybe_flush_switches()
        except Exception:
            log.exception("mtwn: event_gainFocus failed")
        finally:
            nextHandler()
