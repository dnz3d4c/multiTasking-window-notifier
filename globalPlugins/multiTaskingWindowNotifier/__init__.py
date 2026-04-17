# -*- coding: utf-8 -*-
# multiTasking window notifier
# GNU General Public License v2.0-or-later
#
# 📝 보류/고려 아이디어 메모(기억용)
# - 프로필 전환(업무/개인 등): 프로필별 app.list 분리 후 단축키로 전환
# - 포커스 전환 로깅/간단 통계: 오늘 가장 많이 쓴 앱 등 요약 안내
#   ※ 위 두 항목은 아직 미구현. 구조 영향 적음. 추후 필요 시 추가.

import os
import wx
import api
import ui
import gui
import globalPluginHandler
from scriptHandler import script
from logHandler import log

from .constants import MAX_ITEMS
from .appIdentity import getAppId, makeKey, splitKey
from .appListStore import AppListStore
from .windowInfo import config_addon_dir, get_current_window_info
from .beepPlayer import play_window_beep
from .listDialog import AppListDialog

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

    def __init__(self):
        super().__init__()
        self.appDir = config_addon_dir()
        self.appListFile = os.path.join(self.appDir, "app.list")
        # 초기 1회만 로드
        self.appList = AppListStore.load(self.appListFile)
        self.appLookup = {}  # {key: index} 빠른 검색용
        self._rebuild_lookup()

    def _rebuild_lookup(self):
        """appList 변경 시 검색용 딕셔너리 재구성"""
        self.appLookup = {entry: idx for idx, entry in enumerate(self.appList)}

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
            ui.message("창 제목을 확인할 수 없어요.")
            return

        # 중복 체크: 신형 키 또는 구형 제목만 항목 모두 고려
        if key in self.appList or title in self.appList:
            ui.message("이미 목록에 있어요.")
            return
        if len(self.appList) >= MAX_ITEMS:
            ui.message("목록이 가득 찼어요. 몇 개 지우고 다시 시도해 주세요.")
            return

        self.appList.append(key)
        AppListStore.save(self.appListFile, self.appList)
        self._rebuild_lookup()
        ui.message(f"추가했어요: {appId} | {title}")

    @script(
        description=_("Remove current window title from notifier list"),
        category=_("Multi-tasking notifier"),
        gesture="kb:NVDA+shift+d",
    )
    def script_removeCurrentWindowTitle(self, gesture=None):
        fg, appId, title, key = get_current_window_info()
        if not title:
            ui.message("창 제목을 확인할 수 없어요.")
            return

        # 신형 키 우선 제거. 없으면 구형 제목만 항목 제거 시도.
        removed = False
        if key in self.appList:
            self.appList.remove(key)
            removed = True
        elif title in self.appList:
            self.appList.remove(title)
            removed = True

        if not removed:
            ui.message("목록에 없는 항목이에요.")
            return

        AppListStore.save(self.appListFile, self.appList)
        self._rebuild_lookup()
        ui.message("목록에서 삭제했어요.")

    @script(
        description=_("Reload app list from disk"),
        category=_("Multi-tasking notifier"),
        gesture="kb:NVDA+shift+r",
    )
    def script_reloadAppList(self, gesture=None):
        items = AppListStore.load(self.appListFile)
        self.appList = items
        self._rebuild_lookup()
        ui.message(f"목록을 다시 불러왔어요. 지금 {len(items)}개예요.")

    @script(
        description=_("Show all registered entries"),
        category=_("Multi-tasking notifier"),
        gesture="kb:NVDA+shift+i",
    )
    def script_showAllEntries(self, gesture=None):
        # 파일 I/O 없이 메모리 목록 사용
        if not self.appList:
            ui.message("등록된 창이 없어요.")
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
        ui.message(f"총 {len(self.appList)}개를 표시했어요.")

    # -------- 이벤트 훅 --------

    def event_gainFocus(self, obj, nextHandler):
        # 창 전환 시 파일 I/O 없음. 메모리 목록만 참조.
        o = api.getFocusObject()
        if not o:
            nextHandler()
            return

        # 원 설계 유지: 특정 윈도우 클래스에서만 동작
        if getattr(o, "windowClassName", "") == "Windows.UI.Input.InputSite.WindowClass":
            title = (getattr(o, "name", "") or "").strip()
            if title:
                appId = getAppId(o)
                key = makeKey(appId, title)

                # O(1) 딕셔너리 검색: 신형 키 우선, 없으면 구형(제목만) 시도
                idx = self.appLookup.get(key)
                if idx is None:
                    idx = self.appLookup.get(title)  # 하위호환

                if idx is not None:
                    # 같은 appId 중 몇 번째 창인지 계산해 순서에 맞는 비프음 재생
                    order = self._get_registration_order(key, appId)
                    play_window_beep(idx, order)

        nextHandler()
