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


def test_store_public_api_reexported():
    """Phase 3.7 이후 appListStore.py 제거됨. 공개 API는 `store` 패키지로만 접근.

    11개 공개 API가 모두 재export돼 있어야 기존 호출부 + 외부 스크립트 호환.
    """
    from globalPlugins.multiTaskingWindowNotifier import store

    expected = {
        "load", "save", "record_switch", "flush", "reload",
        "is_corrupted", "get_meta", "get_app_beep_idx", "get_tab_beep_idx",
        "prune_stale", "reset_cache",
    }
    missing = expected - set(dir(store))
    assert not missing, f"missing public API: {missing}"


def test_appliststore_module_removed():
    """Phase 3.7: appListStore.py는 삭제됐어야 한다. shim 유지 금지 원칙."""
    import importlib

    try:
        importlib.import_module(
            "globalPlugins.multiTaskingWindowNotifier.appListStore"
        )
    except ModuleNotFoundError as e:
        # 메시지에 appListStore가 포함되는지 확인 — 부모 패키지 초기화 실패로
        # 잘못된 이유의 ModuleNotFoundError가 나는 경우를 배제한다.
        assert "appListStore" in str(e), f"unexpected import error: {e}"
        return
    raise AssertionError("appListStore 모듈이 아직 import 가능함 — shim 남아있는지 확인")
