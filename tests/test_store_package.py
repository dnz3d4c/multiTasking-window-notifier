# -*- coding: utf-8 -*-
"""store/ 서브패키지 스캐폴딩 smoke 테스트.

Phase 3.1: 빈 패키지가 import 가능한지만 확인한다. 후속 커밋(3-2~3-7)에서
실제 모듈/함수가 이관되면 이 파일에 추가 smoke 단언을 덧붙인다.
"""

from __future__ import annotations


def test_store_package_importable():
    from globalPlugins.multiTaskingWindowNotifier import store

    assert store is not None


def test_store_package_has_docstring():
    """공개 패키지는 문서 문자열이 있어야 후속 단계에서 구조 설명이 남는다."""
    from globalPlugins.multiTaskingWindowNotifier import store

    assert store.__doc__ is not None
    assert "store" in store.__doc__.lower()
