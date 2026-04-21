# -*- coding: utf-8 -*-
"""event_gainFocus 처리 시간 측정 (Non-goals 3.3 트리거 데이터).

NVDA는 모든 포커스 이동마다 event_gainFocus를 호출한다. 애드온의 dispatch
처리 시간이 길면 스크린 리더 응답성이 떨어지므로 상한을 assert로 박아 회귀를
막는다. 평균 1ms 기준은 현 구현의 예상 수치(<0.5ms)에 2x 여유. 이 상한을
넘기면 Non-goals 3.3(`requestEvents` 최적화)을 별도 Phase로 상승 검토.

p99는 Windows 백그라운드 노이즈(가상 메모리 스왑, 인덱싱 등) 대비로 경고만
남기고 assert하지 않는다. 평균만이 회귀 지표.
"""

from __future__ import annotations

import statistics
import sys
import time
import types
from unittest.mock import MagicMock

import pytest
from configobj import ConfigObj

from globalPlugins.multiTaskingWindowNotifier import (
    eventRouter,
    store,
)
from globalPlugins.multiTaskingWindowNotifier.constants import (
    ALT_TAB_HOST_FG_WCN,
    ALT_TAB_OVERLAY_WCN,
    SCOPE_WINDOW,
)


ITERATIONS = 100
AVG_THRESHOLD_MS = 1.0  # 평균 assert
P99_WARN_MS = 5.0       # p99 경고 (assert 안 함)


@pytest.fixture
def ready_plugin(monkeypatch, tmp_path):
    """등록 항목 + 비프/레코드 무음 처리된 GlobalPlugin."""
    from globalPlugins.multiTaskingWindowNotifier import settings, settingsPanel

    conf = ConfigObj()
    conf.spec = {}
    fake_config = types.ModuleType("config")
    fake_config.conf = conf
    monkeypatch.setattr(settings, "config", fake_config)
    monkeypatch.setattr(settingsPanel, "config", fake_config)
    sys.modules["globalVars"].appArgs.configPath = str(tmp_path)

    from globalPlugins.multiTaskingWindowNotifier import GlobalPlugin, beepPlayer

    plugin = GlobalPlugin()
    keys = ["notepad|제목 없음", "chrome|YouTube"]
    scopes = {k: SCOPE_WINDOW for k in keys}
    store.save(plugin.appListFile, keys, scopes=scopes)
    plugin.appList = list(keys)
    plugin._rebuild_lookup()

    # 비프/레코드/디버그 로그 전부 no-op
    monkeypatch.setattr(beepPlayer, "play_beep", lambda *a, **kw: None)
    monkeypatch.setattr(store, "record_switch", lambda *a, **kw: None)
    monkeypatch.setattr(eventRouter.settings, "get", lambda key: False)
    monkeypatch.setattr(eventRouter.tabClasses, "is_overlay_class", lambda a, w: False)
    monkeypatch.setattr(eventRouter.tabClasses, "is_editor_class", lambda a, w: False)

    return plugin


def _obj(window_class_name, name, hwnd, appName):
    o = MagicMock()
    o.windowClassName = window_class_name
    o.name = name
    o.windowHandle = hwnd
    o.appModule = MagicMock()
    o.appModule.appName = appName
    return o


def test_event_gain_focus_average_under_threshold(ready_plugin, monkeypatch):
    """100회 반복 평균 처리시간이 AVG_THRESHOLD_MS 미만.

    매 iteration마다 Matcher.last_event_signature를 None으로 리셋해 dedup으로 건너
    뛰는 빠른 경로가 평균을 과소평가하지 않도록 한다.
    """
    obj = _obj(ALT_TAB_OVERLAY_WCN, "제목 없음 - 메모장", 0xAAA, "chrome")
    foreground = _obj(ALT_TAB_HOST_FG_WCN, "작업 전환", 0xBBB, "explorer")
    monkeypatch.setattr(eventRouter.api, "getForegroundObject", lambda: foreground)

    # Warmup: 최초 호출의 JIT/import 비용 배제
    for _ in range(5):
        ready_plugin._matcher.last_event_signature = None
        eventRouter.dispatch_focus(ready_plugin, obj)

    latencies_ms = []
    for _ in range(ITERATIONS):
        ready_plugin._matcher.last_event_signature = None
        t0 = time.perf_counter()
        eventRouter.dispatch_focus(ready_plugin, obj)
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)

    avg = statistics.mean(latencies_ms)
    median = statistics.median(latencies_ms)
    p99 = sorted(latencies_ms)[int(ITERATIONS * 0.99)]

    # 실측 수치는 항상 로그로 노출 — Non-goals 3.3 재판정용 데이터 확보
    print(
        f"\n[perf] event_gainFocus dispatch "
        f"avg={avg:.3f}ms median={median:.3f}ms p99={p99:.3f}ms n={ITERATIONS}"
    )

    if p99 > P99_WARN_MS:
        # flaky 대비: assert 대신 경고만. 평균이 기준 밑이면 OK로 간주.
        print(f"[perf WARN] p99 {p99:.3f}ms > {P99_WARN_MS}ms — background noise 가능성")

    assert avg < AVG_THRESHOLD_MS, (
        f"dispatch avg {avg:.3f}ms >= {AVG_THRESHOLD_MS}ms — "
        f"성능 회귀. IMPROVEMENTS.md Non-goals 3.3 requestEvents 재판정 필요."
    )


def test_match_and_beep_hot_path_under_threshold(ready_plugin):
    """Matcher.match_and_beep 자체의 핫 패스 평균 시간.

    dispatch는 3분기 판정 오버헤드가 있어 matcher 순수 매칭 성능을 별도로
    측정한다. 등록 항목 2개 + window_lookup 히트 케이스.
    """
    for _ in range(5):
        ready_plugin._matcher.last_event_signature = None
        ready_plugin._match_and_beep("notepad", "제목 없음", tab_signature=0xAAA)

    latencies_ms = []
    for _ in range(ITERATIONS):
        ready_plugin._matcher.last_event_signature = None
        t0 = time.perf_counter()
        ready_plugin._match_and_beep("notepad", "제목 없음", tab_signature=0xAAA)
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)

    avg = statistics.mean(latencies_ms)
    print(f"\n[perf] match_and_beep avg={avg:.3f}ms n={ITERATIONS}")

    assert avg < AVG_THRESHOLD_MS, (
        f"match_and_beep avg {avg:.3f}ms >= {AVG_THRESHOLD_MS}ms — 매칭 핫 패스 회귀."
    )
