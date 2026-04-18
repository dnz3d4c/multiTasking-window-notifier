# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""등록된 창/앱 목록을 보여주고 삭제까지 처리하는 wx.Dialog.

Phase 3 변경:
    - scope 표시: `[앱] chrome` / `[창] chrome | YouTube ...`
    - 다중 선택(`wx.LB_EXTENDED`) + Delete 키/삭제 버튼으로 일괄 삭제
    - 앱 entry 삭제 시 "관련 창도 같이 지울까요?" 확인 다이얼로그
    - 실제 저장/lookup 갱신은 호출자가 주입한 on_delete 콜백 책임 (결합도 낮춤)
"""

import wx

from gui import guiHelper

from .appIdentity import splitKey
from .constants import SCOPE_APP, SCOPE_WINDOW

# 번역 초기화(선택). NVDA 외 환경에서 _를 정의해두는 폴백.
try:
    import addonHandler
    addonHandler.initTranslation()
    _  # noqa: F401
except Exception:
    def _(s):
        return s


class AppListDialog(wx.Dialog):
    """등록된 창/앱 목록 다이얼로그.

    Args:
        parent: 부모 wx 창.
        appList: 등록된 entry 키 리스트 (순서 보존).
        get_scope: callable(entry) -> "app" | "window". GlobalPlugin._meta_for를 주입.
        on_delete: callable(entries_to_remove: list[str]) -> bool. 저장 성공 여부 반환.
            None이면 삭제 UI 비활성화 (조회 전용).
    """

    def __init__(self, parent, appList, get_scope=None, on_delete=None):
        super().__init__(parent, title=_("등록된 창 목록"))
        self.appList = list(appList)
        self._get_scope = get_scope or (lambda e: SCOPE_WINDOW)
        self._on_delete = on_delete
        # 표시 순서: scope 무관하게 표시 텍스트 정렬. 내부 entry 매핑은 _entries에 보관.
        self._entries = sorted(self.appList, key=lambda e: self._display_text(e).lower())
        self._create_ui()
        self.CenterOnScreen()

    def _create_ui(self):
        # NVDA 설정 대화상자 관례: sHelper를 독립적으로 만들고 바깥 mainSizer가
        # BORDER_FOR_DIALOGS 여백을 한 겹 감싼다 (LanguageRestartDialog 패턴).
        # 이 여백이 없으면 addDialogDismissButtons의 ALIGN_RIGHT 결과가 창 가장
        # 오른쪽에 딱 붙어 보이고, 전체 레이아웃이 NVDA 다른 대화상자와 어긋난다.
        sHelper = guiHelper.BoxSizerHelper(self, orientation=wx.VERTICAL)

        # 카운트 라벨 — 일괄 삭제 후 SetLabel로 갱신 대상이라 멤버로 보관.
        self.countLabel = sHelper.addItem(
            wx.StaticText(self, label=self._count_text())
        )

        # addLabeledControl: ListBox 앞에 "등록된 항목:" 라벨을 붙여 NVDA가 낭독.
        # size는 기존 픽셀값 유지. style에 LB_EXTENDED(다중 선택) + LB_HSCROLL.
        self.listBox = sHelper.addLabeledControl(
            _("등록된 항목:"),
            wx.ListBox,
            choices=[self._display_text(e) for e in self._entries],
            style=wx.LB_EXTENDED | wx.LB_HSCROLL,
            size=(560, 320),
        )
        self.listBox.Bind(wx.EVT_KEY_DOWN, self._on_listbox_key)

        # "선택 항목 삭제"는 다이얼로그를 닫지 않는 action 버튼이므로 addItem으로.
        # addDialogDismissButtons는 dismiss 전용(닫기/취소 류)에만 쓰는 게 guiHelper 계약.
        if self._on_delete is not None:
            actionButtons = guiHelper.ButtonHelper(wx.HORIZONTAL)
            self.deleteBtn = actionButtons.addButton(self, label=_("선택 항목 삭제(&D)"))
            self.deleteBtn.Bind(wx.EVT_BUTTON, self._on_delete_button)
            sHelper.addItem(actionButtons)

        # dismiss 버튼(닫기)은 단일 버튼으로 addDialogDismissButtons에 전달.
        btnOk = wx.Button(self, id=wx.ID_OK, label=_("닫기"))
        btnOk.SetDefault()
        btnOk.Bind(wx.EVT_BUTTON, self._on_ok)
        sHelper.addDialogDismissButtons(btnOk)

        mainSizer = wx.BoxSizer(wx.VERTICAL)
        mainSizer.Add(sHelper.sizer, border=guiHelper.BORDER_FOR_DIALOGS, flag=wx.ALL)
        self.SetSizer(mainSizer)
        mainSizer.Fit(self)
        # Escape로 닫히도록 명시. NVDA 관례(LanguageRestartDialog)에 맞춰 프로퍼티 스타일.
        self.EscapeId = wx.ID_OK

    def _display_text(self, entry: str) -> str:
        scope = self._get_scope(entry)
        if scope == SCOPE_APP:
            return f"[앱] {entry}"
        appId, title = splitKey(entry)
        appLabel = appId if appId else "앱 미지정"
        return f"[창] {appLabel} | {title}"

    def _count_text(self) -> str:
        return _("총 %d개") % len(self._entries)

    def _selected_entries(self):
        """현재 선택된 entry 리스트 (원본 키)."""
        return [self._entries[i] for i in self.listBox.GetSelections()]

    def _on_listbox_key(self, event):
        if event.GetKeyCode() == wx.WXK_DELETE and self._on_delete is not None:
            self._delete_selected()
            return
        event.Skip()

    def _on_delete_button(self, event):
        self._delete_selected()

    def _delete_selected(self):
        selected = self._selected_entries()
        if not selected:
            # 빈 선택 상태에서 Delete/버튼 누름 — 무반응 대신 짧은 시스템 신호로 피드백
            wx.Bell()
            return

        # 앱 entry가 포함된 경우 일괄 삭제 확인
        app_entries = [e for e in selected if self._get_scope(e) == SCOPE_APP]
        cascade_targets = []  # 함께 삭제할 동일 appId 창 entry
        if app_entries:
            same_app_windows = [
                e for e in self._entries
                if e not in selected
                and self._get_scope(e) == SCOPE_WINDOW
                and splitKey(e)[0] in app_entries
            ]
            if same_app_windows:
                msg = _(
                    "선택한 앱 항목과 같은 앱의 창 항목 %d개가 함께 등록되어 있어요.\n"
                    "창 항목들도 같이 지울까요?"
                ) % len(same_app_windows)
                resp = wx.MessageBox(
                    msg,
                    _("앱 항목 삭제 확인"),
                    wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION,
                    self,
                )
                if resp == wx.CANCEL:
                    return
                if resp == wx.YES:
                    cascade_targets = same_app_windows

        targets = list(dict.fromkeys(selected + cascade_targets))  # 순서 보존 + 중복 제거

        if not self._on_delete(targets):
            wx.MessageBox(
                _("저장 중 문제가 생겨 삭제하지 못했어요."),
                _("오류"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        # 표시 갱신: 내부 entries에서 제거하고 다이얼로그는 열어둠.
        # 사용자가 여러 차례 정리할 수 있게 하는 NVDA 친화 UX.
        self._entries = [e for e in self._entries if e not in targets]
        self.listBox.Set([self._display_text(e) for e in self._entries])
        self.countLabel.SetLabel(self._count_text())
        # 모두 비었으면 자동으로 닫기
        if not self._entries:
            self.EndModal(wx.ID_OK)

    def _on_ok(self, event):
        self.EndModal(wx.ID_OK)
