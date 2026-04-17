# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""wxPython GUI (다이얼로그)."""

import wx

from .appIdentity import splitKey

# 번역 초기화(선택)
try:
    import addonHandler
    addonHandler.initTranslation()
    _  # noqa: F401
except Exception:
    def _(s):
        return s


class AppListDialog(wx.Dialog):
    """등록된 창 목록을 보여주는 다이얼로그."""

    def __init__(self, parent, appList):
        super().__init__(parent, title=_("등록된 창 목록"))
        self.appList = appList
        self._create_ui()
        self.CenterOnScreen()

    def _create_ui(self):
        panel = wx.Panel(self)
        mainSizer = wx.BoxSizer(wx.VERTICAL)

        total = len(self.appList)
        countLabel = wx.StaticText(panel, label=f"총 {total}개")
        mainSizer.Add(countLabel, flag=wx.ALL, border=10)

        entries_sorted = sorted(self.appList, key=lambda s: self._display_text(s).lower())
        display_items = [self._display_text(e) for e in entries_sorted]

        self.listBox = wx.ListBox(
            panel,
            choices=display_items,
            style=wx.LB_SINGLE | wx.LB_HSCROLL,
            size=(500, 300),
        )
        mainSizer.Add(self.listBox, proportion=1, flag=wx.ALL | wx.EXPAND, border=10)

        btnOk = wx.Button(panel, wx.ID_OK, _("확인"))
        btnOk.SetDefault()
        btnOk.Bind(wx.EVT_BUTTON, self.on_ok)
        mainSizer.Add(btnOk, flag=wx.ALL | wx.ALIGN_CENTER, border=10)

        panel.SetSizer(mainSizer)
        mainSizer.Fit(self)

    def _display_text(self, entry: str) -> str:
        appId, title = splitKey(entry)
        appLabel = appId if appId else "앱 미지정"
        return f"{appLabel} | {title}"

    def on_ok(self, event):
        self.EndModal(wx.ID_OK)
