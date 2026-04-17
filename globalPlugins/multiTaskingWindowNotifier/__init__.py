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
import tones
import globalVars
import globalPluginHandler
from scriptHandler import script
from logHandler import log

# 번역 초기화(선택)
try:
    import addonHandler
    addonHandler.initTranslation()
    _  # noqa: F401
except Exception:
    def _(s):
        return s

ADDON_NAME = "multiTaskingWindowNotifier"
MAX_ITEMS = 64
# 비프 테이블 반음 기반
BEEP_TABLE = [
    130, 138, 146, 155, 164, 174, 185, 196, 207, 220, 233, 246,  # C3–B3
    261, 277, 293, 311, 329, 349, 370, 392, 415, 440, 466, 493,  # C4–B4
    523, 554, 587, 622, 659, 698, 740, 784, 831, 880, 932, 987,  # C5–B5
    1047, 1109, 1175, 1245, 1319, 1397, 1480, 1568, 1661, 1760, 1865, 1976,  # C6–B6
    2093, 2217, 2349, 2489, 2637, 2794, 2960, 3136, 3322, 3520, 3729, 3951,  # C7–B7
    4186, 4435, 4699, 4978  # C8–B8
]

def _config_addon_dir() -> str:
    """사용자 설정 경로 하위의 애드온 디렉터리 경로 계산."""
    base = globalVars.appArgs.configPath
    return os.path.join(base, "addons", ADDON_NAME, "globalPlugins", ADDON_NAME)


class AppListStore:
    """app.list 파일 I/O 전담 유틸"""

    @staticmethod
    def load(path: str) -> list:
        try:
            with open(path, "r", encoding="utf-8") as f:
                items = [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            items = []
        except Exception as e:
            log.error(f"app.list 로드 실패: {path}", exc_info=True)
            ui.message(f"앱 목록을 여는 중 문제가 생겼어요: {e}")
            items = []
        return items[:MAX_ITEMS]

    @staticmethod
    def save(path: str, items: list) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, "w", encoding="utf-8") as f:
                for t in items[:MAX_ITEMS]:
                    f.write(f"{t}\n")
        except Exception as e:
            log.error(f"app.list 저장 실패: {path}", exc_info=True)
            ui.message(f"앱 목록을 저장하는 중 문제가 생겼어요: {e}")


def _getAppId(obj) -> str:
    """
    앱 식별자 결정: 기본은 appModule.appName.
    비어 있으면 windowClassName을 대체값으로 사용.
    """
    appId = ""
    try:
        appId = getattr(getattr(obj, "appModule", None), "appName", "") or ""
    except Exception:
        log.debug("appModule.appName 접근 실패", exc_info=True)
        appId = ""
    if not appId:
        appId = getattr(obj, "windowClassName", "") or "unknown"
    return appId


def _makeKey(appId: str, title: str) -> str:
    """저장·매칭용 복합키 생성."""
    return f"{appId}|{title}"


def _splitKey(entry: str):
    """복합키 파싱. 구(제목만) 형식도 처리."""
    if "|" in entry:
        appId, title = entry.split("|", 1)
        return appId, title
    return "", entry  # 구형: 제목만


class AppListDialog(wx.Dialog):
    """앱 목록 표시 다이얼로그"""

    def __init__(self, parent, appList):
        super().__init__(parent, title=_("등록된 창 목록"))
        self.appList = appList
        self._create_ui()
        self.CenterOnScreen()

    def _create_ui(self):
        """UI 구성"""
        panel = wx.Panel(self)
        mainSizer = wx.BoxSizer(wx.VERTICAL)

        # 목록 개수 레이블
        total = len(self.appList)
        countLabel = wx.StaticText(panel, label=f"총 {total}개")
        mainSizer.Add(countLabel, flag=wx.ALL, border=10)

        # 리스트박스
        entries_sorted = sorted(self.appList, key=lambda s: self._display_text(s).lower())
        display_items = [self._display_text(e) for e in entries_sorted]

        self.listBox = wx.ListBox(
            panel,
            choices=display_items,
            style=wx.LB_SINGLE | wx.LB_HSCROLL,
            size=(500, 300)
        )
        mainSizer.Add(self.listBox, proportion=1, flag=wx.ALL | wx.EXPAND, border=10)

        # 확인 버튼
        btnOk = wx.Button(panel, wx.ID_OK, _("확인"))
        btnOk.SetDefault()
        btnOk.Bind(wx.EVT_BUTTON, self.on_ok)
        mainSizer.Add(btnOk, flag=wx.ALL | wx.ALIGN_CENTER, border=10)

        panel.SetSizer(mainSizer)
        mainSizer.Fit(self)

    def _display_text(self, entry: str) -> str:
        """표시용 텍스트 생성"""
        appId, title = _splitKey(entry)
        appLabel = appId if appId else "앱 미지정"
        return f"{appLabel} | {title}"

    def on_ok(self, event):
        """확인 버튼 클릭"""
        self.EndModal(wx.ID_OK)


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    """전역 플러그인: 지정한 창(appName|제목)에 포커스가 오면 비프음 알림"""

    def __init__(self):
        super().__init__()
        self.appDir = _config_addon_dir()
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
            entry_appId, _ = _splitKey(entry)
            if entry_appId == appId:
                order += 1
                if entry == key:
                    return order
        return 1  # 기본값

    def _get_current_window_info(self):
        """현재 창 정보 추출 (공통 메서드)

        Returns:
            tuple: (fg, appId, title, key) 또는 title이 없으면 (None, None, None, None)
        """
        fg = api.getForegroundObject()
        title = (getattr(fg, "name", "") or "").strip()
        if not title:
            return None, None, None, None
        appId = _getAppId(fg)
        key = _makeKey(appId, title)
        return fg, appId, title, key

    # -------- 스크립트 --------
    # 기본 제스처는 데코레이터 gesture 파라미터로 선언

    @script(
        description=_("Add current window title to notifier list"),
        category=_("Multi-tasking notifier"),
        gesture="kb:NVDA+shift+t",
    )
    def script_addCurrentWindowTitle(self, gesture=None):
        fg, appId, title, key = self._get_current_window_info()
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
        fg, appId, title, key = self._get_current_window_info()
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
                appId = _getAppId(o)
                key = _makeKey(appId, title)

                # O(1) 딕셔너리 검색: 신형 키 우선, 없으면 구형(제목만) 시도
                idx = self.appLookup.get(key)
                if idx is None:
                    idx = self.appLookup.get(title)  # 하위호환

                if idx is not None and 0 <= idx < len(BEEP_TABLE):
                    base_freq = BEEP_TABLE[idx]

                    # 등록 순서 계산 (같은 appId 중 몇 번째?)
                    order = self._get_registration_order(key, appId)

                    # 기본음 재생 (짧게 50ms)
                    tones.beep(base_freq, 50, 30, 30)

                    # 2번째 이상이면 순서에 해당하는 높은 음을 wx.CallLater로 지연 재생
                    # (메인 스레드 블로킹 방지)
                    if order > 1:
                        # 반음 = 2^(1/12) ≈ 1.059463
                        # order번째 = (order-1)반음 높게
                        higher_freq = int(base_freq * (1.059463 ** (order - 1)))
                        wx.CallLater(10, tones.beep, higher_freq, 50, 30, 30)

        nextHandler()
