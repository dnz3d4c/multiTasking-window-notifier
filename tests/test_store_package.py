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
    """Phase R3 이후 공개 API 9개 + 내부 유틸 1개(reset_cache) 구조.

    런타임 코드가 실제 쓰는 9개만 __all__에 노출. reset_cache는 테스트 전용
    유틸로 재export는 유지하되 `from store import *`에서는 빠진다.
    prune_stale은 본체/테스트와 함께 제거됨 (Phase R3).
    """
    from globalPlugins.multiTaskingWindowNotifier import store

    expected = {
        "load", "save", "record_switch", "flush", "reload",
        "is_corrupted", "get_meta", "get_app_beep_idx", "get_tab_beep_idx",
    }
    missing = expected - set(dir(store))
    assert not missing, f"missing public API: {missing}"


def test_store_all_only_contains_runtime_api():
    """`__all__`에는 런타임 9개만. reset_cache/prune_stale은 금지."""
    from globalPlugins.multiTaskingWindowNotifier import store

    public = {
        "load", "save", "record_switch", "flush", "reload",
        "is_corrupted", "get_meta", "get_app_beep_idx", "get_tab_beep_idx",
    }
    assert set(store.__all__) == public, (
        f"__all__ drift: {set(store.__all__) ^ public}"
    )


def test_reset_cache_accessible_but_private():
    """reset_cache는 __all__ 격리되지만 명시 접근은 가능 (테스트 호환)."""
    from globalPlugins.multiTaskingWindowNotifier import store

    assert hasattr(store, "reset_cache"), (
        "reset_cache는 명시 접근(store.reset_cache / from store.core import ...)용으로 유지해야 한다"
    )
    assert "reset_cache" not in store.__all__, (
        "reset_cache는 공개 API 아님 — __all__에서 제거된 상태여야 한다"
    )


def test_prune_stale_removed():
    """Phase R3: prune_stale 함수 본체 + 재export 완전 제거.

    Phase 8(창 닫기 알림) 착수 시 신규 설계로 재작성. 과거 구현은 git log.
    """
    from globalPlugins.multiTaskingWindowNotifier import store
    from globalPlugins.multiTaskingWindowNotifier.store import core

    assert not hasattr(store, "prune_stale"), (
        "prune_stale 재export가 남아 있음 — Phase R3에서 완전 제거되어야 함"
    )
    assert not hasattr(core, "prune_stale"), (
        "prune_stale 본체가 store.core에 남아 있음 — Phase R3에서 완전 제거되어야 함"
    )


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
