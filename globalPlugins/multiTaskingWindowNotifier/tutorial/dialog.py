# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""튜토리얼 위저드 다이얼로그.

wx.Wizard 대신 wx.Dialog + Panel swap 방식.
이유: wx.Wizard는 페이지 교체 시점에 NVDA 포커스 낭독 순서가 어긋난 이력 —
Panel을 직접 교체하면서 단계 전환마다 명시적으로 SetFocus + ui.message를
호출해 낭독 타이밍을 제어한다.

단계 전환 책임 분리:
    - 무엇을 그릴지: tutorial.steps 각 빌더
    - 언제 교체/어디에 포커스: 본 클래스

한 다이얼로그 당 한 번만 ShowModal 호출. on_finish 콜백은 종료 직전에 한 번
호출되며 kind 인자로 종료 경로 구분("completed" | "skipped" | "try_now").
mark_tutorial_shown은 모든 종료 경로에서 자동 호출.

진행률 표시("{cur}/{total}단계: {name}")는 STEPS 리스트 길이를 동적으로 참조.
단계 추가/삭제는 steps.py의 STEPS만 수정하면 본 클래스는 자동 적용.
"""

import wx
import ui
import speech
from gui import guiHelper

from .state import mark_tutorial_shown
from .steps import STEPS, TITLES

# 번역 초기화(선택). NVDA 외 환경에서 _를 정의해두는 폴백.
try:
    import addonHandler
    addonHandler.initTranslation()
    _  # noqa: F401
except Exception:
    def _(s):
        return s


# "닫고 지금 해보기" 클릭 시 EndModal 반환 ID — 사용자 정의.
# wx.ID_OK/ID_CANCEL과 겹치지 않는 값으로.
ID_TRY_NOW = wx.NewIdRef()


class TutorialDialog(wx.Dialog):
    """단계별 위저드. 이전/다음/건너뛰기 3버튼 + 단계별 Panel 교체.

    Args:
        parent: 부모 창 (보통 gui.mainFrame).
        context: 빌더에 전달할 공유 데이터 dict. finish 키는 본 클래스가 주입.
        on_finish: callable(kind: str) -> None | None.
            "completed"(마지막 완료) / "skipped"(건너뛰기·Escape·X) / "try_now"(닫고 해보기).
            예외는 내부에서 삼켜 종료 흐름을 막지 않는다.
    """

    def __init__(self, parent, context: dict, on_finish=None):
        super().__init__(parent, title=_("창 전환 알림 — 튜토리얼"))
        self._context = dict(context or {})
        # 빌더가 request_finish("try_now") 식으로 종료를 요청할 수 있도록 주입.
        self._context["finish"] = self.request_finish
        self._on_finish = on_finish
        self._idx = 0
        self._finalized = False  # 종료 경로 이중 호출 방어
        self._create_ui()
        self._show_step(0)
        self.CenterOnScreen()

    # ------------------------------------------------------------------
    # UI 구성
    # ------------------------------------------------------------------

    def _create_ui(self):
        sHelper = guiHelper.BoxSizerHelper(self, orientation=wx.VERTICAL)

        # 제목 라벨: "튜토리얼 — 2/N단계: 비프음 들어보기" 형식.
        # N은 STEPS 리스트 길이로 동적 결정. 단계 전환마다 SetLabel로 갱신.
        self._titleLabel = wx.StaticText(self, label="")
        sHelper.addItem(self._titleLabel)

        # 단계별 콘텐츠가 들어갈 container Panel.
        # DestroyChildren + 새 sizer로 매 단계 교체된다.
        self._contentPanel = wx.Panel(self)
        self._contentPanel.SetMinSize((560, 300))
        sHelper.addItem(self._contentPanel, flag=wx.EXPAND, proportion=1)

        # 이전 / 다음·완료 / 건너뛰기 버튼 한 줄.
        btns = guiHelper.ButtonHelper(wx.HORIZONTAL)
        # Translators: 이전 단계로 이동. &P는 액셀러레이터.
        self._prevBtn = btns.addButton(self, label=_("이전(&P)"))
        self._prevBtn.Bind(wx.EVT_BUTTON, lambda e: self._go(-1))
        # Translators: 다음 단계로 이동 또는 마지막에서 완료.
        self._nextBtn = btns.addButton(self, label=_("다음(&N)"))
        self._nextBtn.Bind(wx.EVT_BUTTON, lambda e: self._go(+1))
        # Translators: 튜토리얼을 중단. Escape와 동일.
        self._skipBtn = btns.addButton(self, label=_("건너뛰기(&S)"))
        self._skipBtn.Bind(wx.EVT_BUTTON, lambda e: self.request_finish("skipped"))
        sHelper.addItem(btns)

        mainSizer = wx.BoxSizer(wx.VERTICAL)
        mainSizer.Add(
            sHelper.sizer,
            flag=wx.ALL | wx.EXPAND,
            border=guiHelper.BORDER_FOR_DIALOGS,
            proportion=1,
        )
        self.SetSizerAndFit(mainSizer)

        # Escape = 건너뛰기, 타이틀바 X = 건너뛰기.
        self.EscapeId = wx.ID_CANCEL
        self.Bind(wx.EVT_CLOSE, lambda e: self.request_finish("skipped"))

    # ------------------------------------------------------------------
    # 단계 전환
    # ------------------------------------------------------------------

    def _show_step(self, idx: int) -> None:
        """idx 단계의 Panel 콘텐츠를 그리고 포커스·낭독을 재설정."""
        # 기존 자식 정리 + 기존 sizer 분리 (panel은 유지).
        self._contentPanel.DestroyChildren()
        self._contentPanel.SetSizer(None, deleteOld=False)

        step_id, builder = STEPS[idx]
        builder(self._contentPanel, self._context)
        self._contentPanel.Layout()

        # 제목 갱신 (진행률 포함). ui.message로 명시 낭독 — 포커스 이동만으로는
        # 제목 라벨이 낭독되지 않는 환경이 있어 안전하게 중복 쏜다.
        total = len(STEPS)
        title = _("튜토리얼 — {cur}/{total}단계: {name}").format(
            cur=idx + 1, total=total, name=TITLES[step_id],
        )
        self._titleLabel.SetLabel(title)

        # 버튼 활성/라벨 갱신.
        self._prevBtn.Enable(idx > 0)
        is_last = idx == total - 1
        # Translators: 마지막 단계의 다음 버튼 라벨.
        self._nextBtn.SetLabel(_("완료(&N)") if is_last else _("다음(&N)"))
        self._nextBtn.SetDefault()

        # 레이아웃 재계산. 단계마다 콘텐츠 크기가 달라 창 크기도 조정.
        self.Layout()
        self.Fit()

        # 낭독 순서: 제목(ui.message) → focusable 자식 포커스 → NVDA 자동 낭독.
        # ui.message를 SetFocus 앞에 둬 speech queue에 title이 먼저 들어가고,
        # 이어지는 포커스 이벤트 낭독이 뒤에 붙는다. 반대로 SetFocus가 먼저면
        # 포커스 이벤트가 speech를 선점해 "컨트롤 → 제목" 역순이 될 수 있다.
        # Spri.NEXT는 기존 낭독을 끊지 않고 뒤에 이어붙인다.
        ui.message(title, speechPriority=speech.Spri.NEXT)

        # 포커스 타깃: 첫 focusable 자식. 각 빌더가 설명 readonly TextCtrl을
        # 가장 먼저 얹으므로 정상 경로에선 이 TextCtrl이 선정된다 — 사용자는
        # 자동으로 설명 낭독을 듣고 화살표로 줄 단위 탐색 가능. panel 렌더가
        # 실패해 자식이 없을 때만 titleLabel(StaticText) 폴백 — SetFocus는
        # 실질 무시되지만 다이얼로그 포커스가 표류하지 않도록 안전망.
        children = self._contentPanel.GetChildren()
        focusable = next((c for c in children if c.AcceptsFocus()), None)
        if focusable is not None:
            focusable.SetFocus()
        else:
            self._titleLabel.SetFocus()

    def _go(self, delta: int) -> None:
        """delta=+1이면 다음 단계(마지막이면 완료), -1이면 이전 단계."""
        new_idx = self._idx + delta
        if new_idx < 0:
            wx.Bell()
            return
        if new_idx >= len(STEPS):
            self.request_finish("completed")
            return
        self._idx = new_idx
        self._show_step(new_idx)

    # ------------------------------------------------------------------
    # 종료 경로
    # ------------------------------------------------------------------

    def request_finish(self, kind: str) -> None:
        """종료 요청. 빌더(Step 6 "닫고 해보기")에서 호출 가능.

        모든 종료 경로는 여기로 수렴해 mark_tutorial_shown 1회 호출을 보장.
        EVT_CLOSE(창 X), EscapeId(Escape), 건너뛰기 버튼, 완료 버튼, 빌더 요청
        5경로 모두 통합. 이중 호출 방어는 _finalized 플래그로.
        """
        if self._finalized:
            return
        self._finalized = True

        try:
            mark_tutorial_shown()
        except Exception:
            # state.mark_tutorial_shown 자체가 예외 흡수하므로 여기 도달할 가능성
            # 낮음. 만약 도달하면 종료 자체는 진행해야 함.
            pass

        if self._on_finish:
            try:
                self._on_finish(kind)
            except Exception:
                # 콜백 오류가 다이얼로그 종료를 막으면 창이 잠겨 사용자가 갇힌다.
                # 조용히 무시하고 EndModal 진행.
                pass

        # kind에 따라 EndModal 반환 값 구분. 호출자가 구분 필요 시 활용 가능.
        if kind == "try_now":
            modal_id = ID_TRY_NOW
        elif kind == "completed":
            modal_id = wx.ID_OK
        else:
            modal_id = wx.ID_CANCEL

        if self.IsModal():
            self.EndModal(modal_id)
        else:
            self.Destroy()
