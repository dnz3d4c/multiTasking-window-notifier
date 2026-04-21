# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""등록된 창/앱 목록을 보여주고 삭제/편집까지 처리하는 wx.Dialog.

기능:
    - scope 표시: `[앱] chrome` / `[창] chrome | YouTube ...`
    - 다중 선택(`wx.LB_EXTENDED`) + Delete 키/삭제 버튼으로 일괄 삭제
    - 앱 entry 삭제 시 "관련 창도 같이 지울까요?" 확인 다이얼로그
    - 실제 저장/lookup 갱신은 호출자가 주입한 on_delete 콜백 책임 (결합도 낮춤)
    - 표시 텍스트에 alias 꼬리표 `(대체: 대화창제목)` 추가 (alias 있을 때만)
    - "편집(&E)" 버튼 — 단일 선택 + on_edit_alias 콜백 주입 시에만 노출
    - 메타 조회 콜백 `get_meta(entry) -> dict`. 기존 호환용 `get_scope`도 여전히 수용.
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


# ---- wx 없이 단위 테스트 가능한 순수 함수 ----


def format_display_text(entry: str, scope: str, aliases=None) -> str:
    """ListBox 1줄 표시 텍스트. scope별 프리픽스 + 가독성 좋은 appId|title 포맷.

    scope=app은 entry 자체가 appId. scope=window는 splitKey로 분해. appId가
    비어 있는 구형 entry는 "앱 미지정" 라벨로 폴백 — wx 의존성 없이 단위
    테스트 가능하도록 module-level로 추출했다.

    aliases가 비어 있지 않으면 꼬리에 `(대체: a1, a2)`를 붙인다. UI 규약상
    alias는 1개만 저장하지만 포맷은 배열 전체 지원.
    """
    if scope == SCOPE_APP:
        base = f"[앱] {entry}"
    else:
        appId, title = splitKey(entry)
        appLabel = appId if appId else "앱 미지정"
        base = f"[창] {appLabel} | {title}"
    alias_list = [a for a in (aliases or []) if a]
    if alias_list:
        base += f" (대체: {', '.join(alias_list)})"
    return base


def format_count_text(n: int) -> str:
    """카운트 라벨 텍스트. 숫자만 있으면 확정 — wx 독립."""
    return _("총 %d개") % n


def compute_cascade_targets(selected, entries, get_scope):
    """앱 entry 선택 시 함께 삭제 후보가 되는 window entry 목록 계산.

    선택된 항목 중 scope=app인 것이 있으면, `_entries` 전체에서 해당 appId에
    속하는 window entry를 찾아 반환. 이미 selected에 들어있는 entry는 제외.
    `_delete_selected`의 cascade 판정 로직을 순수 함수로 분리했다.

    Args:
        selected: 사용자가 선택한 entry 리스트.
        entries: 현재 표시 중인 전체 entry 리스트(다이얼로그의 `_entries`).
        get_scope: callable(entry) -> scope. 메타 조회 콜백.

    Returns:
        list: cascade 대상 window entry. 앱 entry가 선택되지 않았으면 빈 리스트.
    """
    app_entries = [e for e in selected if get_scope(e) == SCOPE_APP]
    if not app_entries:
        return []
    return [
        e for e in entries
        if e not in selected
        and get_scope(e) == SCOPE_WINDOW
        and splitKey(e)[0] in app_entries
    ]


class AppListDialog(wx.Dialog):
    """등록된 창/앱 목록 다이얼로그.

    Args:
        parent: 부모 wx 창.
        appList: 등록된 entry 키 리스트 (순서 보존).
        get_meta: callable(entry) -> dict. GlobalPlugin._meta_for를 주입.
            반환 dict에서 `scope`와 `aliases`를 조회. 미존재 시 빈 dict 반환 가정.
        get_scope: (하위 호환) callable(entry) -> scope. get_meta 미주입 시 fallback.
        on_delete: callable(entries_to_remove: list[str]) -> bool. 저장 성공 여부 반환.
            None이면 삭제 UI 비활성화 (조회 전용).
        on_edit_alias: callable(entry: str) -> (True | False | None).
            편집 버튼을 노출할지 결정. None이면 편집 UI 비활성화.
            True=편집 성공(목록 갱신), False=저장 실패(에러 표시), None=사용자 취소.
    """

    def __init__(self, parent, appList, get_meta=None, get_scope=None,
                 on_delete=None, on_edit_alias=None):
        super().__init__(parent, title=_("등록된 창 목록"))
        self.appList = list(appList)
        # get_meta 우선, 없으면 get_scope를 어댑터로 감싸 dict로 승격.
        if get_meta is not None:
            self._get_meta = get_meta
        elif get_scope is not None:
            self._get_meta = lambda e: {"scope": get_scope(e), "aliases": []}
        else:
            self._get_meta = lambda e: {"scope": SCOPE_WINDOW, "aliases": []}
        self._on_delete = on_delete
        self._on_edit_alias = on_edit_alias
        # 표시 순서: scope 무관하게 표시 텍스트 정렬. 내부 entry 매핑은 _entries에 보관.
        self._entries = sorted(self.appList, key=lambda e: self._display_text(e).lower())
        self._create_ui()
        self.CenterOnScreen()

    def _get_scope(self, entry):
        """scope만 필요한 내부/테스트 호환 헬퍼. 기존 cascade 로직 등에서 사용."""
        return (self._get_meta(entry) or {}).get("scope", SCOPE_WINDOW)

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

        # "선택 항목 삭제"/"대체 제목 편집"은 다이얼로그를 닫지 않는 action 버튼이므로
        # addItem으로. addDialogDismissButtons는 dismiss 전용(닫기/취소 류)에만 쓰는 게
        # guiHelper 계약.
        if self._on_delete is not None or self._on_edit_alias is not None:
            actionButtons = guiHelper.ButtonHelper(wx.HORIZONTAL)
            if self._on_delete is not None:
                self.deleteBtn = actionButtons.addButton(self, label=_("선택 항목 삭제(&D)"))
                self.deleteBtn.Bind(wx.EVT_BUTTON, self._on_delete_button)
            if self._on_edit_alias is not None:
                self.editBtn = actionButtons.addButton(self, label=_("대체 제목 편집(&E)"))
                self.editBtn.Bind(wx.EVT_BUTTON, self._on_edit_button)
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
        meta = self._get_meta(entry) or {}
        return format_display_text(
            entry,
            meta.get("scope", SCOPE_WINDOW),
            aliases=meta.get("aliases") or [],
        )

    def _count_text(self) -> str:
        return format_count_text(len(self._entries))

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

    def _on_edit_button(self, event):
        self._edit_selected_alias()

    def _edit_selected_alias(self):
        """단일 선택 entry의 alias를 편집. 콜백이 저장/안내를 담당."""
        selected = self._selected_entries()
        if not selected:
            wx.Bell()
            return
        if len(selected) > 1:
            wx.MessageBox(
                _("대체 제목 편집은 한 번에 한 항목만 할 수 있어요."),
                _("안내"),
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return
        entry = selected[0]
        result = self._on_edit_alias(entry)
        if result is None:
            # 사용자 취소 — 아무 변경 없음
            return
        if result is False:
            wx.MessageBox(
                _("저장 중 문제가 생겨 대체 제목을 바꾸지 못했어요."),
                _("오류"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        # 성공 → 표시 텍스트 갱신 (alias 꼬리표 반영).
        idx = self._entries.index(entry)
        self.listBox.SetString(idx, self._display_text(entry))

    def _delete_selected(self):
        selected = self._selected_entries()
        if not selected:
            # 빈 선택 상태에서 Delete/버튼 누름 — 무반응 대신 짧은 시스템 신호로 피드백
            wx.Bell()
            return

        # 앱 entry가 포함된 경우 일괄 삭제 확인 (cascade 계산은 순수 함수 위임)
        cascade_targets = []  # 함께 삭제할 동일 appId 창 entry
        same_app_windows = compute_cascade_targets(
            selected, self._entries, self._get_scope
        )
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
