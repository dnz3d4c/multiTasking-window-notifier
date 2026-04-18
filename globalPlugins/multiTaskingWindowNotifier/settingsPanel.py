# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""NVDA 설정 대화상자의 "창 전환 알림" 패널.

스키마는 `settings.py`(Phase 1)의 CONFSPEC을 따른다. 본 모듈은 UI 레이어로,
사용자 대면 문자열만 담당하며 스키마/값 검증은 `config.conf.spec`에 위임한다.

NVDA 설정 등록/해제는 `__init__.py`의 `GlobalPlugin.__init__/terminate`에서
`gui.settingsDialogs.NVDASettingsDialog.categoryClasses`에 add/remove로 수행.

접근성 설계 결정:
    - SpinCtrl 라벨은 핵심 이름만 담고, 범위/의미 설명은 별도 StaticText로 분리한다.
      스크린리더가 컨트롤 진입 시 긴 라벨을 매번 낭독하는 부담을 줄이기 위함.
    - `onSave`는 SpinCtrl의 수동 입력 경로(Ctrl+A 후 직접 타이핑 등)가 범위를 넘길
      가능성을 차단하기 위해 명시적으로 clamp해서 저장한다.
"""

import wx

import config
from gui import guiHelper
from gui.settingsDialogs import SettingsPanel

from .constants import ADDON_NAME

# 번역 초기화(선택). NVDA 외 환경(유닛 테스트 등)에서 _를 정의해두는 폴백.
try:
    import addonHandler
    addonHandler.initTranslation()
    _  # noqa: F401
except Exception:
    def _(s):
        return s


# SpinCtrl의 min/max와 onSave의 clamp 양쪽에서 공용으로 쓰는 상수.
DURATION_MIN, DURATION_MAX = 20, 500
GAP_MIN, GAP_MAX = 0, 200


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(value)))


class MultiTaskingSettingsPanel(SettingsPanel):
    """NVDA 설정 > 창 전환 알림 패널."""

    # Translators: 설정 대화상자의 카테고리 제목.
    title = _("창 전환 알림")

    def makeSettings(self, settingsSizer):
        conf = config.conf[ADDON_NAME]
        sHelper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)

        # Translators: 비프음 길이 SpinCtrl 라벨. 단위는 밀리초. 범위 20~500.
        self.durationSpin = sHelper.addLabeledControl(
            _("비프음 길이 (밀리초):"),
            wx.SpinCtrl,
            min=DURATION_MIN, max=DURATION_MAX,
            initial=_clamp(conf["beepDuration"], DURATION_MIN, DURATION_MAX),
        )

        # Translators: 앱 비프와 탭 비프 사이 간격 SpinCtrl 라벨. 단위는 밀리초.
        self.gapSpin = sHelper.addLabeledControl(
            _("탭 비프 간격 (밀리초):"),
            wx.SpinCtrl,
            min=GAP_MIN, max=GAP_MAX,
            initial=_clamp(conf["beepGapMs"], GAP_MIN, GAP_MAX),
        )

        # Translators: 탭 비프 간격 SpinCtrl 아래의 도움말.
        gapHelp = wx.StaticText(
            self,
            label=_(
                "창으로 등록한 항목은 앱 비프음이 울린 뒤 이 간격만큼 쉬고 탭 비프음이 "
                "이어서 울립니다. 0으로 두면 두 음이 거의 붙어 들립니다."
            ),
        )
        sHelper.addItem(gapHelp)

        # Translators: 진단 로그 체크박스 라벨. 평상시엔 끄고, 문제 추적 시에만 사용.
        self.debugLoggingCheck = sHelper.addItem(
            wx.CheckBox(self, label=_("진단 로그 기록 (문제 추적용)"))
        )
        self.debugLoggingCheck.SetValue(bool(conf["debugLogging"]))

        # Translators: 진단 로그 체크박스 아래의 보조 설명.
        debugHelp = wx.StaticText(
            self,
            label=_(
                "이 옵션을 켜면 포커스가 바뀔 때마다 창 정보가 NVDA 로그 파일에 기록됩니다. "
                "Ctrl+Tab 등에서 비프가 나지 않는 원인을 추적할 때만 잠시 켜고, 평소에는 꺼 두세요."
            ),
        )
        sHelper.addItem(debugHelp)

    def onSave(self):
        # SpinCtrl의 수동 입력 경로(Ctrl+A 후 타이핑 등)가 범위를 넘길 수 있어
        # 쓰기 시점에 명시적으로 clamp한다. configobj의 validate는 읽기 시점
        # 적용이라 쓰기에서는 자동 보호가 없다.
        duration = _clamp(self.durationSpin.GetValue(), DURATION_MIN, DURATION_MAX)
        gap_ms = _clamp(self.gapSpin.GetValue(), GAP_MIN, GAP_MAX)

        conf = config.conf[ADDON_NAME]
        conf["beepDuration"] = duration
        conf["beepGapMs"] = gap_ms
        conf["debugLogging"] = self.debugLoggingCheck.IsChecked()
