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

from . import beepPlayer, settings
from .constants import ADDON_NAME
from .presets import CLASSIC_PRESET_ID, PRESETS

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
# Phase 6: beepVolume 슬라이더 범위. CONFSPEC과 동일.
VOLUME_MIN, VOLUME_MAX = 50, 150

# 프리셋 type → 사용자 노출 카테고리 레이블. ListBox 항목 접두사로 사용.
# Phase 7.4: percussive/atonal 라인업(synthSpecs 5종)이 철회되면서 엔트리 축소.
# 현재 프리셋은 전부 tonal/hybrid이며, 신규 프리셋도 이 두 type만 허용.
_TYPE_CATEGORY_LABELS = {
    "tonal": _("음계"),
    "hybrid": _("혼합"),
}


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(value)))


def _format_preset_label(preset: dict) -> str:
    """ListBox 한 줄에 표시되는 프리셋 레이블 생성.

    포맷: "[카테고리] 이름 — N slots"
    이모지 사용 안 함 — NVDA TTS 엔진별로 이모지 처리가 다르고 소음 유발.

    Phase 7.4에서 옵트인 프리셋(humor_pack)이 철회되며 " (옵트인)" 접미사 경로
    제거. optIn 플래그는 dict에 잔존하지만 현재 모든 프리셋이 False이며, 향후
    재도입 시 본 함수와 onSave를 함께 복원해야 한다.
    """
    category = _TYPE_CATEGORY_LABELS.get(preset["type"], preset["type"])
    name = _(preset["nameLabel"])
    slots = preset["slotCount"]
    return f"[{category}] {name} — {slots} slots"


def _ordered_preset_ids():
    """ListBox 항목 순서. PRESETS의 dict 삽입 순서를 그대로 쓴다.

    Python 3.7+는 dict 순서 보존이 보장되고 `presets.PRESETS`는 사용자 경험에
    맞춰 classic→pentatonic→fifths→soft_retro→moss_bell 순으로 정의돼 있다.
    따라서 list(PRESETS) 만으로 표시 순서가 일관된다.
    """
    return list(PRESETS.keys())


class MultiTaskingSettingsPanel(SettingsPanel):
    """NVDA 설정 > 창 전환 알림 패널."""

    # Translators: 설정 대화상자의 카테고리 제목.
    title = _("창 전환 알림")

    def makeSettings(self, settingsSizer):
        conf = config.conf[ADDON_NAME]
        sHelper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)

        # 프리셋 ListBox + 설명 라벨 + "미리듣기"/"기본값" 버튼 세트.
        # 현재 선택 프리셋이 변경되면 설명 라벨(StaticText)이 갱신되고,
        # 미리듣기 버튼은 그 선택의 previewSlots를 바로 재생해 사용자가 저장 전에
        # 소리를 확인할 수 있게 한다.
        self._preset_ids = _ordered_preset_ids()
        # Translators: 프리셋 ListBox 라벨.
        self.presetList = sHelper.addLabeledControl(
            _("비프 프리셋 (&L):"),
            wx.ListBox,
            choices=[_format_preset_label(PRESETS[pid]) for pid in self._preset_ids],
            style=wx.LB_SINGLE,
        )
        # settings.get이 CONFSPEC default로 폴백까지 담당하므로 여기서는 조회 결과를
        # 그대로 신뢰한다. 혹시 사용자가 수동 편집으로 미지 id를 넣었으면 ListBox에
        # 대응 항목이 없어 아래 in 검사에서 classic으로 재정렬된다.
        current_preset_id = settings.get("beepPreset")
        if current_preset_id not in self._preset_ids:
            current_preset_id = CLASSIC_PRESET_ID
        self.presetList.SetSelection(self._preset_ids.index(current_preset_id))

        # 프리셋 설명 라벨. focus 변경 시 descriptionLabel로 갱신.
        self._presetDescription = wx.StaticText(
            self,
            label=_(PRESETS[current_preset_id]["descriptionLabel"]),
        )
        sHelper.addItem(self._presetDescription)
        self.presetList.Bind(wx.EVT_LISTBOX, self._onPresetChanged)

        # "미리듣기"/"기본값" 버튼 한 줄 배치.
        btnRow = wx.BoxSizer(wx.HORIZONTAL)
        # Translators: 선택한 프리셋의 대표 슬롯 2개를 현장 재생하는 버튼.
        self._previewBtn = wx.Button(self, label=_("미리듣기(&P)"))
        self._previewBtn.Bind(wx.EVT_BUTTON, self._onPreviewClicked)
        btnRow.Add(self._previewBtn, 0, wx.RIGHT, 8)
        # Translators: 프리셋 선택을 Classic Tones(현행 기본)로 되돌리는 버튼.
        self._defaultBtn = wx.Button(self, label=_("기본값(&D)"))
        self._defaultBtn.Bind(wx.EVT_BUTTON, self._onDefaultClicked)
        btnRow.Add(self._defaultBtn, 0)
        sHelper.addItem(btnRow)

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

        # Phase 6: 비프 볼륨 슬라이더. 50~150% 범위로 hybrid 프리셋(waveform 메타
        # 지정 → nvwave 경로) 볼륨을 사용자가 직접 조정. classic/pentatonic/fifths
        # (tones.beep 경로)는 NVDA 내부 볼륨 체계를 쓰므로 영향 받지 않는다.
        # Translators: 비프 볼륨 슬라이더 라벨. 단위는 %. 범위 50~150.
        self.volumeSlider = sHelper.addLabeledControl(
            _("비프 볼륨 (%):"),
            wx.Slider,
            minValue=VOLUME_MIN, maxValue=VOLUME_MAX,
            value=_clamp(conf["beepVolume"], VOLUME_MIN, VOLUME_MAX),
            style=wx.SL_HORIZONTAL | wx.SL_VALUE_LABEL,
        )

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
        volume = _clamp(self.volumeSlider.GetValue(), VOLUME_MIN, VOLUME_MAX)

        conf = config.conf[ADDON_NAME]
        conf["beepDuration"] = duration
        conf["beepGapMs"] = gap_ms
        conf["beepVolume"] = volume
        conf["debugLogging"] = self.debugLoggingCheck.IsChecked()
        # 프리셋 선택 저장. ListBox 미선택(-1) 방어 — 사용자가 전체 해제한 경우
        # classic 폴백(체감 회귀 없음).
        sel = self.presetList.GetSelection()
        if 0 <= sel < len(self._preset_ids):
            new_preset = self._preset_ids[sel]
        else:
            new_preset = CLASSIC_PRESET_ID
        conf["beepPreset"] = new_preset

    # ------------------------------------------------------------------
    # 프리셋 ListBox 이벤트
    # ------------------------------------------------------------------

    def _current_preset_id(self) -> str:
        sel = self.presetList.GetSelection()
        if 0 <= sel < len(self._preset_ids):
            return self._preset_ids[sel]
        return CLASSIC_PRESET_ID

    def _onPresetChanged(self, event):
        """ListBox 선택이 바뀌면 설명 라벨을 갱신."""
        preset_id = self._current_preset_id()
        preset = PRESETS.get(preset_id, PRESETS[CLASSIC_PRESET_ID])
        self._presetDescription.SetLabel(_(preset["descriptionLabel"]))
        # 라벨 길이 변화에 맞춰 레이아웃 재계산. 재발화 스팸을 피하려
        # descriptionLabel은 LabelValue로 교체하지 않고 SetLabel만 사용.
        self._presetDescription.GetParent().Layout()

    def _onPreviewClicked(self, event):
        """현재 선택 프리셋의 previewSlots 2음을 현재 SpinCtrl/Slider 값으로 재생.

        패널을 열고 duration/gap/volume을 수정한 상태(아직 onSave 전)에서도 조정한
        값 그대로 들려줘야 "원하는 타이밍/볼륨인지" 확인 가능하므로 현재 위젯 값을
        직접 전달한다. settings(config.conf) 값을 읽으면 저장된 이전 값으로 재생돼
        사용자 의도 벗어남.
        """
        duration = _clamp(self.durationSpin.GetValue(), DURATION_MIN, DURATION_MAX)
        gap_ms = _clamp(self.gapSpin.GetValue(), GAP_MIN, GAP_MAX)
        volume = _clamp(self.volumeSlider.GetValue(), VOLUME_MIN, VOLUME_MAX)
        beepPlayer.play_preview(self._current_preset_id(), duration, gap_ms, volume)

    def _onDefaultClicked(self, event):
        """프리셋 선택을 Classic Tones로 되돌린다. 즉시 저장되진 않고 onSave에서 반영."""
        if CLASSIC_PRESET_ID in self._preset_ids:
            self.presetList.SetSelection(self._preset_ids.index(CLASSIC_PRESET_ID))
            self._onPresetChanged(None)
