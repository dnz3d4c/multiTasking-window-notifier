# Phase 12 구조 축소 리팩토링 — 교훈 문서

사용자 호소 "코드 이해 어렵고 로직 복잡하다"에서 출발. 2020 legacy 브랜치(70 LOC 단일 파일) 원형에서 출발한 프로젝트가 21개 모듈 / 3,422 LOC / 66.0 KB까지 팽창한 상태를 되감는 작업.

누적 결과: **21 → 14 모듈 / 3,422 → 약 2,900 LOC / 66.0 → 55.2 KB / pytest 202/202 무회귀**.

본 문서는 두 부분으로 구성된다:
1. **Part A — Phase별 이력**: Phase 1~6 각각의 team-debate 결론, 반증된 가설, 회귀 사고 기록
2. **Part B — 재사용 원칙**: 다음 리팩토링 세션이 바로 쓸 수 있는 판단 체크리스트

---

## Part A — Phase별 이력

각 Phase는 team-debate(Consolidator/Guardian/Judge 3인 병렬) 게이트를 거친 후 구현. 토론의 원형은 git log 커밋 메시지에 요약되어 있다.

### Phase 1 — 개인 식별 제거 + 운영 데이터 untrack

**쟁점**: 치환 토큰 선택 (일반명 1개 / 익명 고유명 2개 / 영문 익명), `app.list` 처리.

**판정**: 한국어 익명 고유명 2개 — `"메신저앱"` / `"대화창제목"`. `git rm --cached` + 워킹트리 삭제. `.gitignore`에 `app.list`/`app.json` 패턴 추가.

**반증된 가설**: "리포 내 `app.list` 삭제는 런타임 영향 있을 것" → 실사용자 데이터는 `%APPDATA%\nvda\...\`에 독립 생성/갱신되므로 리포 파일 삭제 영향 0. 오히려 리포 파일이 개인 식별 유출원이었음.

**회귀 사고**: 없음. 커밋 `3b29ce3`.

---

### Phase 2 — store 서브패키지 평탄화

**쟁점**: 섹션 배치 순서 (top-down 실행 / 공개 API 먼저 / `__all__` 상단 + 구현 top-down).

**판정**: `(C)` — `__all__`을 파일 상단에 두고 구현은 실행 순서(I/O → 할당 → 상태 파이프라인 → 공개 API)대로 배치. Judge 가중합 4.80으로 (A) 3.45 / (B) 3.60 압도.

**반증된 가설**: Guardian의 "`_states` 캐시는 공개 API 직전" 주장 → Judge는 "`_load_state` 직전 프라이빗 섹션 중"이 기존 `core.py:86` 배치와 동일하며 회귀 리스크 최소라 판정.

**회귀 사고**: `test_store_package_has_docstring`가 영문 문자열 "store"를 docstring에 요구. 한국어 전용 docstring(`"앱 목록 + 메타데이터 저장소 (단일 파일)"`)으로 작성해 테스트 실패 → 첫 줄에 `"(store 단일 파일)"` 추가로 즉시 정정. **교훈**: 기존 테스트 기대값의 언어/어휘를 사전 점검해야 한다. 커밋 `08e74ec`.

**또 다른 회귀 — 빈 디렉토리 잔존**: `git rm -r store/`로 파일 4개는 제거됐으나 디렉토리 자체는 워킹트리에 남음. NVDA 리뷰가 Critical로 지적 → `rmdir`로 정리. **교훈**: Python import 해석에서 빈 디렉토리 + 동명 모듈 파일 공존 시 무작위 파일 삽입으로 네임스페이스 패키지 활성 위험.

---

### Phase 3 — 이벤트 훅 3-way 통합 (최고 위험 단계)

**쟁점**: 공개 함수 수 / 프라이빗 헬퍼 통합 전략 / normalize_title 공용 헬퍼 추출.

**판정**:
- 쟁점 1: `(A) 3개 공개 함수 유지` — NVDA 훅 이름과 1:1 매핑. `(B) 단일 dispatch + kind enum` 안티패턴 거부.
- 쟁점 2: `(α) dispatch_focus 직속 이관` — `_log_focus_diag`, `_determine_match_source`는 3분기 전용 상수·필드에 종속.
- 쟁점 3: **공용 헬퍼 추출 거부**. `handle_foreground`는 empty title 통과(SCOPE_APP fallback), 나머지는 empty 컷. 정책 차이로 공용화 시 회귀 위험.

**반증된 가설**: 원래 플랜 토론 설계에서 "상태 필드 ≥ 2면 클래스 유리" 판정 기준을 썼으나, 실제 코드는 상태 0이라 클래스 논거 자체가 기각됨. → 초기 설계 가정은 코드 실측으로 재검증되어야 한다.

**회귀 사고**: 없음. 테스트 4파일 monkeypatch 경로 일괄 치환. 커밋 `4439e95`.

---

### Phase 4 — lookupIndex + switchFlusher 흡수

**쟁점**: LookupIndex 흡수 위치 / FlushScheduler 흡수 위치 / property wrapper.

**판정**:
- 쟁점 1: `(B) matcher.py 내부 독립 클래스 공존` — 파일 삭제 + 클래스 유지로 SRP 보존. rebuild 20+ LOC 분기 로직을 Matcher 메서드로 접지 않음.
- 쟁점 2: `(D) GlobalPlugin 흡수` — FlushScheduler의 상태 2개·메서드 3개를 `_notify_switch/_maybe_flush/_reset_flush_schedule`로 GlobalPlugin에 직접 이관. "매칭 후 기록"은 애플리케이션 레이어 책임이라는 레이어 분리 유지.
- 쟁점 3: `(E) @property 유지` — 테스트 25개 호환.

**반증된 가설**: "Matcher에 모든 매칭 관련 상태 집중(C)" 주장 → Judge가 "Matcher 단일 클래스에 flush 상태 흡수 시 match_and_beep 테스트 fixture가 `time.monotonic`·상수·`store.flush` 3종 monkeypatch로 복잡화"를 근거로 기각.

**회귀 사고**: 없음. 커밋 `e899133`.

---

### Phase 5 — 네이밍 풀네임화

**쟁점**: `tab_sig` 파라미터 / `fg` 변수 / `event_sig` 지역 튜플.

**판정 충돌**: Judge는 보수안 `(B)(E)(G)` (외부 유지 + fg 유지 + 지역 변수 유지) 채택. 그러나 이 판정은 원 플랜(사용자 승인된 풀네임화 규칙)과 충돌. **사용자 재확인 결과 원 플랜 `(A)(D)(F)` 전수 풀네임화 채택** — 사용자 명시 지침이 team-debate 판정의 상위.

**중요 교훈**: team-debate는 전술 조율용이지 사용자 확정 지침 번복용이 아니다. Judge의 점수 체계가 "사용자 지침 부합" 축 가중치를 40%로 두었어도, 3안 완전 동점에서 Guardian 우세 룰이 발동하면 사용자 지침이 후순위로 밀릴 수 있음. **사용자에게 충돌을 명시적으로 보고**하고 재확인 받는 단계가 필수.

**회귀 사고 (Critical)**: sed 연쇄 치환 버그. `last_event_sig` → `last_event_signature` 단계에서 `event_sig` 부분 문자열 포함. 이후 `event_sig` → `event_signature` 단계가 `last_event_signature` 안의 `event_signature` 뒤에 또 `nature`를 덧붙여 `last_event_signaturenature`를 생성. 즉시 `signaturenature` → `signature` 전역 정정으로 해결. **교훈**: sed 다단계 치환은 **접두사/접미사 포함 관계를 사전에 전수 확인**해야 한다. 긴 토큰 먼저 규칙만으로는 부족하다. 커밋 `048120a`.

---

### Phase 6 — 주석/docstring 정리 + CLAUDE.md 절충

**쟁점**: Phase 번호 제거 범위 / 미래 예고 주석 / CLAUDE.md 범위.

**판정**:
- 쟁점 1: `(A) 전수 제거` — 단 유형 B(근거 역할)는 Phase 번호만 제거하고 설명 문장은 유지.
- 쟁점 2: `(D) 제거` — IMPROVEMENTS.md로 이관.
- 쟁점 3: `(F) 중복/이력만` — Guardian 우세 발동(±0.30 이내). **실용적 예외**: 코드-문서 불일치 방지를 위해 tree 블록은 갱신.

**특수 케이스**: Phase 12 시리즈(유형 E, 이번 리팩토링 본인 이력)는 git log 신뢰성 최고라 무조건 제거. 오히려 "방금 한 작업"을 주석에 남기면 리팩토링 직후 주석 노이즈가 가장 크다.

**회귀 사고**: 없음. 로직 무수정(주석/docstring만). 커밋 `036d9e1`.

---

## Part B — 재사용 원칙 체크리스트

다음 리팩토링 세션(또는 미래 Claude 세션)이 바로 참조할 수 있는 판단 기준.

### 원칙 1 — 모듈 분할 통합 검토 신호

상호 참조 docstring이 **2건 이상** 반복되면 통합 검토. Phase 3의 3개 파일(foregroundWatcher/nameChangeWatcher/focusDispatcher)이 서로를 "나머지 두 훅은 ~담당"으로 3회 상호 참조한 사례가 전형. 물리 경계가 역할 경계와 어긋났다는 경고.

### 원칙 2 — 축약 변수명 도입 기준

축약 도입 전 NVDA 소스(`C:\project\ext\nvda\source\**`)에서 원문 용어 존재 여부 확인. 원문이 있으면 풀네임 유지(`windowClassName`, `getForegroundObject`). 원문 없이 로컬 관습 축약은 사용자 명시 지침 "연상 가능" 기준 위반.

### 원칙 3 — Phase R 원칙 재확인

시간 가드(`0.3초 내 재매칭 skip`)·중복 가드 도입 전 "NVDA가 이미 보장하는가" / "이벤트 식별자로 근본 분기 가능한가" 점검. NVDA `eventHandler.doPreGainFocus` + `IAccessibleHandler/orderedWinEventLimiter`가 dedup 보장하는 레이어를 애드온에서 재구현하는 건 낭비.

### 원칙 4 — 단일 호출 얇은 래퍼 금지

`rebuild` 1개 메서드만 있는 클래스, `notify`/`maybe_flush` 2개 필드 클래스, property 1개 wrapper는 호출부에 흡수 검토. SRP와 통합의 경계는 **"이 클래스가 단독 테스트 파일을 가질 가치가 있는가"**.

### 원칙 5 — team-debate 게이트 운영

- 동점(±0.30) 시 Guardian 우세 — 회귀 방어 편향 수용.
- 사용자 명시 지침과 판정이 충돌하면 **사용자에게 명시적으로 보고**하고 재확인. 자동 우회 금지.
- 쟁점이 3안 이상이면 완전 동점 가능성 감안.

### 원칙 6 — sed 다단계 치환 안전 순서

1. 치환 쌍 전수를 나열
2. 접두사/접미사 포함 관계 검사 (예: `event_sig` vs `last_event_sig`)
3. 긴 토큰/포함관계상 "피포함" 토큰부터 치환
4. 연쇄 아티팩트(예: `signaturenature`) 최종 grep으로 검증

### 원칙 7 — Python 모듈 평탄화 체크리스트

- 디렉토리 삭제 후 동명 모듈 파일 생성 시 Python import는 `from . import X` 그대로 해석.
- 빈 디렉토리 잔존 주의: `rmdir` 명시 필요. 빈 네임스페이스 패키지 활성 가능성.
- `__pycache__` stale .pyc 제거 필수 (파일 이동/삭제/이름변경 후).

### 원칙 8 — 외부 파라미터 vs 내부 변수 경계

단일 애드온 내부에서는 "외부 공개 계약" 개념이 허구일 수 있다. 테스트가 keyword 인자로 호출한다고 해서 자동으로 파기적 변경 위험이 생기는 건 아니다. 다만 **대규모 diff**를 감수할 수 있는 Phase(예: 네이밍 풀네임화 단독 커밋)에서만 일괄 변경.

### 원칙 9 — Phase 이력 주석의 운명

- 방금 한 작업: **무조건 제거** (git log 신뢰성 최상).
- 유형 B(근거 역할): Phase 번호만 제거, 설명 문장 유지.
- 커밋 규약 프리픽스(`Phase 1.~4.`): **규약 식별자**라 이력 주석과 성격 다름 → 유지.
- Phase R 교훈 섹션(`CLAUDE.md`): 프로젝트 내부 관용어로 교훈 지도 역할 → 유지.

### 원칙 10 — 리뷰 + 빌드 + 마커 삼위일체

프로젝트 `CLAUDE.md` 구현 후 필수 리뷰 절차:
1. `@NVDA Addon Development Specialist` 리뷰
2. Must fix 처리
3. `uv run python build.py` (자동 수행, 사용자 요청 없어도)
4. `.claude/last-review.txt` 갱신 (Stop hook 통과)
5. 위 단계 완료 후에만 "완료" 응답

---

## 회귀 방어 — pytest 체크리스트 (무변경 원칙)

Phase 1~6 내내 **202개 테스트 전수 PASS 유지**가 무회귀 계약. Phase 시작 전/후에 `uv run pytest` 필수.

실기 검증(NVDA 실환경)은 [docs/smoke-test.md](./smoke-test.md) 참조.

---

## 반증된 초기 플랜 가설

| 플랜 초기 주장 | 실제 결과 | 원인 |
|---|---|---|
| Phase 3 "상태 필드 ≥ 2면 클래스 유리" | 실제 무상태 → 클래스 논거 자체 기각 | 초기 설계 가정이 실측으로 반증됨 |
| Phase 5 "fg는 NVDA 관용어라 유지 논거 성립" | 사용자 재확인에서 풀네임 채택 | 사용자 지침이 Judge 판정 상위 |
| Phase 2 "서브패키지 4파일은 관심사 분리 명확" | 단일 파일 + 섹션 구분자로 동등 가독성 확보 | Python 모듈 경계는 섹션 주석으로 대체 가능 |
| Phase 1 "git rm --cached만으로 충분" | 로컬 워킹트리 삭제까지 필요 | 실사용자 데이터는 `%APPDATA%`, 리포 파일은 시드 가치도 없음 |

---

## 참고

- 각 Phase 구현 커밋: `3b29ce3` (P1) → `08e74ec` (P2) → `4439e95` (P3) → `e899133` (P4) → `048120a` (P5) → `036d9e1` (P6) → 본 커밋 (P7).
- 2020 legacy 원형: `git show legacy/2020-master`.
- 토론 참여자 설계는 플랜 파일 "토론 설계" 섹션 — archive 이동 후에도 `git log`로 조회 가능.
