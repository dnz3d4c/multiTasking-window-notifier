# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""창 전환 카운트 디바운스 flush 스케줄러.

event_gainFocus / event_nameChange 매칭이 성공할 때마다 switchCount가
메모리에서 올라가지만, 디스크 I/O는 N회 또는 T초 경과 시에만 몰아서 처리한다.
핫 패스(포커스 이벤트)에서 파일 쓰기를 분리하는 역할.

GlobalPlugin은 인스턴스를 하나 보유해 notify_switch() / maybe_flush() 두 호출로
사용하고, reload 스크립트는 reset()으로 카운터/타이머를 초기화한다.
"""

from __future__ import annotations

import time

from logHandler import log


# 기본 디바운스 임계치. GlobalPlugin이 필요 시 생성자 kwargs로 조정.
DEFAULT_FLUSH_EVERY_N = 10
DEFAULT_FLUSH_INTERVAL_SEC = 30


class FlushScheduler:
    """전환 카운트 디바운스 flush 담당.

    Args:
        flush_fn: `flush(app_list_file)` 시그니처 callable. 보통 `appListStore.flush`.
        app_list_file: flush 대상 app.json 경로.
        every_n: 이 횟수만큼 전환이 누적되면 즉시 flush.
        interval_sec: 누적 수와 무관하게 이 초가 경과했으면 flush.
    """

    def __init__(
        self,
        flush_fn,
        app_list_file: str,
        *,
        every_n: int = DEFAULT_FLUSH_EVERY_N,
        interval_sec: int = DEFAULT_FLUSH_INTERVAL_SEC,
    ):
        self._flush_fn = flush_fn
        self._app_list_file = app_list_file
        self._every_n = every_n
        self._interval_sec = interval_sec
        self._last_flush_at = time.monotonic()
        self._pending = 0

    def notify_switch(self) -> None:
        """매칭 성공 1회 = 미저장 전환 카운트 +1."""
        self._pending += 1

    def maybe_flush(self) -> None:
        """임계치 충족 시 디스크 반영. 실패해도 이벤트 체인을 막지 않도록 예외 흡수."""
        now = time.monotonic()
        if (
            self._pending >= self._every_n
            or (now - self._last_flush_at) >= self._interval_sec
        ):
            try:
                self._flush_fn(self._app_list_file)
            except Exception:
                log.exception("mtwn: switch flush failed")
            self._last_flush_at = now
            self._pending = 0

    def reset(self) -> None:
        """reload 후 카운터/타이머 초기화."""
        self._last_flush_at = time.monotonic()
        self._pending = 0
