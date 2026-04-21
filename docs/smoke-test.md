# 실기 smoke test 체크리스트

NVDA 실환경에서 사용자가 수동으로 확인하는 회귀 검증. Phase 12 리팩토링 완료 후 및 이후 주요 변경 후 공통으로 반복 실행.

## 사전 준비

- [ ] `uv run pytest` — 202/202 PASS 확인
- [ ] `uv run python build.py` — `multiTaskingWindowNotifier-<version>.nvda-addon` 생성
- [ ] NVDA 메뉴 → 도구 → 애드온 스토어 → "외부 파일로부터 애드온 설치" → 생성된 `.nvda-addon` 선택
- [ ] NVDA 재시작

## 설치 구조 검증 (5항목)

프로젝트 CLAUDE.md의 "설치 구조 검증 체크리스트"와 동일:

- [ ] `%APPDATA%\nvda\addons\multiTaskingWindowNotifier\manifest.ini` 존재
- [ ] `%APPDATA%\nvda\addons\multiTaskingWindowNotifier\globalPlugins\multiTaskingWindowNotifier\__init__.py` 존재
- [ ] `%APPDATA%\nvda\addons\multiTaskingWindowNotifier\*.py` 결과 **없음**(수동 복사 오타 감지)
- [ ] `%APPDATA%\nvda\multiTaskingWindowNotifier\` 사용자 데이터 디렉토리 존재 (애드온 최소 1회 실행 후)
- [ ] `%APPDATA%\nvda\nvda.ini`에 `[multiTasking...]` 섹션 헤더 (애드온 최소 1회 실행 후)

## 단축키 4종 동작 (4항목)

- [ ] **NVDA+Shift+T** (등록): 현재 창에서 눌러 scope 선택 다이얼로그 표시 → "이 창만" / "이 앱 전체" 중 선택 → alias 입력창 표시(빈 값 허용) → 등록 완료 음성 안내
- [ ] **NVDA+Shift+D** (삭제): 등록된 창에서 눌러 정확 매치만 삭제. 다른 앱의 동일 title 창은 보존됨을 확인
- [ ] **NVDA+Shift+R** (새로고침): 목록 파일 재로드. 수동으로 `app.json` 편집한 경우 반영 확인
- [ ] **NVDA+Shift+I** (목록): 다이얼로그 표시 → 다중 선택(Shift/Ctrl+클릭) → Delete 키로 일괄 삭제 가능 → 단일 선택 시 "대체 제목 편집(&E)" 버튼 노출

## Alt+Tab 전환 비프 (3항목)

- [ ] 등록된 창 2개 이상 상태에서 Alt+Tab 오버레이 표시 → 후보 창마다 **다른 비프 조합** 들림 (앱 음 + 탭 음)
- [ ] scope=app 등록만 있는 앱(예: Spotify)으로 Alt+Tab → **단음** 재생 (alias 경유 매칭)
- [ ] 같은 앱의 다른 창으로 Alt+Tab → 앱 음은 공유, 탭 음은 구분됨

## Ctrl+Tab 탭 전환 비프 (2항목)

- [ ] **메모장** Ctrl+Tab (editor 분기): 같은 제목의 여러 탭이 있어도 **자식 hwnd 기반으로 구분**되어 탭별 비프
- [ ] **Notepad++** MRU 오버레이 (앱별 overlay 분기): 탭 순회 중 탭마다 비프

## event_foreground 전환 비프 (2항목)

- [ ] 등록 안 된 앱 → 등록된 앱으로 **Alt+Tab 릴리스**하면 foreground 전환 시 비프 1회
- [ ] SCOPE_APP 등록만 있는 앱(Spotify 등) 진입 시 **단음** 재생 (title 빈 상태에서도 appId만으로 fallback)

## 설정 패널 (3항목)

NVDA 설정(`NVDA+Ctrl+G`) → "창 전환 알림" 카테고리:

- [ ] **프리셋 전환** (classic/pentatonic/fifths/moss_bell): 미리듣기 버튼 눌러 각 프리셋 2음 시연
- [ ] **duration** 조정 (20~500ms): 값 변경 후 저장 → 다음 비프에 반영
- [ ] **gap_ms** 조정 (0~200ms): 2음 사이 간격 변경 확인

## app.json v9 로드 (2항목)

- [ ] 다른 머신의 v9 `app.json`을 `%APPDATA%\nvda\multiTaskingWindowNotifier\app.json`에 복사 → NVDA 재시작 → 목록 정상 로드
- [ ] 일부러 `"version": 8`로 수정 → NVDA 재시작 → `ui.delayedMessage`로 "목록 파일이 손상되어 빈 상태로 시작했어요" 안내 표시 + 원본 파일 보존(덮어쓰지 않음)

## 손상 복구 (1항목)

- [ ] 손상 상태에서 NVDA+Shift+T로 새 항목 등록 → 정상 저장 + `state["corrupted"] = False` 자동 해소

## 특수 회귀 방어 (2항목)

- [ ] Firefox (자식 wcn = 최상위 wcn) → editor 분기로 **오탐 없음** (모든 포커스 이동에 비프 울리지 않음)
- [ ] Win+B / 시스템 트레이 / 알림 센터 (Alt+Tab 오버레이와 같은 wcn 공유) → **오탐 없음** (Alt+Tab 전용 fg_class_name AND 조건)

## 완료 후

- [ ] 모든 항목 통과 시 `.claude/last-review.txt` 갱신 (`date > .claude/last-review.txt`)
- [ ] `git log --oneline` Phase 12-1~7 커밋 7개 확인
- [ ] `IMPROVEMENTS.md` Phase 12 완료 이력 반영 확인

## 실패 시

실패 항목 재현 로그를 `debugLogging=True`(설정 패널) 활성화 후 `%APPDATA%\nvda\nvda.log` 수집. `mtwn: DBG` 라인 + 해당 시점 스택트레이스 함께 제출.
