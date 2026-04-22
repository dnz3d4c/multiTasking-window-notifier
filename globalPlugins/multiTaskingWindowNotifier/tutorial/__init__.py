# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""튜토리얼 서브패키지 공개 API.

Phase 1에서는 state 헬퍼만 공개. Phase 2에서 open_tutorial() 추가 예정.
"""

from .state import is_tutorial_shown, mark_tutorial_shown

__all__ = ["is_tutorial_shown", "mark_tutorial_shown"]
