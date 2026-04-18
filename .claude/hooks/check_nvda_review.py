# -*- coding: utf-8 -*-
"""NVDA 애드온 리뷰 미수행 감지 Stop hook.

변경된 globalPlugins/*.py 또는 manifest.ini가 있는데
.claude/last-review.txt가 그보다 오래됐으면 Claude에게
리뷰 수행을 요구하는 block 메시지를 stdout(JSON)으로 주입한다.

세션당 1회만 block 하도록 .claude/hook-state.json로 중복 방지.
git status가 없어도(미설치/비-git) 조용히 통과한다.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

# .claude/hooks/check_nvda_review.py  →  project root
ROOT = Path(__file__).resolve().parent.parent.parent
CLAUDE_DIR = ROOT / ".claude"
REVIEW_MARKER = CLAUDE_DIR / "last-review.txt"
HOOK_STATE = CLAUDE_DIR / "hook-state.json"

# 리뷰가 필요한 경로 (globalPlugins 전체 + manifest.ini)
WATCH_PATHS = ["globalPlugins", "manifest.ini"]


def read_input():
    try:
        raw = sys.stdin.read().strip()
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def git_changed_files():
    """git status --porcelain에서 감시 경로의 변경 파일 목록을 반환."""
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "status", "--porcelain", "--"] + WATCH_PATHS,
            capture_output=True, text=True, timeout=5,
        )
    except FileNotFoundError:
        return []
    except Exception:
        return []

    if out.returncode != 0:
        return []

    files = []
    for line in out.stdout.splitlines():
        # 포맷 예: " M globalPlugins/.../file.py", "?? manifest.ini"
        if len(line) < 4:
            continue
        path_part = line[3:].strip().strip('"')
        # rename 표기("orig -> new") 처리
        if " -> " in path_part:
            path_part = path_part.split(" -> ", 1)[1]
        path = ROOT / path_part
        if path.exists() and path.is_file():
            files.append(path)
    return files


def latest_mtime(paths):
    best = 0.0
    for p in paths:
        try:
            m = p.stat().st_mtime
            if m > best:
                best = m
        except OSError:
            continue
    return best


def review_marker_mtime():
    if REVIEW_MARKER.exists():
        try:
            return REVIEW_MARKER.stat().st_mtime
        except OSError:
            return 0.0
    return 0.0


def session_already_warned(session_id):
    if not session_id or not HOOK_STATE.exists():
        return False
    try:
        state = json.loads(HOOK_STATE.read_text(encoding="utf-8"))
        return state.get("warned_session") == session_id
    except Exception:
        return False


def mark_session_warned(session_id):
    if not session_id:
        return
    try:
        HOOK_STATE.write_text(
            json.dumps({"warned_session": session_id}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def main():
    hook_input = read_input()

    # 이미 이 Stop 훅이 block을 반환한 상태면 무한 루프 방지를 위해 통과
    if hook_input.get("stop_hook_active"):
        return 0

    session_id = hook_input.get("session_id", "")

    changed = git_changed_files()
    if not changed:
        return 0

    marker_mtime = review_marker_mtime()
    changed_mtime = latest_mtime(changed)

    # 리뷰 마커가 최신 수정보다 나중이면 통과
    if marker_mtime > 0 and marker_mtime >= changed_mtime:
        return 0

    # 세션당 1회만 경고 (사용자가 "리뷰 생략"으로 탈출하는 경우 대비)
    if session_already_warned(session_id):
        return 0
    mark_session_warned(session_id)

    rel_files = []
    for p in changed[:5]:
        try:
            rel_files.append(str(p.relative_to(ROOT)).replace("\\", "/"))
        except ValueError:
            rel_files.append(str(p))

    tail = f" 외 {len(changed) - 5}개" if len(changed) > 5 else ""
    reason = (
        "NVDA 애드온 파일 {n}개가 변경되었습니다. "
        "완료 선언 전 @NVDA Addon Development Specialist 에이전트로 리뷰를 수행한 뒤 "
        "`.claude/last-review.txt`를 현재 시각으로 갱신하세요.\n"
        "변경 파일: {files}{tail}\n"
        "리뷰 생략이 사용자에 의해 명시된 경우에만 마커만 touch 하세요."
    ).format(n=len(changed), files=", ".join(rel_files), tail=tail)

    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
