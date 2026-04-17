# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""app.list 파일 I/O 전담."""

import os

import ui
from logHandler import log

from .constants import MAX_ITEMS


def load(path: str) -> list:
    """app.list 파일을 읽어 최대 MAX_ITEMS개까지 반환."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            items = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        items = []
    except Exception as e:
        log.error(f"app.list 로드 실패: {path}", exc_info=True)
        ui.message(f"앱 목록을 여는 중 문제가 생겼어요: {e}")
        items = []
    return items[:MAX_ITEMS]


def save(path: str, items: list) -> None:
    """app.list 파일에 항목을 기록 (최대 MAX_ITEMS)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            for t in items[:MAX_ITEMS]:
                f.write(f"{t}\n")
    except Exception as e:
        log.error(f"app.list 저장 실패: {path}", exc_info=True)
        ui.message(f"앱 목록을 저장하는 중 문제가 생겼어요: {e}")
