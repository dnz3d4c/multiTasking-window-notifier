# 시니어 6인 토론식 코드 리뷰 — multiTaskingWindowNotifier (2026-04-20)

## 메타

- **대상**: `globalPlugins/multiTaskingWindowNotifier/` 전체 Python 코드 + `manifest.ini`
- **현재 상태**: Phase 9.2까지 완료 (v9 마이그레이션, normalize_title 4단계 파이프라인, 5 프리셋)
- **방식**: 시니어 20년차 6인 페르소나 라운드 왕복 토론. 각 쟁점마다 **반대 의견 최소 1명**, 모든 의견은 **파일:라인 근거** 동반.
- **원칙**: 기존 기능 회귀 방지가 절대 조건. 수정은 별도 Phase(I-P0~P2)에서 진행하며 `@NVDA Addon Development Specialist` 리뷰 + `build.py` 재빌드가 관문.

### 참가자

| # | 페르소나 | 핵심 입장 |
|---|---------|-----------|
| 1 | **김아키** | 책임 분리, 결합도 감소, 관심사 분리 |
| 2 | **박성능** | 핫패스 성능, NVDA가 이미 보장하는 것 신뢰 |
| 3 | **이안전** | 예외/로그/부분 실패 대비, 방어 프로그래밍 |
| 4 | **정실용** | YAGNI, 과잉 추상화 비판, 관용 존중 |
| 5 | **최접근성** | NVDA 관행, i18n 엄수, 사용자 경험 |
| 6 | **한유지** | 일관 네이밍, DRY, 문서화 |

### 우선순위 기준

- **P0**: 기존 기능 오동작 가능성 있음 또는 NVDA 관행 명시 위반
- **P1**: 유지보수성·안정성 개선, 회귀 위험 낮음
- **P2**: 스타일·네이밍·문서화, 선택적

---

## A. 구조 / 책임 분리

### A1. Matcher가 GlobalPlugin 인스턴스를 참조하는 결합도

**발제자(김아키)**: `matcher.py:49-50`에서 `self._plugin = plugin`로 저장하고 `plugin.appList`, `plugin._lookup.windowLookup`, `plugin._lookup.appLookup`, `plugin.appListFile`, `plugin._meta_for(matched_key)`, `plugin._flush_scheduler` 6개 속성을 참조한다(`matcher.py:79, 93, 120-122, 137, 215-217`). `_lookup`·`_flush_scheduler`는 private인데도 Matcher가 뚫고 들어간다. 의존성 주입(DI)이나 이벤트 패턴으로 정리하자.

**찬성(한유지)**: 문서화 관점에서도 "Matcher가 plugin 내부 private를 읽는다"는 사실이 코드 리뷰어에게 매번 재발견됨. 생성자에 `appList_getter`, `lookup`, `flush_scheduler`, `meta_provider`, `app_list_file` 5개 의존성을 명시 주입하면 "이 객체가 읽는 것"이 시그니처에서 바로 보인다.

**반대(정실용)**: **`matcher.py:10-16` 모듈 docstring이 이미 "역방향(Matcher → GlobalPlugin) 의존은 이 4개뿐. 반대는 없다"고 명시적 설계 의도로 선언**한다. 단방향 + 의존 목록이 작게 고정되어 있으면 DI 도입의 이점(테스트 용이성, 대체 구현)이 실제로 쓰이지 않는 한 과잉 추상화. NVDA 애드온에 Matcher의 대체 구현이 생길 시나리오가 없다.

**제3 관점(박성능)**: 핫패스(`event_gainFocus` 초당 다회 호출) 성능 관점에서 의존성 바인딩 함수 호출 1단 추가는 무시 수준. 성능 반대는 없음. 다만 **테스트에서 이미 `matcher.last_event_sig` 직접 대입으로 리셋**(`matcher.py:45-46 주석`)하는 관행이 정착되어 있어, 지금 생성자 시그니처 뜯어고치면 기존 테스트 광범위 수정.

**이안전**: 롤백 리스크 측면 — Matcher 리팩토링은 이벤트 훅 최상위 레이어와 직결. 회귀 시 3분기 매칭 전체가 망가짐. P0/P1 수정할 때 동시에 건드리면 회귀 원인 분석 어려움.

**결정**: **P2** (선택적). 현재 단방향 + docstring 명시 의존 목록이 설계 의도이고 실질 피해 없음. **단, P2 착수 시에는 "생성자 파라미터만 추가하고 기존 plugin 참조는 그대로 두는 단계적 리팩토링"**(adapter 패턴)으로 회귀 위험 최소화. 현 시점 긴급성 없음.

---

### A2. `store/core._load_state`의 9단계 선형 마이그레이션 파이프라인

**발제자(이안전)**: `store/core.py:110-233`의 `_load_state`가 9단계(① 캐시, ② 경로, ③ JSON 로드 또는 legacy, ④ legacy 백업, ⑤ title normalize, ⑥ v7 비프 재배정, ⑥' v8 aliases, ⑥'' v9 backup+재정규화, ⑦ 캐시 등록). 각 단계가 `state["items"]`를 제자리 수정. **중간 단계 실패 시 부분 마이그레이션 상태가 메모리에 남고 디스크엔 아직 안 쓰인 어중간한 상황** 가능.

**찬성(한유지)**: 9단계가 단일 함수 본문에 선형 나열되어 있어 **"어느 단계에서 어떤 불변식이 보장되는가"를 주석으로만 추적**한다. 파이프라인 객체나 상태 머신으로 재설계하면 각 단계 이름·입출력이 코드로 드러남.

**반대(박성능)**: 코드를 실제로 읽으면 **멱등 재시도 설계**가 보임. `store/core.py:194-197`에서 `_normalize_titles_in_place` 변경이 있으면 `_save_to_disk` 시도 → 성공 시만 `dirty=False`. 실패 시 **`dirty=True`가 유지되어 다음 `flush()`에서 자연 재시도**. `store/core.py:225-229`도 동일 패턴. 트랜잭션/롤백 없이 **"디스크 쓰기 실패는 다음 기회에"** 로 설계됐고, `_ensure_beep_assignments`·`normalize_title` 모두 멱등이라 N회 재시도해도 결과 동일. 상태 머신으로 뜯어내면 "같은 구조를 더 어렵게" 쓰는 리팩토링.

**정실용**: v6→v7→v8→v9 연쇄가 "한 번 쓰고 끝"인 1회성 데이터 마이그레이션 로직. 장기적으로 v9가 굳으면 v6~v8 경로는 dead code로 전환. **리팩토링 투자비 회수가 어렵다**. 비프 테이블 다음 세대 변경(v10)이 생기면 그때 같은 선형 단계 하나 더 추가하면 됨.

**김아키**: 멱등 재시도는 맞지만 **"디스크가 실패 중인 상태에서 `load()`가 반환한 key 리스트로 매칭이 일어나면?"** `store/core.py:239-242` `load()`는 `state["items"]`에서 key만 뽑아 반환. 마이그레이션 변경이 적용된 **메모리 상태**로 매칭 동작 → 디스크와 메모리 일시 괴리. 다행히 `_save_to_disk` 실패 빈도가 극저라 실용 문제 없음.

**최접근성**: 사용자 체감 영향 없음. corrupted app.json 감지(`is_corrupted`, `store/core.py:155`)는 빈 상태로 초기화 + 사용자 delayedMessage 안내(`__init__.py:96-101`)로 명시적 처리되고 있어 **침묵 실패가 아니다**.

**결정**: **P1** (리팩토링 대상은 아니나 **주석 보강**만). 현재 멱등 재시도 설계가 적절하고 롤백·트랜잭션 도입은 YAGNI. 다만 **`_load_state` 시작부에 "각 단계 실패 시 `dirty=True` 유지 → 다음 flush 재시도"라는 정책을 한 단락 주석으로 명시**해 미래 개발자가 트랜잭션 도입 유혹을 받지 않게 방어.

---

### A3. `__init__.py`의 손상 알림 로직 분리 가능성

**발제자(김아키)**: `__init__.py:96-101`의 "손상된 app.json 감지 시 `ui.delayedMessage`" 블록이 GlobalPlugin 초기화 본문에 직접 박혀 있다. `store.is_corrupted()` 조회 + 메시지 출력은 "부팅 알림" 헬퍼 한 함수로 뽑아낼 수 있다.

**찬성(한유지)**: 함수 이름이 "무엇을 언제 알리는가"를 선언. 지금은 본문 읽어야 이해.

**반대(정실용)**: **4줄짜리 블록을 함수로 뽑는 건 가독성 손실**. "부팅 시 손상 감지되면 사용자에게 한 번 안내"라는 로직이 초기화 문맥 안에 그대로 보이는 게 더 명확. `def _warn_if_corrupted(self):` 한 단계 심화는 미래 "다른 알림이 더 생길 때" 하면 됨. 지금은 너무 일러.

**박성능**: 동의. 이건 YAGNI 영역.

**결정**: **No-Op**. 현재 구조 유지. P2 후보에도 넣지 않는다.

---

## B. 중복 / 일관성

### B1. `normalize_title` + empty-check 5곳 반복

**발제자(한유지)**: 5곳에서 동일 패턴 반복.
- `focusDispatcher.py:65` → `title = normalize_title(raw_title); if not title: return`
- `nameChangeWatcher.py:64` → 동일
- `foregroundWatcher.py:60` → 동일
- `scripts.py:223, 386` → normalize만(empty-check는 다른 형태)
- `windowInfo.py:55` → normalize만

래퍼 `normalize_and_skip_if_empty(raw)` 하나 만들면 3개 이벤트 훅 경로가 한 줄로 줄어든다.

**찬성(정실용, 드물게)**: 3곳(세 이벤트 훅)만 정확히 동일 패턴. 거기만 래핑하면 `if normalize_title(raw): ... return` 한 줄로 끊어짐.

**반대(김아키)**: 각 호출처의 **맥락이 다르다**. focusDispatcher는 3분기 중 현재 분기에서 raw_title을 뽑은 직후, nameChangeWatcher는 foreground 본체 title 변경 감지 후, foregroundWatcher는 새 foreground obj.name에서. 공통 래퍼로 묶으면 **"왜 return하는가"의 맥락이 사라짐**. 특히 scripts.py와 windowInfo.py는 normalize만 하고 empty-check는 각자 다른 로직(등록 실패 메시지 출력 vs 조용히 빈 문자열 반환)이라 묶기 어려움.

**박성능**: 성능 차이 없음.

**이안전**: 래핑하면 스택 한 단계 깊어짐 → 디버깅 시 로그 라인 일관성 유지 어려움(각 훅이 `log.exception`을 자기 이름으로 남김).

**결정**: **P2** (선택적). `focusDispatcher`/`nameChangeWatcher`/`foregroundWatcher` 세 곳만 예외적으로 동일 패턴이지만 래핑으로 얻는 이점이 작고 맥락 소실 우려. **현 상태 유지하되 각 훅 상단에 `# raw_title → normalize → empty 조기 탈출` 한 줄 주석을 공통 문구로 통일**해 독자가 세 곳이 같은 관례임을 즉시 인지하게 하는 선에서 마무리.

---

### B2. 3개 이벤트 훅의 try/except/finally 구조 반복

**발제자(한유지)**: `__init__.py:155-194`에서 3 훅이 완벽히 동일 구조.
```python
try:
    <dispatcher>.<handle>(self, obj)
except Exception:
    log.exception("mtwn: event_<name> failed")
finally:
    nextHandler()
```
decorator 하나로 추상화 가능.

**찬성(김아키)**: 이런 decorator는 NVDA 이외 Python 생태계 관용이다. `@ensure_next_handler("gainFocus")` 같은 형태.

**반대(이안전)**: **NVDA 이벤트 훅 시그니처 `(self, obj, nextHandler)`는 NVDA 코어 레벨에서 이름으로 인식**된다. Decorator로 `*args, **kwargs` 래핑하면 NVDA가 시그니처 검사할 때 문제 소지. 설령 동작해도 **스택 트레이스가 decorator 한 단계 깊어져** 훅 예외 디버깅 시 헤맴.

**박성능**: NVDA가 이벤트 훅을 바인딩하는 방식(`eventHandler.py`의 `executeEvent`)은 객체의 속성 조회로 이름 참조. decorator가 `functools.wraps`로 이름 보존하면 이론상 가능하지만 **검증 부담이 이득 대비 큼**.

**정실용**: 9줄 × 3개 훅 = 27줄을 decorator로 줄이는 이익이 "훅 한 개 추가할 때 9줄 타이핑 절약"인데 훅 추가 빈도가 거의 0. YAGNI.

**최접근성**: NVDA 다른 애드온 수십 개 전수 조사해도 이 decorator 패턴 쓰는 곳 없음. **관용을 따르는 게 이후 기여자 진입 장벽 낮춤**.

**결정**: **No-Op**. 도입하지 않는다. 이 중복은 "명시적 중복이 낫다"의 모범 사례. 토론 결과 자체를 리뷰 문서에 남겨 "왜 유지했는가"를 기록.

---

### B3. `makeAppKey(appId) = appId` 래퍼 함수 정당성

**발제자(정실용)**: `appIdentity.py:51-57`의 `makeAppKey(appId)`는 `return appId` 한 줄. 호출처는 `scripts.py:199` 1곳뿐. 이 래퍼가 왜 존재?

**찬성(김아키, 이 경우는 반대의 반대)**: **대칭성** — `makeKey(appId, title)` / `splitKey(entry)`와 묶어 "scope=app 키를 만드는 공식 경로"를 타입으로 명시. `scripts.py:199` 호출이 `new_key = appId`로 바뀌면 **"앱 scope 키를 대입한다"는 의도가 코드에서 사라짐**.

**찬성(한유지)**: 향후 scope=app 키 포맷이 바뀔 때(예: `"app:<appId>"` 접두사 추가) 단일 수정 지점.

**반대(정실용)**: 지금까지 한 번도 바뀐 적 없고, `matcher.py:80-82`에서 SCOPE_APP이면 `real_app_id = matched_key`로 **이미 "복합키 파싱 없음" 관행이 코드 전체 정착**. 포맷이 바뀌면 `splitKey` + `matched_key` 로직도 같이 바뀌어야 해서 단일 수정 지점 이점이 허구.

**박성능**: 성능 중립.

**이안전**: YAGNI 관점에서 제거 찬성. 다만 **제거하면 import/호출 1회 삭제인데 git log 1줄밖에 남지 않아 "왜 제거?"의 추적성 낮음**. 결정 문서화가 필요.

**결정**: **P2** (선택적). 제거 가능하나 이익 미미 + 대칭성 설명력 약간의 가치. **현 상태 유지**하되 `appIdentity.py:51-57`에 "대칭성 유지를 위해 의미 없는 래퍼를 남긴다. scope=app 키 포맷이 바뀌면 여기가 단일 수정 지점" 주석 1줄 보강. 주석 보강 자체는 P2 착수 시 같이.

---

## C. 안정성 / 에러 처리

### C1. `_states` 모듈 캐시 스레드 안전성

**발제자(이안전)**: `store/core.py:99`의 `_states = {}` 모듈 레벨 dict. 접근부(`load`, `save`, `record_switch`, `flush`, `reload`, `get_meta`, `get_app_beep_idx`, `get_tab_beep_idx`, `set_aliases`, `is_corrupted`)는 **10개 공개 API + `_load_state` 내부 캐시 체크**. Lock 없음. 명시적 스레드 안전성 선언도 없음.

**찬성(김아키)**: 향후 `threading.Thread`로 백업 작업 추가하거나 NVDA의 다른 스레드에서 호출되면 경합.

**반대(박성능)**: NVDA의 이벤트 훅은 **기본적으로 main thread(wx GUI 스레드)에서 순차 호출**(`eventHandler.py`의 `executeEvent`). `@script` 핸들러도 동일. `_states` 접근은 **단일 스레드 직렬**이고 GIL 보호도 덤. **현 코드 경로에서 경합은 이론상 0**. threading 도입하는 순간에 Lock 걸면 됨.

**정실용**: Lock 선제 도입 = YAGNI. 심지어 **CPython dict는 GIL로 보호돼 `dict[k] = v` / `dict.get(k)` 단일 연산은 아토믹**. 복합 연산(check-then-act)만 문제인데 현재 `_states[list_path] = state`는 단일 대입.

**한유지**: 문서화 관점에서는 `store/core.py:89-99` 상단에 **"호출자는 NVDA main thread 전제"** 주석 한 줄이면 미래 기여자가 threading 도입하기 전 주의.

**이안전**: 동의. 주석으로 가정 명시 + threading 도입 시점에 Lock 추가는 합리적.

**결정**: **P2** — `_states` 정의 바로 위에 "**동시성 가정: NVDA main thread 단일 소유. threading 도입 시 `threading.Lock`으로 감싸거나 copy-on-read 전략 검토**" 주석 1~2줄 보강. Lock 도입은 안 함.

---

### C2. Matcher 2중 dedup 정책의 상호작용

**발제자(이안전)**: `matcher.py:54-62`에서 3상태 보유.
- `last_event_sig`: (appId, title, tab_sig) 연속 동일 흡수 (이벤트 식별자)
- `_last_matched_key` + `_last_match_time`: 같은 매칭 key 0.3초 내 재진입 (사용자 행동)
- `_octave_toggle`: 같은 key 재진입 시 ±7 옥타브 토글

`matcher.py:145-155` 주석이 "리셋 정책 독립"을 명시하지만, **A → 미스 창 → A 복귀** 케이스에서:
- `last_event_sig`는 미스에서 None 리셋(`matcher.py:154`)되므로 재진입 A 통과
- `_last_matched_key`는 A 유지되므로 `is_repeat=True` 판정 → `suppressRepeat`·`octaveVariation` 적용

이게 설계 의도인 것은 주석으로 명시되어 있지만, **실제 관측 가능한 케이스에서 예상 밖 동작**일 가능성 있음.

**찬성(박성능)**: **설계 의도 명확** — `matcher.py:150-153` 주석이 "사용자 관점에서 같은 창 빠른 복귀는 반복"이라고 선언. pentatonic 프리셋의 `suppressRepeat=True`(`presets.py:148`) 활성 사용자는 이 동작을 원한다. 제거/통일하면 **의도된 기능 후퇴**.

**반대(이안전)**: 그래도 **테스트 커버리지**가 이 교차 시나리오를 명시적으로 검증하는지 불확실. A→미스→A와 A→B→A 차이가 기댓값 문서화되어 있는가?

**최접근성**: pentatonic 사용자는 청각 변별 개선이 목적. `suppressRepeat`/`octaveVariation` 플래그의 실동작이 일정하면 된다 — 복잡도는 내부 문제.

**정실용**: 설계가 명시되어 있고 사용자 기능이 의도대로 동작하면 충분. 내부 일관성 집착은 과잉.

**김아키**: **상태 3개는 많다**. `_last_matched_key`만 있으면 되고 `_octave_toggle`은 파생 가능(`_last_matched_key`가 바뀌면 0으로 리셋). 단 이것도 리팩토링 범위가 커서 회귀 위험. 지금 수정은 보류.

**결정**: **P2** — **토론에서 합의된 "의도된 독립 정책"을 리뷰 문서로 기록**하고, 테스트 스위트에 **A→미스→A / A→B→A 기댓값 케이스** 추가하는 것은 차기 수정 Phase 후보. 지금 당장 코드는 건드리지 않음.

---

### C3. `None` early return 로깅 부재

**발제자(이안전)**: 3곳에서 `None` 체크 후 silent return.
- `focusDispatcher.py:53` `if obj is None: return`
- `nameChangeWatcher.py:42-46` obj / fg `None`
- `foregroundWatcher.py:50-58` obj / appId

실패 재현이 어려움. debug log 한 줄이라도 있으면 trace.

**찬성(박성능)**: `debugLogging` 설정 켠 사용자만 로그 보게 하면 핫패스 영향 없음 — `settings.get("debugLogging")` 체크 후 `log.debug` 호출.

**반대(정실용)**: `None` early return은 **"NVDA 부팅 초기 또는 윈도우 사이 틈에 일시적으로 발생하는 정상 경로"**. 여기에 로그 남기면 **정상 상황 로그 폭주** → "이상하다" 느끼게 하고 진짜 이슈 묻힘.

**최접근성**: NVDA 관행상 `api.getForegroundObject()` None 반환은 드물지만 존재(시스템 전환 과도기). 이런 건 로그 안 쓰는 게 관용.

**한유지**: **"정상 경로"라는 것이 주석으로 명시되어 있지 않다**. 3곳에 각각 `# 부팅/전환 과도기 None 가능. 정상 경로.` 한 줄 주석 추가하자.

**김아키**: 동의. 코드 수정 없이 주석으로 해결.

**이안전**: 주석 타협안 수용. 단 `nameChangeWatcher.py:55-56`의 **int 변환 `except Exception: return`**(로그 없음)은 real 예외 가능성 있으므로 `log.debug("mtwn: nameChange hwnd coerce failed")` 정도는 추가.

**결정**: **P1** (경미). 3곳 `None` early return은 주석으로 명시(P2 수준). `nameChangeWatcher.py:55-56`의 int 변환 예외만 `log.debug` 한 줄 추가(P1).

---

## D. NVDA 관행

### D1. `ui.message` 문자열의 `_()` 번역 래퍼 일부 누락

**발제자(최접근성)**: `scripts.py`의 `ui.message` 호출에서 **번역 래퍼 누락 다수**.

| 위치 | 현재 | 문제 |
|------|------|------|
| `scripts.py:127` | `ui.message("창 제목을 확인할 수 없어요.", ...)` | `_()` 미적용 |
| `scripts.py:136` | `ui.message("이미 창과 앱 둘 다 목록에 있어요.", ...)` | `_()` 미적용 |
| `scripts.py:192, 197` | `"이미 목록에 있어요."` | `_()` 미적용 |
| `scripts.py:205-208` | `"목록이 가득 찼어요..."` | `_()` 미적용 |
| `scripts.py:214-217` | `"앱 목록을 저장하는 중 문제가 생겼어요..."` | `_()` 미적용 |
| `scripts.py:228-232` | alias 저장 실패 메시지 | `_()` 미적용 |
| `scripts.py:242-244` | `"앱 전체로 추가했어요: %s" % appId` | **전체를 `_()` 밖에 둠 + % 포맷** |
| `scripts.py:247-249` | `"창으로 추가했어요: %s | %s" % (appId, title)` | 동일 |
| `scripts.py:252-254` | `"대체 제목도 저장했어요: %s"` | 동일 |
| `scripts.py:269, 286, 291-294, 298, 300` | 삭제 경로 메시지들 | `_()` 미적용 |
| `scripts.py:313-316` | reload 안내 f-string | f-string에 한글 박힘, `_()` 미적용 |
| `scripts.py:326, 343-346, 361-364` | showAllEntries / bulk delete 안내 | `_()` 미적용 |
| `scripts.py:389-392, 402-404, 407-410` | alias 편집 결과 안내 | `_()` 미적용 |
| `__init__.py:99-101` | `ui.delayedMessage("앱 목록 파일이 손상되어...")` | `_()` 미적용 |

반면 **다이얼로그 prompt + @script description + `scriptCategory` + `settingsPanel` 위젯 라벨은 전부 `_()` 적용**(`scripts.py:77-80, 115, 120, 262, 304, 320`, `settingsPanel.py` 전체).

**찬성(한유지)**: gettext 추출 도구(xgettext/Babel)가 **정적 분석으로 `_()` 호출만 번역 대상으로 인식**. 현재 상태는 **번역 작업 자체가 불가능**. 이건 NVDA 관행 명시 위반.

**반대(정실용, 소극적)**: **애드온이 현재 한국어 단일 사용자 기반**으로 배포되고 있고, `manifest.ini:3`의 description도 한글 원문. 번역 파일(`locale/`)도 프로젝트에 없다. **지금 당장 실 이익 없음**. 다만 NVDA 공식 애드온 제출하려면 필수이긴 함.

**박성능**: `_()` 래핑 자체는 no-op + dict lookup 1회. 핫패스 영향 0.

**김아키**: **엄격하게 래핑하는 게 장기 비용 절감**. 지금 30곳 수정 vs 나중에 번역 시작할 때 100곳 추적.

**이안전**: 기능적으로 `_()`는 영어 환경에서 identity 함수이므로 **수정으로 인한 회귀 위험 극히 낮음**. 다만 `%` 포맷팅 위치(바깥 vs `_()` 내부) 정책은 합의 필요.

**최접근성 결론**: 래핑 방식은 `_("템플릿 {placeholder}").format(placeholder=값)` 형태 권장. 이유:
1. 번역자가 `{placeholder}` 위치를 자유롭게 배치(언어별 어순 다름)
2. `%s` 방식은 순서 의존이라 언어별 어순 맞추기 어려움
3. gettext 표준 관행

**결정**: **P0** — 기능적 회귀 위험 낮음 + NVDA 관행 명시 위반. 래핑 방식은 **`_("템플릿 {var}").format(var=값)` 표준 적용**. 모든 `ui.message` + `ui.delayedMessage` 사용자 대면 문자열 대상. log 메시지(`log.info`, `log.warning`, `log.exception`)는 **영문 유지** — 개발자용이지 사용자 대면 아님.

---

### D2. `manifest.ini`의 `minimumNVDAVersion = 2019.3.0`

**발제자(최접근성)**: `manifest.ini:6`의 `minimumNVDAVersion = 2019.3.0`. 2019.3은 7년 전 릴리스. 코드가 `baseObject.ScriptableType`(`scripts.py:38`), `guiHelper.BoxSizerHelper`(`settingsPanel.py`), `gui.settingsDialogs.NVDASettingsDialog.categoryClasses`(`__init__.py:64`) 등 **현대 API 사용**. 2019.3에서 실제 동작 검증이 됐는가?

**찬성(한유지)**: 솔직한 값으로 업데이트하는 게 사용자 기대치 정확. 동작 안 하는 NVDA에서 설치되면 오히려 나쁨.

**반대(박성능)**: **하한선 올리는 건 사용자 일부를 내쫓는 파괴적 변경**. 구형 NVDA 사용자(시각장애 사용자는 버전 업데이트 주저하는 경우 많음) 중에 이 애드온 의존자가 있으면 손해. 일단 **현재 작동 중인 설치분은 유지**하고 "2023.1+"로 올리려면 **실 사용자 통계 확인 선행**.

**정실용**: 통계 데이터 없이 하한선 결정은 추측. `manifest.ini:7`의 `lastTestedNVDAVersion = 2026.1.0`만 최신 유지하면 상한 검증은 충분.

**이안전**: **`ScriptableType`은 NVDA 2019.3에 존재**(git log로 확인 가능). 문제 없을 수 있음. 실제로 2019.3 기준 설치 시도해봐야 검증.

**김아키**: 실 검증 없이 숫자만 올리는 건 무책임. 실 검증하려면 VM에 NVDA 2019.3 설치 + 본 애드온 로드 테스트 필요. 이건 현재 플랜 범위 밖.

**최접근성**: 동의. 숫자 변경은 보류하되, **README 또는 문서에 "검증된 NVDA 버전 범위"를 lastTestedNVDAVersion 기준으로 명시**는 가능.

**결정**: **No-Op** (manifest.ini 수정 없음). 하한선 변경은 실 검증 선행 필요 + 사용자 파급 있어 별도 플랜에서 처리. 현 리뷰에서는 결정하지 않음.

---

### D3. `PRESETS`의 `durationMs` / `gapMs` 필드가 실제 재생에 반영되지 않음

**발제자(정실용)**: `presets.py:128-129`(classic), `presets.py:141-142`(pentatonic), `presets.py:159-160`(fifths), `presets.py:179-180`(soft_retro), `presets.py:196-197`(moss_bell) 모든 프리셋이 `"durationMs": 50, "gapMs": 100` 보유. 그러나 **`matcher.py:210-214`는 항상 `settings.get("beepDuration")` / `settings.get("beepGapMs")`만 사용**. 프리셋 필드는 **어디서도 읽히지 않는다**.

**찬성(한유지)**: Dead field. 사용자가 프리셋 바꿔도 duration/gap은 사용자 설정값 그대로. 필드 존재 자체가 거짓 약속.

**찬성(최접근성)**: **프리셋 캐릭터 완성도 관점에서는 활용하는 게 맞다** — pentatonic "Calm"은 더 긴 gap이, fifths "Fanfare"는 짧은 duration이 성격에 맞음.

**반대(박성능, 소극적)**: 활용하려면 `matcher.py`의 duration/gap 주입 로직을 `preset.get("durationMs", settings.get("beepDuration"))` 우선순위로 바꿔야 하는데, **사용자가 설정 패널에서 수동 조정한 값을 프리셋이 덮어쓰면 혼란**. 우선순위 설계 합의 필요.

**정실용**: **두 옵션 중 하나 선택** — (가) 필드 활용: 프리셋의 duration/gap을 default로, 사용자 조정 시에만 override. UI/로직 복잡도 증가. (나) 필드 제거: 5줄 × 2(duration+gap) = 10줄 제거. 단순. **현재 리소스에서는 (나)가 맞다**.

**김아키**: (나) 찬성. YAGNI — 아직 활용 안 하고 활용 계획도 없음.

**이안전**: (나) 찬성. 회귀 위험 0(어차피 읽지 않는 필드 제거).

**최접근성**: 아쉽지만 (나) 수용. 프리셋 캐릭터 구현은 **freqs + waveform + suppressRepeat + octaveVariation**으로 이미 충분히 차별화됨. duration/gap까지 프리셋별로 가지 않아도 됨.

**한유지**: (나) 찬성 + `presets.py:17-28` 모듈 docstring의 `durationMs / gapMs` 설명도 같이 제거해 **"dict 포맷 문서와 실제 일치"** 확보.

**결정**: **P0** — 필드 + docstring 라인 제거. 총 10 + 2 = 12줄 삭제. 기능 변화 0. NVDA 리뷰에서 "문서와 실제 불일치" 지적 대상.

---

## 우선순위 요약

| # | 쟁점 | 우선순위 | 수정 범위 | 회귀 위험 |
|---|------|---------|----------|----------|
| D1 | `ui.message` 등의 `_()` 누락 | **P0** | scripts.py 약 30곳 + __init__.py 1곳. `_("...{var}").format(var=값)` 적용 | 낮음 (`_()`는 영어 환경 identity) |
| D3 | PRESETS durationMs/gapMs 미사용 필드 제거 | **P0** | presets.py 10줄 + docstring 2줄 | 0 (읽지 않는 필드) |
| A2 | `_load_state` 멱등 재시도 정책 주석 보강 | **P1** | store/core.py 시작부 4~6줄 주석 | 0 (주석만) |
| C3 | `nameChangeWatcher` hwnd int 변환 `log.debug` + 3곳 early return 주석 | **P1** | nameChangeWatcher.py 1줄 log + 3곳 주석 | 낮음 |
| A1 | Matcher ↔ GlobalPlugin 결합 해소 | **P2** | 생성자 파라미터 추가(단계적) | **중** (매칭 핫패스) — 착수 시 신중 |
| B1 | normalize_title 3 훅 주석 통일 | **P2** | 3곳 주석 | 0 |
| B3 | makeAppKey 주석 보강 | **P2** | 1곳 주석 | 0 |
| C1 | `_states` 스레드 가정 주석 | **P2** | store/core.py 2줄 주석 | 0 |
| C2 | Matcher 3상태 테스트 케이스 추가 | **P2** | 테스트 추가(없으면 신설) | 0 |
| A3 | 손상 알림 분리 | **No-Op** | — | — |
| B2 | 이벤트 훅 try/except decorator | **No-Op** | — | — |
| D2 | manifest minimumNVDAVersion | **No-Op** (실 검증 선행) | — | — |

**P0/P1/P2 총 쟁점 수**: P0=2, P1=2, P2=5, No-Op=3.

---

## 회귀 방지 체크리스트

수정 착수 전·후로 반드시 수동 검증할 시나리오. 어떤 P0/P1/P2 수정이라도 **해당 항목 재확인 없이는 "완료" 선언 금지**.

### Scenario 1: 매칭 3경로 (focusDispatcher 3분기)

- [ ] **Alt+Tab 오버레이** (`Windows.UI.Input.InputSite.WindowClass`): Alt+Tab 탐색 중 각 후보마다 비프 재생
- [ ] **앱별 오버레이** (Notepad++ MRU `#32770`): Ctrl+Tab MRU 탐색 중 각 후보마다 비프
- [ ] **에디터 자식 컨트롤** (메모장 `RichEditD2DPT` / Notepad++ `Scintilla`): Ctrl+Tab 확정 전환 시 `foreground.name` 기반 비프

### Scenario 2: 2음 비프 (scope=window)

- [ ] 같은 앱 다른 창 2개 등록 → 각 창 포커스 시 **앱 공통 a음 + 창별 b음** 2음 재생
- [ ] `gap_ms` 설정값(기본 100ms) 반영 확인: 두 음 사이 간격
- [ ] `duration` 설정값(기본 50ms) 반영 확인
- [ ] scope=app 단일 등록은 **a음 단음**만 재생

### Scenario 3: 마이그레이션 연쇄 (v6→v7→v8→v9)

- [ ] v6 app.json으로 부팅 → v7 온음계 테이블 기준 재배정 + v8 aliases=[] 주입 + v9 재정규화 + `app.json.v8.bak` 백업
- [ ] v7 app.json → v8→v9 자동 승격 (비프 재배정 없음)
- [ ] v8 app.json → v9 aliases 재정규화 + .v8.bak 백업(첫 회만)
- [ ] v9 app.json 재부팅 → no-op
- [ ] legacy app.list만 있는 경우 → v9 JSON으로 한 번에 변환 + app.list.bak 생성

### Scenario 4: 단축키 4종

- [ ] **NVDA+Shift+T**: scope 선택 + alias 입력 + `_do_add` 성공. 스코프 이미 등록 시 꼬리표(`이미 등록됨`) 표시. 128 상한 안내.
- [ ] **NVDA+Shift+D**: 정확 매치만 삭제. 창 우선 앱 fallback. 다른 앱 동일 title 오삭제 없음.
- [ ] **NVDA+Shift+R**: flush → 캐시 무효화 → 재로드. 개수 음성 안내.
- [ ] **NVDA+Shift+I**: 다중 선택, Delete 키, 앱 일괄 삭제 확인 다이얼로그, 단일 선택 시 alias 편집 버튼(E).

### Scenario 5: 설정 패널

- [ ] 프리셋 5종(classic/pentatonic/fifths/soft_retro/moss_bell) 각각 미리듣기 정상
- [ ] 프리셋 전환 즉시 다음 매칭부터 새 freqs 적용
- [ ] 음 길이(duration) 슬라이더 반영
- [ ] 음 간격(gap) 슬라이더 반영
- [ ] 볼륨(hybrid 프리셋만 영향) 슬라이더 반영
- [ ] `debugLogging` 체크박스: 로그 ON 시 `focusDispatcher gF`·`sig_guard skip` 등 디버그 라인 생성 / OFF 시 없음

### Scenario 6: 손상 app.json 감지

- [ ] app.json을 일부러 손상시킨 후 NVDA 재시작 → `ui.delayedMessage`로 "손상되어 빈 상태로 시작" 안내
- [ ] 이후 NVDA+Shift+T로 새 항목 추가 → 정상 저장 + 손상 플래그 해소 (`state["corrupted"] = False`)

### Scenario 7: alias 매칭 (카카오톡 케이스)

- [ ] scope=window 항목에 alias 설정 → Alt+Tab 오버레이에서 alias 이름으로 매칭 시 **해당 entry의 앱 a음 + 탭 b음** 정상
- [ ] scope=app 항목에 alias 설정 → Alt+Tab 오버레이에서 alias 이름으로 매칭 시 **단음** 정상
- [ ] alias 편집 시 `set_aliases` 즉시 저장 + `_rebuild_lookup` 호출로 다음 매칭 반영

### Scenario 8: dedup / 반복 억제 / 옥타브 변주

- [ ] 같은 창 포커스 유지 중 자식 컨트롤 재진입 → sig_guard로 비프 skip(매 자식마다 울리지 않음)
- [ ] A→B→A 빠른 왕복: pentatonic 프리셋 suppressRepeat 활성 시 A 복귀에서 **앱음만** 단음
- [ ] A→B→A 빠른 왕복: pentatonic의 octaveVariation으로 A 복귀의 b음이 ±7 shift(옥타브 위/아래)로 전환
- [ ] A→미스 창→A 복귀: `last_event_sig` 리셋되어 통과, `_last_matched_key`는 A 유지되어 suppressRepeat/octaveVariation 적용

---

## 결론

이 프로젝트는 **NVDA 이벤트 훅 관행·핫패스 최적화·마이그레이션 설계 관점에서 매우 높은 성숙도**를 보인다. 특히 Phase R 리팩토링 이후의 "NVDA 재방어 금지" 원칙이 깨끗하게 적용되어 있고, `event_sig` 기반 dedup + 3 훅 책임 분리로 **단순화와 안정성을 동시에 확보**했다.

본 리뷰에서 발견한 쟁점 12건 중 **실 사용자 기능에 영향 있는 것은 P0 2건(D1 번역 래퍼, D3 dead field)만**이고, 나머지는 **주석 보강·테스트 추가·선택적 리팩토링** 수준이다. 이는 코드 품질이 이미 관리 수준에 있다는 강한 시그널.

### 권장 실행 순서

1. **I-P0**: D1(번역 래퍼) → D3(dead field 제거) — 각각 NVDA 리뷰 + 빌드 + 체크리스트 Scenario 4·5·7 재확인
2. **I-P1**: A2(주석) + C3(log.debug + 주석) — 묶음 커밋 가능, Scenario 1·3·6 재확인
3. **I-P2**: 사용자 재승인 후 A1(단계적) / B1·B3·C1·C2(주석·테스트) 순차

### 기록 남길 교훈

- **B2 이벤트 훅 try/except 중복은 의도적으로 유지**(NVDA 관용 준수 + 스택 투명성)
- **A1 Matcher 결합은 단방향 의존 + docstring 명시로 이미 수용 가능한 상태**
- **C2 Matcher 2중 dedup은 pentatonic 프리셋 기능의 의도된 구현**이며 단순화하면 기능 후퇴

이 토론 기록 자체가 "왜 건드리지 않았는가"의 미래 참조점.
