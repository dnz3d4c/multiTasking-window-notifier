# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""@script 핸들러 모음을 GlobalPlugin에서 분리.

`__init__.py`는 설정/이벤트 훅/모듈 결합만 담당하고, 단축키 4종과 보조 헬퍼
(_do_add / _delete_entries_from_dialog)는 이 파일의 `ScriptsMixin`이 담당한다.

NVDA의 스크립트 스캔은 클래스 MRO를 따르므로 mixin 메서드의 @script
데코레이터도 GlobalPlugin 서브클래스에서 정상 바인딩된다.

ScriptsMixin이 읽는 GlobalPlugin 속성:
    - self.appList / self.appListFile
    - self.windowLookup / self.appLookup (LookupIndex 경유 property)
    - self._rebuild_lookup()
    - self._reset_flush_schedule() (reload 시 카운터/타이머 초기화)
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

# ScriptableType은 @script(gesture=)의 기본 바인딩을 수집하는 NVDA 메타클래스.
# Mixin에 이걸 명시하지 않으면 namespace-only 스캔 경로(baseObject.py:186-205)가
# Mixin body의 script_* 메서드를 만나지 못해 _gestureMap이 공란으로 남고,
# 입력 제스처 대화상자에 기본 단축키가 표시되지 않는다. NVDA 외부(단위 테스트 등)
# 에서 import 실패 시 fallback은 type — 그 상황에선 gesture 바인딩 검증을 하지 않음.
try:
    from baseObject import ScriptableType
except ImportError:
    ScriptableType = type

from . import store
from .appIdentity import makeAppKey, normalize_title
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


def _prompt_for_alias(current_alias: str = "") -> str | None:
    """alias 입력 다이얼로그를 띄우고 결과 문자열 반환.

    Alt+Tab 오버레이 이름과 foreground 제목이 다른 앱을 단일 entry로 매칭
    하기 위한 "대체 제목" 입력창. 등록(NVDA+Shift+T) 흐름과 목록 다이얼로그
    편집 흐름 양쪽에서 공유.

    Args:
        current_alias: 기본값으로 표시할 현재 alias. 등록 시에는 "".
            편집 시에는 entry의 기존 aliases[0]을 넣는다.

    Returns:
        str | None:
            - None: 사용자가 Cancel을 눌러 조작 전체를 취소.
            - "": 확인은 눌렀지만 값이 비어 alias 없이 진행 (또는 제거).
            - 그 외 str: 입력 원문(호출부가 normalize_title 적용).
    """
    gui.mainFrame.prePopup()
    try:
        prompt = _(
            "이 항목이 Alt+Tab 등 다른 경로에서 다른 이름으로 들리면 입력해요.\n"
            "예: 어떤 메신저앱은 Alt+Tab에서 '대화창제목' 같은 대화 이름으로 보여요.\n"
            "대체 제목이 없다면 빈 값으로 확인하면 돼요."
        )
        dlg = wx.TextEntryDialog(
            gui.mainFrame,
            prompt,
            _("창 전환 알림 — 대체 제목"),
            value=current_alias or "",
        )
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return None
            return dlg.GetValue().strip()
        finally:
            dlg.Destroy()
    finally:
        gui.mainFrame.postPopup()


class ScriptsMixin(metaclass=ScriptableType):
    """GlobalPlugin의 @script 핸들러 + 보조 헬퍼 모음.

    scriptCategory를 여기 선언하면 NVDA Input gestures 다이얼로그에서 이 mixin을
    상속한 GlobalPlugin의 모든 @script가 같은 카테고리로 묶인다. 각 @script에
    category 인자를 반복 선언할 필요 없음.

    metaclass=ScriptableType 지정 이유: @script(gesture=) 기본 바인딩은 클래스
    생성 시점에 namespace를 스캔해 _<ClassName>__gestures dict를 만드는 경로로만
    _gestureMap에 등록된다. Mixin을 기본 type 메타로 두면 이 경로를 통째로 우회해
    입력 제스처 대화상자에 기본 단축키가 표시되지 않는다(userGestureMap 수동
    등록 경로로만 우연히 동작). GlobalPlugin(ScriptsMixin, ...) 상속 트리에서
    ScriptsMixin 자체가 ScriptableType을 메타클래스로 가지면, __init__의 MRO
    순회가 _ScriptsMixin__gestures를 찾아 bindGestures로 적용한다.
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
        foreground, appId, title, key = get_current_window_info()
        if not title:
            ui.message(_("창 제목을 확인할 수 없어요."), speechPriority=speech.Spri.NEXT)
            return

        # 사전 중복 검사: 창과 앱 둘 다 이미 등록돼 있으면 다이얼로그 건너뛰고 즉시 안내.
        # 한쪽만 등록돼 있으면 다이얼로그는 뜨되 라벨에 꼬리표로 상태 표시 — 사용자는
        # 남은 scope로만 추가 가능. _do_add 내부 중복 검사는 안전망으로 유지.
        window_registered = key in self.windowLookup
        app_registered = appId in self.appLookup
        if window_registered and app_registered:
            ui.message(_("이미 창과 앱 둘 다 목록에 있어요."), speechPriority=speech.Spri.NEXT)
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
            # 모달 종료 후 같은 GUI 스레드에서 즉시 alias 입력 → _do_add 호출.
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
            if selected_scope is None:
                return
            # alias(대체 제목) 입력 — scope 무관하게 동일 프롬프트. 빈 값 허용.
            # 사용자가 Cancel하면 등록 자체 취소(앞선 scope 선택 무효화).
            alias = _prompt_for_alias(current_alias="")
            if alias is None:
                return
            self._do_add(appId, title, key, selected_scope, alias=alias)

        wx.CallAfter(show_choice)

    def _do_add(self, appId, title, key, scope, alias: str = ""):
        """scope 선택 후 실제 등록. GUI 스레드에서 호출.

        alias는 `_prompt_for_alias`가 반환한 정규화 전 원문. 빈 문자열이면
        aliases=[] (기본값)으로 저장. 비어있지 않으면 normalize_title 적용
        후 aliases=[정규화값] 1개만 저장. UI 규약: 한 항목당 최대 alias 1개.
        """
        # 중복 체크: scope별로 나뉘므로 같은 appId여도 창 등록과 앱 등록은 공존 허용.
        if scope == SCOPE_WINDOW:
            if key in self.windowLookup:
                ui.message(_("이미 목록에 있어요."), speechPriority=speech.Spri.NEXT)
                return
            new_key = key
        else:  # SCOPE_APP
            if appId in self.appLookup:
                ui.message(_("이미 목록에 있어요."), speechPriority=speech.Spri.NEXT)
                return
            new_key = makeAppKey(appId)

        # 하드 상한(MAX_ITEMS=128) 적용. v7부터 사용자 운영 상한 슬라이더 제거 —
        # BEEP_TABLE_SIZE(35)와 디커플되어 있고 비프 변별이 BEEP_TABLE 안에서 끝나서
        # 사용자가 직접 줄일 실용 이유가 없다.
        if len(self.appList) >= MAX_ITEMS:
            ui.message(
                _("목록이 가득 찼어요. 몇 개 지우고 다시 시도해 주세요."),
                speechPriority=speech.Spri.NEXT,
            )
            return

        self.appList.append(new_key)
        if not store.save(self.appListFile, self.appList, scopes={new_key: scope}):
            self.appList.pop()
            ui.message(
                _("앱 목록을 저장하는 중 문제가 생겼어요. 다시 시도해 주세요."),
                speechPriority=speech.Spri.NOW,
            )
            return

        # alias 적용: 입력이 있으면 normalize_title로 꼬리 서픽스를 벗긴 뒤 저장.
        # 매칭 경로(eventRouter의 3-way handle_foreground/dispatch_focus/handle_name_change)는 모두 정규화된 title을
        # 쓰므로 저장 시에도 같은 형태로 통일해야 역매핑이 히트한다.
        normalized_alias = normalize_title(alias) if alias else ""
        if normalized_alias:
            if not store.set_aliases(self.appListFile, new_key, [normalized_alias]):
                # alias 저장 실패 — 본 등록은 성공했으므로 롤백하지 않음.
                # 사용자에게 경고만. listDialog 편집으로 재시도 가능.
                ui.message(
                    _("추가는 됐는데 대체 제목을 저장하지 못했어요. "
                      "목록 다이얼로그에서 다시 시도해 주세요."),
                    speechPriority=speech.Spri.NOW,
                )
                log.warning(
                    f"mtwn: set_aliases failed after add key={new_key!r} alias={normalized_alias!r}"
                )
        self._rebuild_lookup()

        # 사용자 알림: scope 알림 먼저, alias 있으면 별도 줄로 이어서.
        # f-string에 사용자 데이터를 조사 템플릿으로 박지 않고 ": " 경계로
        # 분리해 NVDA 발화 호흡을 확보.
        if scope == SCOPE_APP:
            ui.message(
                _("앱 전체로 추가했어요: {appId}").format(appId=appId),
                speechPriority=speech.Spri.NEXT,
            )
        else:
            ui.message(
                _("창으로 추가했어요: {appId} | {title}").format(appId=appId, title=title),
                speechPriority=speech.Spri.NEXT,
            )
        if normalized_alias:
            ui.message(
                _("대체 제목도 저장했어요: {alias}").format(alias=normalized_alias),
                speechPriority=speech.Spri.NEXT,
            )
        log.info(
            f"mtwn: add succeeded scope={scope!r} key={new_key!r} "
            f"alias={normalized_alias!r} total={len(self.appList)}"
        )

    @script(
        description=_("Remove current window title from notifier list"),
        gesture="kb:nvda+shift+d",
    )
    def script_removeCurrentWindowTitle(self, gesture=None):
        # 삭제 소스도 foreground (메모장 자식 컨트롤 케이스 대응).
        foreground, appId, title, key = get_current_window_info()
        if not title:
            ui.message(_("창 제목을 확인할 수 없어요."), speechPriority=speech.Spri.NEXT)
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
            ui.message(_("목록에 없는 항목이에요."), speechPriority=speech.Spri.NEXT)
            return

        if not store.save(self.appListFile, self.appList):
            self.appList = original
            ui.message(
                _("앱 목록을 저장하는 중 문제가 생겼어요. 다시 시도해 주세요."),
                speechPriority=speech.Spri.NOW,
            )
            return
        self._rebuild_lookup()
        if removed_scope == SCOPE_APP:
            ui.message(_("앱 전체에서 삭제했어요."), speechPriority=speech.Spri.NEXT)
        else:
            ui.message(_("창에서 삭제했어요."), speechPriority=speech.Spri.NEXT)
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
        self._reset_flush_schedule()
        ui.message(
            _("목록을 다시 불러왔어요. 지금 {count}개예요.").format(count=len(items)),
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
            ui.message(_("등록된 창이 없어요."), speechPriority=speech.Spri.NEXT)
            return

        def show_dialog():
            gui.mainFrame.prePopup()
            dlg = AppListDialog(
                gui.mainFrame,
                self.appList,
                get_meta=self._meta_for,
                on_delete=self._delete_entries_from_dialog,
                on_edit_alias=self._edit_alias_from_dialog,
            )
            dlg.ShowModal()
            dlg.Destroy()
            gui.mainFrame.postPopup()

        wx.CallAfter(show_dialog)
        ui.message(
            _("총 {count}개를 표시했어요.").format(count=len(self.appList)),
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
            _("{count}개 항목을 목록에서 삭제했어요.").format(count=len(entries)),
            speechPriority=speech.Spri.NEXT,
        )
        log.info(f"mtwn: dialog bulk delete count={len(entries)} total={len(self.appList)}")
        return True

    def _edit_alias_from_dialog(self, entry: str) -> bool | None:
        """목록 다이얼로그에서 단일 항목의 alias 편집 호출.

        TextEntryDialog로 현재 alias를 기본값으로 보여주고 입력받아
        `store.set_aliases`로 즉시 저장. 빈 값 확인 시 alias 제거.

        Returns:
            True: 편집 성공 (alias 설정/변경/제거).
            False: 디스크 저장 실패. listDialog가 에러 메시지 표시.
            None: 사용자가 Cancel 눌러 변경 없음. listDialog는 아무 알림 안 함.
        """
        meta = self._meta_for(entry) or {}
        current_aliases = meta.get("aliases") or []
        current = current_aliases[0] if current_aliases else ""

        new_input = _prompt_for_alias(current_alias=current)
        if new_input is None:
            return None  # 사용자 취소
        normalized = normalize_title(new_input) if new_input else ""
        # 기존 값과 정규화 결과가 같으면 no-op (불필요한 디스크 쓰기 방지)
        if normalized == current:
            ui.message(
                _("대체 제목에 변화가 없어 그대로 두었어요."),
                speechPriority=speech.Spri.NEXT,
            )
            return True

        new_aliases = [normalized] if normalized else []
        if not store.set_aliases(self.appListFile, entry, new_aliases):
            return False
        self._rebuild_lookup()
        if normalized:
            # 사용자 입력을 조사(`'...'(으)로`) 템플릿에 박지 않고 ": " 경계로
            # 분리해 발화 품질 확보. 기존 "추가/삭제했어요" 메시지 톤과 일치.
            ui.message(
                _("대체 제목을 바꿨어요: {alias}").format(alias=normalized),
                speechPriority=speech.Spri.NEXT,
            )
        else:
            ui.message(
                _("대체 제목을 지웠어요."),
                speechPriority=speech.Spri.NEXT,
            )
        log.info(
            f"mtwn: alias edited entry={entry!r} "
            f"{current!r} → {normalized!r}"
        )
        return True
