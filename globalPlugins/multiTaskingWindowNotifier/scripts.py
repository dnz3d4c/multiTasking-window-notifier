# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""@script 핸들러 모음을 GlobalPlugin에서 분리.

Phase 2 최종 단계. `__init__.py`에는 설정/이벤트 훅/모듈 결합만 남기고
단축키 4종과 보조 헬퍼(_do_add / _delete_entries_from_dialog)는 이 파일의
`ScriptsMixin`이 담당한다.

NVDA의 스크립트 스캔은 클래스 MRO를 따르므로 mixin 메서드의 @script
데코레이터도 GlobalPlugin 서브클래스에서 정상 바인딩된다.

ScriptsMixin이 읽는 GlobalPlugin 속성:
    - self.appList / self.appListFile
    - self.windowLookup / self.appLookup (LookupIndex 경유 property)
    - self._rebuild_lookup()
    - self._flush_scheduler (FlushScheduler, reload 시 reset)
    - self._meta_for(entry)  (listDialog에 scope 콜백으로 전달)

역방향(__init__.py → scripts.py) 의존은 ScriptsMixin 상속 한 줄이 전부.
"""

from __future__ import annotations

import wx
import ui
import gui
import speech
from logHandler import log
from scriptHandler import script

from . import store
from .appIdentity import makeAppKey
from .constants import MAX_ITEMS, SCOPE_APP, SCOPE_WINDOW
from .listDialog import AppListDialog
from .windowInfo import get_current_window_info

# 번역 초기화(선택) — __init__.py와 동일한 패턴. 테스트 환경에서는 no-op.
try:
    import addonHandler
    addonHandler.initTranslation()
    _  # noqa: F401
except Exception:
    def _(s):
        return s


class ScriptsMixin:
    """GlobalPlugin의 @script 핸들러 + 보조 헬퍼 모음.

    scriptCategory를 여기 선언하면 NVDA Input gestures 다이얼로그에서 이 mixin을
    상속한 GlobalPlugin의 모든 @script가 같은 카테고리로 묶인다. 각 @script에
    category 인자를 반복 선언할 필요 없음.
    """

    # Translators: Input gestures 다이얼로그에 표시되는 카테고리 이름
    scriptCategory = _("Multi-tasking notifier")

    # -------- 스크립트 --------

    @script(
        description=_("Add current window title to notifier list"),
        gesture="kb:nvda+shift+t",
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

        # 하드 상한(MAX_ITEMS=128) 적용. v7부터 사용자 운영 상한 슬라이더 제거 —
        # BEEP_TABLE_SIZE(35)와 디커플되어 있고 비프 변별이 BEEP_TABLE 안에서 끝나서
        # 사용자가 직접 줄일 실용 이유가 없다.
        if len(self.appList) >= MAX_ITEMS:
            ui.message(
                "목록이 가득 찼어요. 몇 개 지우고 다시 시도해 주세요.",
                speechPriority=speech.Spri.NEXT,
            )
            return

        self.appList.append(new_key)
        if not store.save(self.appListFile, self.appList, scopes={new_key: scope}):
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
        gesture="kb:nvda+shift+d",
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

        if not store.save(self.appListFile, self.appList):
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
        gesture="kb:nvda+shift+r",
    )
    def script_reloadAppList(self, gesture=None):
        # reload는 미저장 변경분을 먼저 flush한 뒤 캐시 무효화 후 재로드한다.
        items = store.reload(self.appListFile)
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
        gesture="kb:nvda+shift+i",
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
        if not store.save(self.appListFile, new_list):
            return False
        self.appList = new_list
        self._rebuild_lookup()
        ui.message(
            f"{len(entries)}개 항목을 목록에서 삭제했어요.",
            speechPriority=speech.Spri.NEXT,
        )
        log.info(f"mtwn: dialog bulk delete count={len(entries)} total={len(self.appList)}")
        return True
