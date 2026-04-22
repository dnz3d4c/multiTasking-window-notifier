# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""튜토리얼 노출 여부 플래그 read/write.

저장 위치는 `config.conf[ADDON_NAME]["tutorialShown"]` (boolean).
스키마와 default는 settings.CONFSPEC에서 단일 선언하고 settings.register()가
live config에 기본값을 주입한다. 본 모듈은 조회/기록만 담당해 레이어를 얇게 유지.

NVDA는 프로필 전환/종료 시점에 config.conf를 자동 flush하므로 `mark_`에서
`config.conf.save()`를 명시 호출하지 않는다. 중간에 NVDA가 비정상 종료되면
다음 부팅에서 다시 한 번 안내가 뜰 수 있는데, 이건 데이터 손상이 아니라
"안내가 한 번 더 오는" 정도의 허용 가능한 회귀.
"""

import config
from logHandler import log

from ..constants import ADDON_NAME


def is_tutorial_shown() -> bool:
    """튜토리얼 안내를 이미 1회 이상 노출했는지 조회.

    settings.register()가 이미 default=False를 live config에 주입한 뒤이므로
    정상 흐름에서는 KeyError가 나지 않는다. 다만 사용자가 nvda.ini를 수동
    편집했거나 프로필 전환 경계에서 섹션이 일시적으로 비어있는 케이스를
    방어적으로 False로 폴백 — 안내를 한 번 더 띄우는 쪽이 "안내를 아예 못
    받는 쪽"보다 사용자 친화적이다.
    """
    try:
        return bool(config.conf[ADDON_NAME]["tutorialShown"])
    except KeyError:
        log.warning("mtwn: tutorialShown read fallback — section/key missing")
        return False
    except Exception:
        log.exception("mtwn: tutorialShown read failed")
        return False


def mark_tutorial_shown() -> None:
    """튜토리얼 안내를 노출했음을 영구 기록.

    호출 경로:
        1. tutorial.prompt._show_prompt — 사용자가 첫 실행 확인에서 Yes/No 선택 시
        2. tutorial.dialog.TutorialDialog EndModal 전부 — 완료/스킵/try_now/Escape

    예외는 삼키고 log만 — 기록 실패가 다른 Phase의 이벤트 훅을 막으면 비프
    기능 자체가 회귀하는 게 더 큰 손해.
    """
    try:
        config.conf[ADDON_NAME]["tutorialShown"] = True
    except Exception:
        log.exception("mtwn: tutorialShown write failed")
