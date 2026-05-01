# Codex × Claude 페어 리뷰

작성일: 2026-05-01
대상: multiTaskingWindowNotifier 전체 (HEAD `1b9fe61`)
플랜: `~/.claude/plans/floofy-riding-patterson.md`

---

## 1. 페어 리뷰 구성

본 프로젝트 첫 cross-provider 페어 리뷰. self-correction blind spot(Tsui et al. 2025) 회피 목적.

| 트랙 | 시각 | 모델 | 범위 | 라인 |
|------|------|------|------|------|
| Codex (`--deep`) | OpenAI 일반 코드 시각 | model_reasoning_effort=high | globalPlugins/ + tests/ + manifest 전체 (stat만 prompt에 주고 sandbox read 위임) | 11,881 |
| 영역 A — NVDA API/이벤트 라우팅 | 도메인 (Phase R/T/R5 교훈) | NVDA Addon Specialist (opus) | `__init__`, `eventRouter`, `scripts`(@script), `appIdentity`, `windowInfo`, `tabClasses` | ~1,236 |
| 영역 B — matcher 코어 | 도메인 (매칭 정합성) | NVDA Addon Specialist (opus) | `matcher.py` 단독 | 312 |
| 영역 C — 데이터·비프·설정 | Python (SoT/원자성/할당) | Python Specialist (opus) | `store`, `presets`, `constants`, `beepPlayer`, `settings` | ~1,194 |
| 영역 D — GUI 접근성 & UX | wxPython (NVDA 음성) | wxPython Specialist (opus) | `listDialog`, `settingsPanel`, `scripts`(wx 모달), `ui.message` 패턴 전반 | ~611+ |

병렬 5 트랙 동시 디스패치, 단일 메시지로 띄움.

## 2. 통계

| 등급 | 건수 | 비고 |
|------|------|------|
| **Critical (P0)** | 0 | 보안/데이터 손실/즉시 회귀 위험 발견 없음 |
| **Important (즉시 수정 후보)** | 9 | 양측 동의 1 + Codex만 2 + Claude만 6 |
| **Insight (방향성/원칙)** | 8 | docstring 보강, SoT 정렬, 디버그 단서 |
| **Defer (의도된 trade-off)** | 9 | 동작 무관 / 발생 빈도 0 / 이미 별 트랙 의도 |
| **Reject (실제 이슈 아님)** | 2 | 자기 결론 "유지가 합리적" 류 |
| **합계** | 28 | |

원본 출처별: Codex 3건 / 영역 A 4건 / 영역 B 4건 / 영역 C 12건 / 영역 D 6건. 영역 C(데이터 저장소)에 발견이 집중됐다 — v9 전환 후 손상 처리 정책 일관성이 후속 회귀 잠재선임을 시사.

## 3. 페어 리뷰 핵심 인사이트 (토론 산출)

### 인사이트 1 — 두 시각의 발견 패턴이 보완적이었다

Codex는 **코드 외부 산출물**(`manifest.ini` ↔ `readme.html` 부재, 빌드 스크립트와의 정합성)에 발견을 넣었다. Claude 4트랙은 **코드 내부 로직**만 깊이 봤다. 페어 리뷰의 의의는 정확히 이 보완성에서 나왔다.

> 단일 시각으로는 "코드만 보거나 메타데이터만 보거나" 둘 중 하나로 기울기 쉬움. 페어 리뷰가 둘 다 강제로 본다.

### 인사이트 2 — 양측이 같은 결론에 도달한 단 1건은 실제 핵심 이슈

`set_aliases` / `move_item`이 디스크 저장 실패 시 메모리 변경을 롤백하지 않는 비대칭 (vs `save()`)은 양측이 독립적으로 같은 라인·같은 진단을 냈다. 페어 리뷰에서 양측 동의 1건은 priority 가중치를 한 단계 올린다.

### 인사이트 3 — Claude 4트랙은 NVDA Phase 교훈을 정확히 적용해 false positive를 만들지 않았다

CLAUDE.md의 Phase R("NVDA가 이미 보장하는 조건 재방어 금지"), R4b("단일 SoT"), R5("ScriptableType 메타"), T("callLater 안 ShowModal 금지") 4개 교훈이 모두 검토 통과. 도메인 컨텍스트 사전 주입이 실제로 false positive를 줄였다는 증거.

### 인사이트 4 — Codex의 P0 0건은 코드베이스 일반 품질이 양호하다는 시그널

Codex 프롬프트(`~/.claude/codex-prompts/review.md`)가 "anti-sycophancy: Claude가 어디 잘못했는지 찾아라"로 적극 공격을 요구했는데도 P0 0건. 단순한 sample size 문제는 아니다 — 14모듈 3,353줄을 high effort로 sandbox read까지 했으니. P0 부재는 진짜 시그널이다.

### 인사이트 5 — 데이터 무결성에 발견이 모인 패턴

전체 28건 중 12건이 영역 C(저장소). 그중 4건이 P1, 손상 처리 회로 관련. `app.json` v9 스펙 자체는 잘 잡혔지만, **"손상 감지 → corrupted=True → 빈 목록 시작 → 원본 보존"** 정책의 적용 일관성이 다음 작업 후보. 정책 통일 시 다른 발견(Codex P1, 영역 C P1 #1/#2) 다수가 같이 해결된다.

## 4. Important — 즉시 수정 후보 (9건)

### IMP-1 [양측 동의] `set_aliases` / `move_item` 저장 실패 시 메모리 롤백 부재

- **위치**: `store.py:578-583` (set_aliases), `store.py:622-627` (move_item)
- **출처**: Codex P2 (confidence 0.86) + 영역 C P2 #1
- **진단**: `save()`는 임시 dict로 디스크 성공 후 메모리 반영. 두 함수만 메모리 먼저 변경 → 저장 실패 시 False 반환하지만 메모리는 바뀐 채. 다음 `flush()`가 dirty=True 보고 자동 저장하면서 사용자가 의도 안 한 상태가 디스크에 슬쩍 박힐 수 있음.
- **권고**: `save()` 패턴(temp dict → 디스크 성공 → 메모리 교체)으로 정렬. 두 함수 동시에. 단위 테스트로 회귀 차단(`tests/test_store_move_item.py` 확장).

### IMP-2 [Codex] `app.json` 항목 key 타입 검증 누락

- **위치**: `store.py:180`
- **출처**: Codex P1 (confidence 0.88)
- **진단**: `_load_from_json`이 `it["key"]` 타입을 체크 안 하고 `_new_meta`로 전달. 외부 편집·손상으로 숫자 key가 들어오면 `splitKey`(`appIdentity.py:65`)의 문자열 검사에서 예외 → 손상 처리 회로(corrupted=True + 빈 목록) 대신 초기 로드 자체가 깨짐.
- **권고**: `isinstance(key, str)` 검증 추가. 실패 시 `return None`(전체 손상) 또는 해당 항목 skip + log.warning. 정책 통일 측면에서 전체 손상 권장(IMP-3, IMP-4와 일관).

### IMP-3 [Claude 영역 C] `items` 길이 초과를 손상이 아닌 절단으로 처리 — 손상 정책 위반

- **위치**: `store.py:148-152`, `:170`
- **진단**: scope 무효는 `return None`(전체 손상)인데 `len(items) > MAX_ITEMS=128`은 warning만 + `items[:MAX_ITEMS]` 절단 후 정상 반환. 절단된 결과가 다음 `_save_to_disk`에서 **원본을 덮어써 129번째 이후 항목 영구 소실**.
- **권고**: 손상 정책 통일 — `corrupted=True` + 빈 목록 + 원본 보존. 또는 절단 후에도 `state["corrupted"] = True`로 마킹해 자동 save 차단.

### IMP-4 [Claude 영역 C] `tabBeepIdx` 무효 시 침묵 드롭

- **위치**: `store.py:184-187`
- **진단**: 잘못된 타입/범위면 로그 한 줄 없이 조용히 버림. `_ensure_beep_assignments`가 빈 슬롯 max+1로 재할당 → **사용자가 익숙한 탭 비프 음정이 바뀜**. `appBeepMap` 검증(`:162-166`)은 warning 남기는데 `tabBeepIdx`만 침묵이라 비대칭.
- **권고**: invalid 시 `log.warning(f"mtwn: tabBeepIdx for key={it['key']!r} = {v!r} invalid, will be reassigned")` 추가. 또는 손상 정책 합류.

### IMP-5 [Claude 영역 C] `set_aliases` 입력 정규화 누락 — 매칭 회로 깨짐

- **위치**: `store.py:566-569`
- **진단**: docstring(L548)이 "정규화된 alias 목록" 입력 전제 명시하지만 함수 자체는 `normalize_title` 호출 안 함. `lookupIndex`의 windowLookup setdefault 키와 어긋나면 alias가 영영 매칭 안 됨.
- **권고**: store에서 정규화 호출하거나, docstring 강조 + 디버그 assert(`if any(s != normalize_title(s) for s in clean): log.warning(...)`)로 회귀 탐지. 안전 측면에서 store에서 호출하는 게 안전망 포함.

### IMP-6 [Codex] `manifest.ini` `docFileName = readme.html` 선언했지만 파일 부재

- **위치**: `manifest.ini:8`
- **출처**: Codex P2 (confidence 0.93)
- **진단**: 저장소에 `readme.html` 없고 `build.py`도 manifest와 `globalPlugins`만 zip에 넣음. **설치 후 NVDA 애드온 도움말 진입이 깨짐**.
- **권고**: 둘 중 하나
  - (a) `readme.html` 추가하고 `build.py` 포함 대상에 추가
  - (b) `manifest.ini`의 `docFileName` 항목 제거 — 도움말 페이지 운영 의도가 없으면 이 쪽이 깔끔

### IMP-7 [Claude 영역 D] `wx.MessageBox` 4번째 위치 인자 parent 모호 + 페어링 누락

- **위치**: `listDialog.py:260-265, 273-278, 301-306, 336-341, 350-355` (5곳)
- **진단**: wxPython 4 시그니처는 keyword 위주(`(message, caption=, style=, parent=, x=, y=)`). 위치 인자 4개 전달은 일부 빌드에서 parent 무시 → 다이얼로그가 free-floating으로 떠 NVDA 포커스 복귀가 메인 프레임으로 흘러 listDialog로 못 돌아옴. 추가로 `gui.mainFrame.prePopup/postPopup` 페어링도 누락 — `scripts.py:74-94` `_prompt_for_alias`는 정확히 따르므로 일관성 격차.
- **권고**: 5곳 모두 `with wx.MessageDialog(self, ...) as dlg: dlg.ShowModal()` 컨텍스트 매니저로 통일. parent=self 명시. 부모가 listDialog 자신이면 prePopup 불필요.

### IMP-8 [Claude 영역 D] alias 빈 입력 = "삭제" 동작이 사용자에게 명시 안 됨

- **위치**: `scripts.py:88-94` (`_prompt_for_alias`), `scripts.py:407` (`_edit_alias_from_dialog`)
- **진단**: 편집 다이얼로그에서 기존 alias가 표시된 상태로 열림. Ctrl+A → Delete → Enter 하면 alias **삭제**되지만 프롬프트 텍스트는 등록 시점 기준 문장이라 "비우면 삭제됩니다" 안내 없음. NVDA 사용자는 의도치 않게 삭제 가능.
- **권고**: `current_alias` 분기로 prompt 분기 — 편집 시 "비우면 대체 제목이 삭제됩니다" 줄 추가. 또는 별도 "지우기" 버튼이 있는 커스텀 dialog로 분리.

### IMP-9 [Claude 영역 C] corrupted 직후 사용자 신규 등록 → 원본 손상 파일 1회 save로 덮어씀

- **위치**: `store.py:389` (corrupted=True 설정 진입), `:457` (save 시 corrupted=False 리셋)
- **진단**: CLAUDE.md "## 데이터 포맷 / 손상 처리"는 "사용자가 파일을 복구/삭제할 기회"를 약속하지만, 신규 등록 한 번에 그 기회가 닫힘. 사용자가 "손상 안내 → 잠시 후 새 창 등록" 흐름이면 백업 기회 상실.
- **권고**: `_save_to_disk`가 `corrupted=True` 상태에서 처음 쓸 때 `app.json.corrupted-{timestamp}` 자동 백업 후 본체 저장. 코드량 작고 정책 약속 강화.

## 5. Insight — 방향성/원칙 (8건)

`즉시 fix는 아니지만 향후 리팩토링 시드.`

| # | 위치 | 발견 | 권고 |
|---|------|------|------|
| INS-1 | `matcher.py:107` (영역 B P1) | `_SUPPRESS_REPEAT_SEC = 0.3` 매직 숫자가 코드 1곳 + presets.py docstring 1곳 + CLAUDE.md 설명 1곳에 분산 | preset dict의 `suppressRepeatSec` 필드로 이동(R4b 단일 SoT) + 상수 위 docstring에 "preset 명세 기반 윈도우, dedup 가드 아님" 1줄 |
| INS-2 | `matcher.py:248-252` (영역 B P2) | `signature_guard skip` 분기에서 `switchCount` 증분 안 하는 의도가 코드만으론 모호 | docstring에 "skip 시 사용자 행동 1회 = 1 카운트로 보고 증분 안 함" 1줄 |
| INS-3 | `matcher.py:166-169` (영역 B P2) | `_resolve_beep_pair`의 `splitKey` 빈 appId 폴백 silent miss | invariant 깨짐 시 `log.warning(...)` 1줄로 가시화 |
| INS-4 | `matcher.py:170-184` (영역 B P2) | `appBeepMap`/`tabBeepIdx` miss 0번 collision 디버그 단서 약함 | 로그 메시지에 `available_keys=list(state['appBeepMap'].keys())[:8]` 추가 |
| INS-5 | `store.py:236-264` (영역 C P2) | `_assign_next_idx` 35슬롯 포화 후 wrap이 사용자 인지 모델("등록 순서대로 반음씩 위로")을 깸 | 단축키 등록 결과 보고 시점에서 1회 안내(CLAUDE.md UI 안내 원칙 충돌 주의 — **결과 보고**는 허용 카테고리). 또는 gap 재사용 모드 옵션 |
| INS-6 | `store.py:494-504` (영역 C P2) | `is_corrupted` `state=None`(미로드) 경로가 항상 False — 호출 순서 의존 fragile | docstring에 "load/save/reload로 캐시 워밍업 후 호출" 명시. 또는 내부에서 강제 로드 |
| INS-7 | `beepPlayer.py:134` (영역 C P3) | `slot_a, slot_b = preset["previewSlots"]` unpack 길이 미검증 | `presets.py:170` 부근에 `assert len(_p["previewSlots"]) == 2` 1줄 |
| INS-8 | `settingsPanel.py:143-150, 159-166` (영역 D P3) | `gapHelp`/`debugHelp` StaticText가 SpinCtrl/CheckBox와 페어 미명시 → 도움말 무음 | SpinCtrl에 `SetToolTip(_("..."))` 부착 또는 라벨에 합치기. 패널 docstring(L13-16)이 trade-off 의도 표명했으면 그대로 유지 + 명시 |

## 6. Defer — 의도된 trade-off (9건)

코드 변경 안 함. 발견 사실만 기록.

| # | 위치 | 보류 사유 |
|---|------|----------|
| DEF-1 | `eventRouter.py:64-76` (영역 A P3) | event_foreground tab_signature=0 dedup 윈도우 — 발생 빈도 0, 다음 정상 이벤트로 자연 회복 |
| DEF-2 | `eventRouter.py:122` (영역 A P3) | event_nameChange `getAppId(obj)` vs `getAppId(foreground)` 비대칭 — 동작 차이 거의 없음 |
| DEF-3 | `eventRouter.py:225-229` (영역 A P3) | dispatch_focus 3분기 우선순위 — 현재 `DEFAULT_TAB_CLASSES` 데이터에서 동시 매칭 케이스 0 |
| DEF-4 | `appIdentity.py:29-31` (영역 A P3) | "순환 위험" 코멘트 근거 약함 — 동작 무관 |
| DEF-5 | `store.py:198-228` (영역 C P3) | 동시 NVDA 인스턴스 race(`.tmp → os.replace`) — portable+installed 동시 운영 거의 없음 |
| DEF-6 | `store.py:217-228` (영역 C P3) | `.tmp` 잔여물 운영 가이드 — README 업데이트 시점 후보 |
| DEF-7 | `presets.py:162-175` (영역 C P3) | 부팅 assert가 `python -O` 우회 가능 — NVDA stock 빌드는 `-O` 안 씀, 위험 0 |
| DEF-8 | `settings.py:69-87` (영역 C P3) | `_parse_default` 정규식 매번 — Python 정규식 LRU 캐시로 실질 영향 미미 |
| DEF-9 | `tutorial/dialog.py:127-151` (영역 D P3) | `ui.message(title)` 중복 낭독 — `_titleLabel`이 StaticText로 Tab 도달 불가, ui.message 없으면 사용자가 단계 제목 들을 방법 없음. **유지가 합리적**. |

## 7. Reject — 실제 이슈 아님 (2건)

| # | 위치 | 기각 사유 |
|---|------|----------|
| REJ-1 | `tutorial/dialog.py:127-151` 일부 | 영역 D 발견 본문에서 자기 결론 "유지가 합리적" — 발견 즉시 자기 기각 |
| REJ-2 | `tutorial/dialog.py:160-163` | StaticText.SetFocus 폴백 — 트리거 조건(panel 렌더 실패)이 정상 흐름에서 0건. 폴백 자체가 무효 코드라 제거 vs 유지는 미세 — **현재 상태로 동작 영향 0** |

## 8. NVDA Phase 교훈 통과 검증

다음 영역에서 **재방어/안티패턴이 발견되지 않았다**. CLAUDE.md 사전 컨텍스트 주입이 효과적이었던 증거.

| 교훈 | 검증 결과 |
|------|-----------|
| Phase R — NVDA 보장 재방어 금지 | event_foreground/nameChange/gainFocus 진입점 모두 try/except + finally `nextHandler()` 1겹만. 시간 가드(0.3초 매직 상수) 같은 재방어 코드 없음. ✓ |
| Phase R — `core.callLater` 단일 호출 | `beepPlayer._schedule_second_beep`(`:44-59`) `core.callLater` + `try/except + log.exception` 1겹. 과거 3단 폴백(wx.CallLater, 동기) 제거 완료. ✓ |
| Phase R4b — 단일 SoT | `beepPlayer.py:39-41` 주석 명시적 "기본값 상수 두지 않음" + matcher/settingsPanel이 `settings.get()` 주입. ✓ (단, INS-1의 `_SUPPRESS_REPEAT_SEC`는 SoT 분산 — Insight) |
| Phase R5 — Mixin `ScriptableType` 메타 | `scripts.py:97`에 `metaclass=ScriptableType` 명시. ✓ |
| Phase T — `callLater` 콜백 안 ShowModal 금지 | `tutorial/prompt.py`가 `core.postNvdaStartup.register` + `wx.CallAfter`로 한 틱 양보. ShowModal 직전 `mark_tutorial_shown` 호출. 정확. ✓ |
| 불변 원칙 6번 — UI 선제 안내 금지 | `scripts.py`의 모든 `ui.message`가 사용자 트리거 결과 보고 또는 오류 안내. "이동했어요" 류 선제 안내 없음. `_move_entry_from_dialog` docstring(L437-439)에서 의식적 생략 명시. ✓ |
| 번역 `_()` 누락 | listDialog/settingsPanel/scripts 전체 raw 문자열 노출 없음. ✓ |

## 9. 추천 후속 액션

> 사용자 명시 채택 시 진행. 메인 컨텍스트가 자체 판단으로 fix 적용하지 않음 (글로벌 지침 codex 섹션).

### 우선순위 묶음

**그룹 1 — 손상 정책 통일** (IMP-2 + IMP-3 + IMP-4 + IMP-9)

`_load_from_json` 검증 4개 경로(scope/items 길이/tabBeepIdx 타입/key 타입)를 한 정책으로 통일. 정책 통일이 가장 큰 가치 — 4 발견 중 3개가 같은 카테고리이므로 한 번 작업으로 묶음 처리.

**그룹 2 — 메모리/디스크 일관성** (IMP-1)

`set_aliases`/`move_item`을 `save()` 패턴으로 정렬. 양측 동의 1건이라 강한 권고. 단위 테스트 보강 동반.

**그룹 3 — GUI 모달 일관성** (IMP-7 + IMP-8)

listDialog의 5개 wx.MessageBox를 `wx.MessageDialog` 컨텍스트 매니저로 통일 + alias 편집 다이얼로그의 빈 입력 안내 보강. NVDA 사용자 경험 개선.

**그룹 4 — 빌드 패키지 정합** (IMP-6)

`readme.html` 추가 또는 `manifest.ini`의 `docFileName` 제거. 작은 작업이지만 사용자가 도움말 진입 시도하면 즉시 깨지므로 빠른 처리.

### IMPROVEMENTS.md 동기화

사용자 채택 후 그룹 1~4를 "현재 로드맵"에 Phase R6(가칭 — 손상 정책 통일) / Phase R7(메모리/디스크 일관성) / Phase R8(GUI 모달) / 빌드 메타데이터 fix로 후속 후보 추가 권장.

## 10. 메타데이터

- Codex 결과 raw: `/tmp/codex-review-20260501-155244.json` (~/.claude/codex-reviews/2026-05/ sync 대상)
- 토큰 사용량: Codex 141,268 (high effort). Claude 4트랙 합계 약 308,512 (78,175 + 68,982 + 76,845 + 84,510)
- 페어 리뷰 총 비용 시각: 약 ~450K 토큰 / 단일 시각의 약 4-5배 — 발견 28건 중 양측 동의 1건의 신뢰도 가중 + 보완적 4건(코드 외부)이 그 비용의 정당화
- 첫 페어 리뷰 시도. 후속 리뷰는 변경분 대비 `--uncommitted` 또는 `--base master`로 더 작은 범위로 진행 가능.
