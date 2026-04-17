#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""multiTaskingWindowNotifier 애드온 패키징 스크립트.

manifest.ini + globalPlugins/ 디렉토리를 .nvda-addon(zip)으로 묶는다.
수동 복사 설치 중 구조가 뒤바뀌어 발생한 패널 미표시/비프 회귀를
구조적으로 차단하기 위해 도입.

사용:
    uv run python build.py

산출물:
    multiTaskingWindowNotifier-<version>.nvda-addon
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "manifest.ini"

EXCLUDE_DIR_NAMES = {"__pycache__", ".pytest_cache", ".venv", "venv", ".git", "tests"}
EXCLUDE_FILE_SUFFIXES = {".pyc", ".pyo", ".pyd"}
# 런타임 사용자 데이터. 배포 패키지에 포함하면 설치 시 다른 사용자의 데이터가
# 덮어씌워지거나 예상치 못한 마이그레이션이 일어난다.
EXCLUDE_FILE_NAMES = {"app.list", "app.list.bak", "app.json", "app.json.tmp"}


def read_version() -> str:
    if not MANIFEST.exists():
        sys.exit("manifest.ini를 찾을 수 없다. 프로젝트 루트에서 실행하라.")
    text = MANIFEST.read_text(encoding="utf-8")
    m = re.search(r"^\s*version\s*=\s*(.+?)\s*$", text, re.MULTILINE)
    if not m:
        sys.exit("manifest.ini에 version 필드가 없다.")
    return m.group(1).strip().strip('"').strip("'")


def iter_payload_files(root: Path):
    """애드온 zip에 담을 파일만 골라 yield (absolute_path, arcname)."""
    yield MANIFEST, MANIFEST.name

    globalPlugins = root / "globalPlugins"
    if not globalPlugins.is_dir():
        sys.exit("globalPlugins 디렉토리가 없다. 리포 구조를 확인하라.")

    for path in globalPlugins.rglob("*"):
        if path.is_dir():
            continue
        if any(part in EXCLUDE_DIR_NAMES for part in path.parts):
            continue
        if path.suffix in EXCLUDE_FILE_SUFFIXES:
            continue
        if path.name in EXCLUDE_FILE_NAMES:
            continue
        yield path, str(path.relative_to(root)).replace("\\", "/")


def build() -> Path:
    version = read_version()
    out = ROOT / f"multiTaskingWindowNotifier-{version}.nvda-addon"
    if out.exists():
        out.unlink()

    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for src, arc in iter_payload_files(ROOT):
            zf.write(src, arc)
            count += 1

    size_kb = out.stat().st_size / 1024
    print(f"OK: {out.name}  ({count} files, {size_kb:.1f} KB)")
    return out


if __name__ == "__main__":
    build()
