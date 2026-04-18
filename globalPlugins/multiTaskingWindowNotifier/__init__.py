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
import speech
import globalPluginHandler
from logHandler import log
from scriptHandler import script

from .constants import ADDON_NAME, ALT_TAB_OVERLAY_WCN, MAX_ITEMS, SCOPE_APP, SCOPE_WINDOW
from .appIdentity import getAppId, makeKey, makeAppKey, normalize_title, splitKey
from . import appListStore
from . import settings
from . import tabClasses
from .windowInfo import config_addon_dir, get_current_window_info
from .beepPlayer import play_beep
from .listDialog import AppListDialog
from .settingsPanel import MultiTaskingSettingsPanel
from .switchFlusher import FlushScheduler
from .lookupIndex import LookupIndex

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
            log.exception("mtwn: tabClasses load failed — overlay branch disabled")
        # 매칭용 룩업 인덱스. windowLookup/appLookup 두 dict는 LookupIndex가 소유하고,
        # GlobalPlugin은 property로 read-only 노출(기존 테스트 호환).
        self._lookup = LookupIndex(meta_provider=self._meta_for)
        self._rebuild_lookup()
        # 전환 카운트 디바운스 저장: switchFlusher가 카운터/타이머 상태 캡슐화.
        self._flush_scheduler = FlushScheduler(appListStore.flush, self.appListFile)
        # 시그니처 기반 dedup — (appId, title, tab_sig)가 연속으로 같으면 skip.
        # 확정 탭 전환은 title 또는 tab_sig(hwnd)가 바뀌므로 자연 통과하고,
        # 같은 탭 자식 컨트롤 재진입 같은 이벤트 중복 폭주만 흡수한다.
        # 시간 기반 가드는 쓰지 않는다 — "같은 제목 다른 탭"을 key만 보고 잘라내는
        # 부작용(메모장 '제목 없음' 여러 개, 빠른 탭 왕복)이 드러나 제거했다.
        self._last_event_sig = None

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

    def _meta_for(self, entry):
        """디스크 메타에서 scope를 조회. 메타 없으면 기본 SCOPE_WINDOW로 간주.

        appListStore가 아직 로드 안 됐거나(부팅 직후) entry가 막 추가되어 메타가
        없을 수 있다. 그런 케이스에서도 안전하게 동작하도록 fallback.
        """
        meta = appListStore.get_meta(self.appListFile, entry) or {}
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

    def _match_and_beep(self, appId, title, tab_sig=0):
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
        key = makeKey(appId, title)

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

        # 시그니처 dedup: (appId, title, tab_sig) 동일이면 skip.
        # tab_sig(hwnd)는 호출부에서 분기별로 추출. 같은 탭 자식 컨트롤 재진입은
        # hwnd 동일 → skip. Ctrl+Tab으로 다른 탭이 되면 hwnd 달라 통과. 시간 개념
        # 없이 "직전 이벤트와 완전 동일한가"만 보기 때문에 빠른 탭 왕복(A→B→A)도
        # 중간 B에서 sig가 갱신되어 복귀한 A가 정상 통과한다. 단 중간 B에 대한
        # 이벤트 자체가 누락되면(A→A만 두 번) 두 번째 A가 여기서 조용히 skip되어
        # 사용자 관점엔 "비프 누락"으로 보인다. debugLogging 켰을 때 이 경로도
        # 기록해서 "왜 안 울렸는지" 실측 가능하게 한다.
        event_sig = (appId, title, tab_sig)
        if event_sig == self._last_event_sig:
            if settings.get("debugLogging"):
                log.info(f"mtwn: DBG sig_guard skip sig={event_sig!r}")
            return
        self._last_event_sig = event_sig

        app_idx, tab_idx = self._resolve_beep_pair(matched_key, scope, appId)
        play_beep(
            app_idx, tab_idx, scope,
            duration=settings.get("beepDuration"),
            gap_ms=settings.get("beepGapMs"),
            left=settings.get("beepVolumeLeft"),
            right=settings.get("beepVolumeRight"),
        )
        appListStore.record_switch(self.appListFile, matched_key)
        self._flush_scheduler.notify_switch()
        self._flush_scheduler.maybe_flush()

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

        # 사전 중복 검사: 창과 앱 둘 다 이미 등록돼 있으면 다이얼로그 건너뛰고 즉시 안내.
        # 한쪽만 등록돼 있으면 다이얼로그는 뜨되 라벨에 꼬리표로 상태 표시 — 사용자는
        # 남은 scope로만 추가 가능. _do_add 내부 중복 검사는 안전망으로 유지.
        window_registered = key in self.windowLookup
        app_registered = appId in self.appLookup
        if window_registered and app_registered:
            ui.message("이미 창과 앱 둘 다 목록에 있어요.", speechPriority=speech.Spri.NEXT)
            return

        # scope 선택 다이얼로그를 GUI 스레드에서 띄우고 결과를 콜백으로 처리.
        # wx.SingleChoiceDialog는 키보드/스크린리더 친화적이며 기본 포커스가
        # 첫 항목("이 창만")이라 Enter 한 번으로 기존 동작 재현 가능.
        # Translators: scope 선택 다이얼로그에서 이미 등록된 항목 끝에 붙는 꼬리표.
        # 앞 공백은 번역 문자열 밖에 두어 번역 시 공백 유실 위험 차단.
        already_suffix = " " + _("(이미 등록됨)")
        choices = [
            (_("이 창만 (%(app)s | %(title)s)") % {"app": appId, "title": title})
            + (already_suffix if window_registered else ""),
            (_("이 앱 전체 (%s)") % appId)
            + (already_suffix if app_registered else ""),
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
        self._flush_scheduler.reset()
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
        """event_gainFocus 3분기 판정.

        매칭 대상이면 (raw_title, tab_sig), 아니면 None.

        대부분의 Ctrl+Tab 확정 전환은 `event_nameChange`가 foreground title
        변경으로 감지한다. 여기서는 nameChange가 못 잡거나 의미가 없는 경로만
        다룬다.

          1) Alt+Tab 오버레이 — obj.wcn이 `ALT_TAB_OVERLAY_WCN`. obj 자신이
             "선택 후보 창"의 name을 들고 있음.
          2) 앱별 오버레이 (예: Notepad++ MRU) — fgWcn이 appId의 overlay
             목록에 있음. obj가 리스트 항목.
          3) 에디터 자식 컨트롤 — `is_editor_class(appId, wcn) AND wcn != fg_wcn`.
             메모장 "제목 없음" 여러 탭처럼 title이 안 바뀌어 nameChange로는
             구분 불가한 앱 전용. `wcn != fg_wcn` 게이트가 자식==최상위 wcn인
             앱(Firefox 계열)의 과도 매칭을 자동 차단한다. 이 분기는 fg.name을
             탭 제목으로, obj.windowHandle(자식 hwnd, 탭별 고유)을 tab_sig로
             쓴다.
        """
        in_alt_tab     = wcn == ALT_TAB_OVERLAY_WCN
        in_app_overlay = tabClasses.is_overlay_class(appId, fg_wcn)
        in_tab_editor  = (tabClasses.is_editor_class(appId, wcn)
                          and wcn != fg_wcn)

        if not (in_alt_tab or in_app_overlay or in_tab_editor):
            return None

        # 매칭 소스: alt_tab/overlay는 obj.name(후보·리스트 항목 자체),
        # editor는 fg.name(= 활성 탭 제목 포함한 창 title bar).
        if in_tab_editor:
            src = fg or obj
        else:
            src = obj

        raw_title = (getattr(src, "name", "") or "").strip()
        if not raw_title:
            return None

        # tab_sig: editor 분기는 **항상 obj(자식)**의 hwnd. fg.windowHandle로 쓰면
        # 메모장 같은 "제목 없음" 여러 탭이 같은 최상위 hwnd를 공유해 구분 불가.
        # 나머지 분기는 title 소스와 같은 obj의 hwnd.
        sig_obj = obj if in_tab_editor else src
        try:
            tab_sig = int(getattr(sig_obj, "windowHandle", 0) or 0)
        except Exception:
            tab_sig = 0
        return raw_title, tab_sig

    def event_gainFocus(self, obj, nextHandler):
        # event_gainFocus는 모든 포커스 전환마다 호출되므로 본 애드온 예외가
        # NVDA 이벤트 체인을 끊지 않도록 try/except + finally로 nextHandler() 보장.
        # 여기서는 오버레이(Alt+Tab / 앱별 MRU) 탐색만 처리한다.
        try:
            if settings.get("debugLogging"):
                self._log_focus_diag(obj)

            if obj is None:
                return

            wcn = getattr(obj, "windowClassName", "")
            appId = getAppId(obj)
            fg = api.getForegroundObject()
            fg_wcn = getattr(fg, "windowClassName", "") if fg is not None else ""

            match_source = self._determine_match_source(obj, wcn, appId, fg, fg_wcn)
            if match_source is None:
                return
            raw_title, tab_sig = match_source
            title = normalize_title(raw_title)
            if not title:
                return
            self._match_and_beep(appId, title, tab_sig=tab_sig)
        except Exception:
            log.exception("mtwn: event_gainFocus failed")
        finally:
            nextHandler()

    def event_nameChange(self, obj, nextHandler):
        """탭 확정 전환 감지. foreground 창 자체의 name 변경만 매칭 입력으로 사용.

        Ctrl+Tab / Ctrl+Shift+Tab 등으로 탭이 확정 전환되면 대부분 앱에서 최상위
        창의 title bar가 바뀐다. Firefox / Notepad++가 여기에 해당. 메모장처럼
        "제목 없음" 여러 탭을 동시에 쓰면 title이 안 바뀌어 이 훅으로는 구분
        불가 — 그 케이스는 `event_gainFocus`의 editor 분기가 자식 hwnd로 구분.

        자식 요소(웹 DOM, 동적 레이블 등)의 name 변경은 `obj.name != fg.name`
        비교로 걸러진다. NVDA는 같은 창의 자식 객체에도 nameChange를 쏘지만
        fg.name과는 보통 다른 값을 갖기 때문.
        """
        try:
            if obj is None:
                return
            fg = api.getForegroundObject()
            if fg is None:
                return
            fg_name = (getattr(fg, "name", "") or "").strip()
            obj_name = (getattr(obj, "name", "") or "").strip()
            debug = settings.get("debugLogging")
            if not obj_name or obj_name != fg_name:
                if debug:
                    log.info(
                        f"mtwn: DBG nameChange skip obj_name={obj_name!r} "
                        f"fg_name={fg_name!r}"
                    )
                return
            appId = getAppId(obj)
            title = normalize_title(obj_name)
            if not title:
                if debug:
                    log.info(
                        f"mtwn: DBG nameChange skip-normalize obj_name={obj_name!r}"
                    )
                return
            try:
                tab_sig = int(getattr(obj, "windowHandle", 0) or 0)
            except Exception:
                tab_sig = 0
            if debug:
                log.info(
                    f"mtwn: DBG nameChange appId={appId!r} title={title!r} "
                    f"tab_sig={tab_sig}"
                )
            self._match_and_beep(appId, title, tab_sig=tab_sig)
        except Exception:
            log.exception("mtwn: event_nameChange failed")
        finally:
            nextHandler()
