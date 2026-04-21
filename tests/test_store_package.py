# -*- coding: utf-8 -*-
"""store 모듈 공개 표면 smoke 테스트.

Phase 12-2에서 `store/` 서브패키지(4파일)를 단일 `store.py`로 평탄화.
외부 import 경로 `from . import store`는 불변이므로 본 테스트가 검증하는
공개 표면(10개 __all__ + reset_cache 테스트 유틸)도 그대로 유지된다.
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
    """공개 API + 내부 유틸 1개(reset_cache) 구조.

    런타임 코드가 실제 쓰는 함수만 __all__에 노출. reset_cache는 테스트 전용
    유틸로 재export는 유지하되 `from store import *`에서는 빠진다.
    prune_stale은 본체/테스트와 함께 제거됨 (Phase R3).
    """
    from globalPlugins.multiTaskingWindowNotifier import store

    expected = {
        "load", "save", "record_switch", "flush", "reload",
        "is_corrupted", "get_meta", "get_app_beep_idx", "get_tab_beep_idx",
        "set_aliases", "move_item",
    }
    missing = expected - set(dir(store))
    assert not missing, f"missing public API: {missing}"


def test_store_all_only_contains_runtime_api():
    """`__all__`에는 런타임 공개 API만. reset_cache/prune_stale은 금지."""
    from globalPlugins.multiTaskingWindowNotifier import store

    public = {
        "load", "save", "record_switch", "flush", "reload",
        "is_corrupted", "get_meta", "get_app_beep_idx", "get_tab_beep_idx",
        "set_aliases", "move_item",
    }
    assert set(store.__all__) == public, (
        f"__all__ drift: {set(store.__all__) ^ public}"
    )


def test_reset_cache_accessible_but_private():
    """reset_cache는 __all__ 격리되지만 명시 접근은 가능 (테스트 호환)."""
    from globalPlugins.multiTaskingWindowNotifier import store

    assert hasattr(store, "reset_cache"), (
        "reset_cache는 명시 접근(store.reset_cache / from .store import reset_cache)용으로 유지해야 한다"
    )
    assert "reset_cache" not in store.__all__, (
        "reset_cache는 공개 API 아님 — __all__에서 제거된 상태여야 한다"
    )


def test_prune_stale_removed():
    """Phase R3: prune_stale 함수 본체 + 재export 완전 제거.

    Phase 8(창 닫기 알림) 착수 시 신규 설계로 재작성. 과거 구현은 git log.
    Phase 12-2에서 서브패키지가 단일 파일로 평탄화됐으므로 store 모듈 단독
    검증만 남긴다(core 서브모듈은 더 이상 존재하지 않음).
    """
    from globalPlugins.multiTaskingWindowNotifier import store

    assert not hasattr(store, "prune_stale"), (
        "prune_stale 재export가 남아 있음 — Phase R3에서 완전 제거되어야 함"
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
