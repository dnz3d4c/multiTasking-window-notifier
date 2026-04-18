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
import controlTypes
import globalPluginHandler
from logHandler import log
from scriptHandler import script

from .constants import ADDON_NAME, MAX_ITEMS, SCOPE_APP, SCOPE_WINDOW
from .appIdentity import getAppId, makeKey, makeAppKey, normalize_title, splitKey
from . import appListStore
from . import settings
from . import tabClasses
from .windowInfo import config_addon_dir, get_current_window_info
from .beepPlayer import play_beep
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

    # 매칭 중복 억제 윈도우(초). 같은 탭 안에서 자식 컨트롤(예: 메모장 RichEditD2DPT)
    # 로 gainFocus가 다중 발동해도 매칭 1회만. 너무 길면 의도적 빠른 재진입을 놓치고,
    # 너무 짧으면 중복 비프가 들리므로 0.3s로 시작.
    _MATCH_DEDUP_SEC = 0.3

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

        # 앱별 탭 컨트롤 wcn 매핑 로드. 파일이 없으면 DEFAULT_TAB_CLASSES로 자동 생성된다.
        # 로드 실패해도 애드온 기본 동작(Alt+Tab 매칭)은 유지되어야 하므로 예외는 삼킴.
        self.tabClassesFile = os.path.join(self.appDir, "tabClasses.json")
        try:
            tabClasses.load(self.tabClassesFile)
        except Exception:
            log.exception("mtwn: tabClasses load failed — editor/overlay branches disabled")
        # scope=window 매칭용 사전: 복합키(appId|title)와 title-only 역매핑 모두 보유.
        # title-only 역매핑은 Alt+Tab 오버레이 케이스에서 obj의 appId가 explorer 등으로
        # 찍혀 신형 키 매칭이 깨질 때 fallback으로 쓰인다.
        self.windowLookup = {}
        # scope=app 매칭용 사전: appId만 키로. windowLookup이 모두 미스일 때 fallback.
        self.appLookup = {}
        self._rebuild_lookup()
        # 전환 카운트 디바운스 저장 상태
        self._lastFlushAt = time.monotonic()
        self._switchesSinceFlush = 0
        # 매칭 중복 억제 상태
        self._last_matched_key = None
        self._last_matched_ts = 0.0

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

    def _meta_for(self, entry):
        """디스크 메타에서 scope를 조회. 메타 없으면 기본 SCOPE_WINDOW로 간주.

        appListStore가 아직 로드 안 됐거나(부팅 직후) entry가 막 추가되어 메타가
        없을 수 있다. 그런 케이스에서도 안전하게 동작하도록 fallback.
        """
        meta = appListStore.get_meta(self.appListFile, entry) or {}
        return meta.get("scope", SCOPE_WINDOW)

    def _rebuild_lookup(self):
        """appList 변경 시 검색용 딕셔너리 재구성.

        windowLookup:
            - 복합키(`appId|title`) → idx
            - title-only 역매핑 → idx (Alt+Tab 오버레이에서 obj.appId가 explorer로
              찍혀 정확 매치가 깨질 때 fallback)
            - 구형 entry(title == entry, '|' 없음)는 자기 자신이 그대로 등록되어
              자동 fallback 역할
            - title 충돌 시 먼저 등록된 idx 우선 (`setdefault`)
        appLookup:
            - appId → idx (scope=app entry만)
            - windowLookup이 모두 미스일 때 마지막 fallback. 매칭 우선순위 창 > 앱.
        """
        self.windowLookup = {}
        self.appLookup = {}
        for idx, entry in enumerate(self.appList):
            scope = self._meta_for(entry)
            if scope == SCOPE_APP:
                # appId 자체가 key
                self.appLookup.setdefault(entry, idx)
                continue
            # SCOPE_WINDOW
            self.windowLookup[entry] = idx
            _, title = splitKey(entry)
            if title and title != entry:
                self.windowLookup.setdefault(title, idx)
        log.debug(
            f"mtwn: _rebuild_lookup entries={len(self.appList)} "
            f"window_keys={len(self.windowLookup)} app_keys={len(self.appLookup)}"
        )

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
        if scope == SCOPE_APP:
            real_app_id = matched_key
        else:
            real_app_id, _ = splitKey(matched_key)
        app_idx = appListStore.get_app_beep_idx(self.appListFile, real_app_id)
        if app_idx is None:
            # _ensure_beep_assignments가 모든 등록 appId에 할당하므로 정상 흐름에선
            # miss가 뜨지 않는다. 뜬다면 캐시 정합성 버그 신호 → warning.
            log.warning(
                f"mtwn: appBeepMap miss appId={real_app_id!r} — falling back to 0"
            )
            app_idx = 0
        if scope == SCOPE_APP:
            return app_idx, None
        # SCOPE_WINDOW
        tab_idx = appListStore.get_tab_beep_idx(self.appListFile, matched_key)
        if tab_idx is None:
            log.warning(
                f"mtwn: tabBeepIdx miss key={matched_key!r} — falling back to 0"
            )
            tab_idx = 0
        return app_idx, tab_idx

    def _match_and_beep(self, appId, title):
        """공통 매칭 루틴. event_gainFocus가 매칭 소스를 결정한 뒤 호출.

        매칭 우선순위:
            1. windowLookup 정확 매치 (key=appId|title) → 창 비프
            2. windowLookup title-only 역매핑 → 창 비프 (Alt+Tab 오버레이 호환)
            3. appLookup (appId) → 앱 비프
            4. 미스 → no-op
        """
        key = makeKey(appId, title)

        # 중복 매칭 가드
        now = time.monotonic()
        if (key == self._last_matched_key
                and now - self._last_matched_ts < self._MATCH_DEDUP_SEC):
            return

        matched_key = None
        scope = None
        if key in self.windowLookup:
            matched_key, scope = key, SCOPE_WINDOW
        elif title in self.windowLookup:
            # title 역매핑 → 실제 entry 문자열로 변환 (record_switch는 entry 키가 필요)
            idx = self.windowLookup[title]
            matched_key, scope = self.appList[idx], SCOPE_WINDOW
        elif appId in self.appLookup:
            matched_key, scope = appId, SCOPE_APP

        if matched_key is None:
            return

        self._last_matched_key = key
        self._last_matched_ts = now

        app_idx, tab_idx = self._resolve_beep_pair(matched_key, scope, appId)
        play_beep(
            app_idx, tab_idx, scope,
            duration=settings.get("beepDuration"),
            gap_ms=settings.get("beepGapMs"),
            left=settings.get("beepVolumeLeft"),
            right=settings.get("beepVolumeRight"),
        )
        appListStore.record_switch(self.appListFile, matched_key)
        self._switchesSinceFlush += 1
        self._maybe_flush_switches()

    # -------- 스크립트 --------
    # 기본 제스처는 데코레이터 gesture 파라미터로 선언

    @script(
        description=_("Add current window title to notifier list"),
        category=_("Multi-tasking notifier"),
        gesture="kb:NVDA+shift+t",
    )
    def script_addCurrentWindowTitle(self, gesture=None):
        # 등록 소스는 foreground (메모장처럼 자식 컨트롤이 focus를 받아도 활성 탭 제목 취득).
        fg, appId, title, key = get_current_window_info()
        if not title:
            ui.message("창 제목을 확인할 수 없어요.", speechPriority=speech.Spri.NEXT)
            return

        # scope 선택 다이얼로그를 GUI 스레드에서 띄우고 결과를 콜백으로 처리.
        # wx.SingleChoiceDialog는 키보드/스크린리더 친화적이며 기본 포커스가
        # 첫 항목("이 창만")이라 Enter 한 번으로 기존 동작 재현 가능.
        choices = [
            _("이 창만 (%(app)s | %(title)s)") % {"app": appId, "title": title},
            _("이 앱 전체 (%s)") % appId,
        ]

        def show_choice():
            # 모달 종료 후 같은 GUI 스레드에서 즉시 _do_add 호출.
            # CallAfter 이중으로 큐에 쌓아 음성 순서가 큐 깊이에 따라 바뀌는 것을 방지.
            gui.mainFrame.prePopup()
            dlg = wx.SingleChoiceDialog(
                gui.mainFrame,
                _("등록 범위를 선택하세요."),
                _("창 전환 알림 — 항목 추가"),
                choices,
            )
            dlg.SetSelection(0)
            selected_scope = None
            try:
                if dlg.ShowModal() == wx.ID_OK:
                    selected_scope = SCOPE_WINDOW if dlg.GetSelection() == 0 else SCOPE_APP
            finally:
                dlg.Destroy()
                gui.mainFrame.postPopup()
            if selected_scope is not None:
                self._do_add(appId, title, key, selected_scope)

        wx.CallAfter(show_choice)

    def _do_add(self, appId, title, key, scope):
        """scope 선택 후 실제 등록. GUI 스레드에서 호출."""
        # 중복 체크: scope별로 나뉘므로 같은 appId여도 창 등록과 앱 등록은 공존 허용.
        if scope == SCOPE_WINDOW:
            if key in self.windowLookup:
                ui.message("이미 목록에 있어요.", speechPriority=speech.Spri.NEXT)
                return
            new_key = key
        else:  # SCOPE_APP
            if appId in self.appLookup:
                ui.message("이미 목록에 있어요.", speechPriority=speech.Spri.NEXT)
                return
            new_key = makeAppKey(appId)

        # 사용자 설정 상한과 하드 상한(BEEP_TABLE 길이) 중 작은 값을 적용
        effective_max = min(settings.get("maxItems"), MAX_ITEMS)
        if len(self.appList) >= effective_max:
            ui.message(
                "목록이 가득 찼어요. 몇 개 지우고 다시 시도해 주세요.",
                speechPriority=speech.Spri.NEXT,
            )
            return

        self.appList.append(new_key)
        if not appListStore.save(self.appListFile, self.appList, scopes={new_key: scope}):
            self.appList.pop()
            ui.message(
                "앱 목록을 저장하는 중 문제가 생겼어요. 다시 시도해 주세요.",
                speechPriority=speech.Spri.NOW,
            )
            return
        self._rebuild_lookup()

        # editor classname 자동 학습: scope=window 등록이 성공했고, 실제 focus가
        # foreground 최상위와 다른 자식 컨트롤(예: 메모장의 RichEditD2DPT)이라면
        # 그 wcn을 tabClasses에 추가. 이후 Ctrl+Tab 전환 시 event_gainFocus가
        # 바로 editor 분기를 탄다. scope=app은 탭 의미 없어 스킵.
        # 학습 실패는 등록 자체를 막지 않음 — best-effort, 예외는 로그만.
        #
        # wx.CallAfter로 한 틱 미뤄 실행하는 이유: _do_add 자체가 SingleChoiceDialog
        # 모달 종료 직후 동기 실행되어 focus가 아직 다이얼로그/mainFrame에 있을 수
        # 있다. NVDA focus 이벤트가 큐 흘러간 뒤(=다음 wx 이벤트 루프 틱) `api.
        # getFocusObject()`가 실제 대상 창의 자식 컨트롤을 가리킨다.
        #
        # 그래도 focus가 다이얼로그 내부에 남아 있는 경우가 있어(실측에서 wx
        # SingleChoiceDialog의 ListBox가 반복 학습되는 버그 확인) role 게이트를
        # 추가한다. 에디터 자식 컨트롤은 EDITABLETEXT(Scintilla) 또는
        # DOCUMENT(RichEditD2DPT) 역할을 가지며, ListBox/Pane 같은 다이얼로그
        # 위젯은 이 두 role에 속하지 않아 필터링된다.
        if scope == SCOPE_WINDOW:
            def _learn_editor_wcn():
                try:
                    focus = api.getFocusObject()
                    fg_obj = api.getForegroundObject()
                    if focus is None or fg_obj is None:
                        return
                    focus_wcn = getattr(focus, "windowClassName", "") or ""
                    fg_wcn = getattr(fg_obj, "windowClassName", "") or ""
                    focus_role = getattr(focus, "role", None)
                    editor_roles = (controlTypes.Role.EDITABLETEXT, controlTypes.Role.DOCUMENT)
                    if (focus_wcn and focus_wcn != fg_wcn
                            and focus_role in editor_roles):
                        tabClasses.learn_editor(appId, focus_wcn)
                except Exception:
                    log.exception("mtwn: tabClasses learn_editor hook failed")
            wx.CallAfter(_learn_editor_wcn)

        if scope == SCOPE_APP:
            ui.message(f"앱 전체로 추가했어요: {appId}", speechPriority=speech.Spri.NEXT)
        else:
            ui.message(f"창으로 추가했어요: {appId} | {title}", speechPriority=speech.Spri.NEXT)
        log.info(f"mtwn: add succeeded scope={scope!r} key={new_key!r} total={len(self.appList)}")

    @script(
        description=_("Remove current window title from notifier list"),
        category=_("Multi-tasking notifier"),
        gesture="kb:NVDA+shift+d",
    )
    def script_removeCurrentWindowTitle(self, gesture=None):
        # 삭제 소스도 foreground (메모장 자식 컨트롤 케이스 대응).
        fg, appId, title, key = get_current_window_info()
        if not title:
            ui.message("창 제목을 확인할 수 없어요.", speechPriority=speech.Spri.NEXT)
            return

        # 우선순위 창 > 앱. 무엇을 지웠는지 음성으로 명확히 알려줌.
        # title-only fallback은 일부러 사용하지 않음 — 다른 앱의 동일 title 창을
        # 의도와 다르게 지울 위험. 매칭(_match_and_beep)에선 fallback이 유용하지만
        # 삭제는 정확 매치만 허용한다. 앱 entry 삭제 시 같은 appId 창 entry는
        # 그대로 둠 (안전 원칙. 일괄 삭제는 목록 다이얼로그에서 명시적으로 가능).
        original = list(self.appList)
        removed_scope = None
        if key in self.windowLookup:
            self.appList.remove(key)
            removed_scope = SCOPE_WINDOW
        elif appId in self.appLookup:
            self.appList.remove(appId)
            removed_scope = SCOPE_APP
        else:
            ui.message("목록에 없는 항목이에요.", speechPriority=speech.Spri.NEXT)
            return

        if not appListStore.save(self.appListFile, self.appList):
            self.appList = original
            ui.message(
                "앱 목록을 저장하는 중 문제가 생겼어요. 다시 시도해 주세요.",
                speechPriority=speech.Spri.NOW,
            )
            return
        self._rebuild_lookup()
        if removed_scope == SCOPE_APP:
            ui.message("앱 전체에서 삭제했어요.", speechPriority=speech.Spri.NEXT)
        else:
            ui.message("창에서 삭제했어요.", speechPriority=speech.Spri.NEXT)
        log.info(f"mtwn: remove succeeded scope={removed_scope!r} total={len(self.appList)}")

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

        def show_dialog():
            gui.mainFrame.prePopup()
            dlg = AppListDialog(
                gui.mainFrame,
                self.appList,
                get_scope=self._meta_for,
                on_delete=self._delete_entries_from_dialog,
            )
            dlg.ShowModal()
            dlg.Destroy()
            gui.mainFrame.postPopup()

        wx.CallAfter(show_dialog)
        ui.message(
            f"총 {len(self.appList)}개를 표시했어요.",
            speechPriority=speech.Spri.NEXT,
        )

    def _delete_entries_from_dialog(self, entries) -> bool:
        """목록 다이얼로그에서 일괄 삭제 호출 시 진행. 저장 성공 여부 반환.

        에러 알림은 listDialog 측 wx.MessageBox로 통일 (이중 알림 방지).
        성공 시 _rebuild_lookup + 음성 안내.
        """
        if not entries:
            return True
        new_list = [e for e in self.appList if e not in entries]
        if not appListStore.save(self.appListFile, new_list):
            return False
        self.appList = new_list
        self._rebuild_lookup()
        ui.message(
            f"{len(entries)}개 항목을 목록에서 삭제했어요.",
            speechPriority=speech.Spri.NEXT,
        )
        log.info(f"mtwn: dialog bulk delete count={len(entries)} total={len(self.appList)}")
        return True

    # -------- 이벤트 훅 --------

    def _log_focus_diag(self, obj):
        """debugLogging=True 진단 로그. 본 로직 침범 방지를 위해 전용 try/except로 격리.

        Ctrl+Tab 등에서 비프가 안 나는 원인을 실측으로 특정하기 위한 일회성 기록.
        NVDA 로그에 한 줄/이벤트로 남는다. settings.get("debugLogging")이 True일
        때만 event_gainFocus가 호출하므로 off 상태에선 함수 호출 자체 없음.
        """
        try:
            wcn = getattr(obj, "windowClassName", "") if obj is not None else ""
            obj_name = (getattr(obj, "name", "") or "") if obj is not None else ""
            role = getattr(obj, "role", "") if obj is not None else ""
            parent = getattr(obj, "parent", None) if obj is not None else None
            parent_wcn = getattr(parent, "windowClassName", "") if parent is not None else ""
            fg = api.getForegroundObject()
            fg_wcn = getattr(fg, "windowClassName", "") if fg is not None else ""
            fg_name = (getattr(fg, "name", "") or "") if fg is not None else ""
            try:
                obj_app = getAppId(obj) if obj is not None else ""
            except Exception:
                obj_app = "<err>"
            log.info(
                f"mtwn: DBG gF wcn={wcn!r} name={obj_name!r} role={role!r} "
                f"parentWcn={parent_wcn!r} fgWcn={fg_wcn!r} fgName={fg_name!r} "
                f"appId={obj_app!r}"
            )
        except Exception:
            log.exception("mtwn: debug log failed")

    def _determine_match_source(self, obj, wcn, appId, fg, fg_wcn):
        """event_gainFocus 4분기 판정. 매칭 대상이면 raw_title(str), 아니면 None.

        우선순위: alt_tab > app_overlay > tab_editor > enable_all.
        in_app_overlay(fg.wcn 기반)와 in_tab_editor(obj.wcn 기반)가 같은 이벤트에서
        둘 다 True가 될 수 있어도 아래 `if in_alt_tab or in_app_overlay: src = obj`로
        overlay가 editor를 이긴다. 비프는 어느 쪽이든 1회이며 dedup 가드로 중복 억제.
          1) Alt+Tab 오버레이 — obj.wcn이 Windows.UI.Input.InputSite.WindowClass.
             obj 자신이 "선택 후보 창"의 name을 들고 있다.
          2) 앱별 오버레이 (예: Notepad++ MRU) — fgWcn이 appId의 overlay
             리스트에 등록된 상위창 wcn이면 overlay 모드. obj는 리스트 항목.
          3) 에디터 자식 컨트롤 (예: 메모장 RichEditD2DPT) — obj.wcn이 appId의
             editor 리스트에 있으면 editor 모드. foreground.name이 탭 제목.
          4) enableAllWindows — 1~3 해당 없어도 전역 on일 때 foreground name.
        """
        in_alt_tab     = wcn == "Windows.UI.Input.InputSite.WindowClass"
        in_app_overlay = tabClasses.is_overlay_class(appId, fg_wcn)
        in_tab_editor  = tabClasses.is_editor_class(appId, wcn)
        enable_all = settings.get("enableAllWindows")

        if not (enable_all or in_alt_tab or in_app_overlay or in_tab_editor):
            return None

        # 매칭 소스 결정:
        #   - alt_tab/overlay: obj.name이 탭 제목 (Alt+Tab 후보 창, MRU 리스트 항목)
        #   - editor/enable_all: foreground.name이 활성 탭 제목. fg None이면 obj 폴백.
        if in_alt_tab or in_app_overlay:
            src = obj
        else:
            src = fg or obj

        raw_title = (getattr(src, "name", "") or "").strip()
        if not raw_title:
            return None
        return raw_title

    def event_gainFocus(self, obj, nextHandler):
        # 창 전환 시 파일 I/O 없음. 메모리 목록만 참조.
        # event_gainFocus는 모든 포커스 전환마다 호출되므로, 본 애드온 예외가
        # NVDA 이벤트 체인을 끊지 않도록 try/except + finally로 nextHandler() 보장.
        try:
            if settings.get("debugLogging"):
                self._log_focus_diag(obj)

            if obj is None:
                return

            wcn = getattr(obj, "windowClassName", "")
            appId = getAppId(obj)
            fg = api.getForegroundObject()
            fg_wcn = getattr(fg, "windowClassName", "") if fg is not None else ""

            raw_title = self._determine_match_source(obj, wcn, appId, fg, fg_wcn)
            if not raw_title:
                return
            # title 정규화: 꼬리 " - 앱명" 한 덩이 제거로 Alt+Tab obj.name,
            # editor fg.name, overlay obj.name을 같은 형태로 통일 → 등록 데이터와
            # 정확 일치. appId는 scope=window 복합키의 1등 요소라 title에 앱명을
            # 중복 저장하지 않는다.
            title = normalize_title(raw_title)
            if not title:
                return
            self._match_and_beep(appId, title)
        except Exception:
            log.exception("mtwn: event_gainFocus failed")
        finally:
            nextHandler()
