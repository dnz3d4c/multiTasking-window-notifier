# -*- coding: utf-8 -*-
# GNU General Public License v2.0-or-later

"""PCM 파형 합성 + wav 파일 캐시. Phase 3 신설 — 순수 함수 전용(+ 캐시 I/O).

Phase 3 이후 `beepPlayer`가 프리셋의 waveform 메타를 보고 이 모듈을 경유해
nvwave로 재생한다. 이 모듈은 의도적으로 `nvwave`/`config`/`settings`를 import
하지 않는다 — unit test 친화 + 계층 분리.

## 파일 기반 캐시 이유
NVDA `nvwave.playWaveFile`은 **문자열 파일 경로만** 받고 BytesIO/bytes는 거부
(`NVDA/source/nvwave.py:82-155`에서 `os.path.basename(fileName)` 등 호출).
따라서 합성 결과를 임시 wav 파일로 영속화한 뒤 경로를 넘긴다. 파일 자체가 캐시
역할 — 같은 (waveform, freq, duration, sample_rate) 조합은 모듈 dict에서 경로
즉시 반환, 신규 조합은 `tempfile.gettempdir()` 밑 전용 하위 폴더에 렌더링 후
경로 저장. 재시작 시 잔존 파일은 OS temp 청소가 정리.

## 생성 파형
- sine / square(pulse50) / pulse25 / pulse12 / triangle / saw
- noise (결정론적 `random.Random` 시드)
- 변조/엔벨로프(portamento/fm_wobble/vibrato/exp_decay/pluck/boing)는 Phase 4
  `synthSpecs` 스키마 도입 시 추가. 지금은 기본 파형만(Phase R3 교훈 — 실제 사용
  시점까지 예비 코드 보류).

## 성능 전략
- sine은 `math.sin` 호출을 정적 룩업 테이블(1024 entries) + 위상 누적으로 대체.
  44100Hz × 50ms = 2205 샘플을 CPython 루프로 돌려도 ms 단위.
- 결과는 (waveform_name, freq, duration_ms, sample_rate) 튜플 키로 캐싱.
  캐시 값은 파일 시스템의 **경로 문자열**(wav 파일 실체는 디스크에 존재).
  경로는 결정론적(해시 기반) — 같은 입력이면 같은 파일명, 동시 호출 경합 안전.
- 캐시 상한 `_CACHE_MAX=1024` 도달 시 FIFO 방식 한 개 제거 + 파일 unlink 시도
  (실패는 무시 — OS 청소에 위임).
- 동시성: 모듈 dict + `threading.Lock`. NVDA 메인 이벤트 스레드 외 다른 스레드가
  접근할 수 있는 미래(진단 덤프 등)에 대비.

## 한계
- 모든 파형은 진폭 ±0.8 스케일로 출력(클리핑 여유 +20%). gain 적용은 호출자 책임.
- duration_ms 하드캡은 두지 않는다. 호출자(beepPlayer/synthSpecs validator)가
  적정 범위를 강제.
- sample_rate 기본 44100Hz. nvwave.playWaveFile은 wav 헤더를 읽어 자동 대응하므로
  호출자가 다른 레이트를 원하면 인자로 넘길 수 있다.
"""

from __future__ import annotations

import array
import hashlib
import math
import os
import random
import tempfile
import threading
import wave

SAMPLE_RATE = 44100
_AMPLITUDE = 0.8

# Phase 6: 엔진 버전 suffix. 캐시 키에 포함해 §1 어택 램프/§2 파형 게인/§3 노이즈
# LPF 도입 이전 구 wav 파일과 자동 분리. 업그레이드 후 구 캐시는 OS temp cleanup
# 위임.
_ENGINE_VERSION = 2

# Phase 6 §1: 어택/릴리즈 램프. 모든 PCM 샘플의 양끝 1/2ms를 선형 보간으로 fade.
# 샘플 0에서 ±peak 계단 도약이 만들어내던 "클릭/팝" 트랜지언트를 제거해 전체
# 프리셋의 체감 날카로움을 크게 낮춘다. envelope이 있든 없든 최종 곱셈으로 적용.
# 초기 3/5ms는 clock_tick(15ms) 같은 짧은 슬롯의 본체를 거의 삼켜서 청각 전달이
# 약해짐 → 1/2ms로 낮춤. 클릭 제거는 여전히 유효(22.7μs 계단이 사라지면 충분).
_ATTACK_MS = 1
_RELEASE_MS = 2


def _edge_ramp(i: int, n_samples: int, sample_rate: int) -> float:
    """양끝 선형 램프. attack_n/release_n은 duration 짧을 때 n_samples//3 cap."""
    if n_samples <= 0:
        return 0.0
    attack_n = min(n_samples // 3, max(1, int(sample_rate * _ATTACK_MS / 1000)))
    release_n = min(n_samples // 3, max(1, int(sample_rate * _RELEASE_MS / 1000)))
    if i < attack_n:
        return i / attack_n
    if i >= n_samples - release_n:
        return max(0.0, (n_samples - i) / release_n)
    return 1.0


# Phase 6 §2: 파형별 crest factor 역보정. 같은 peak에서 sine(RMS 0.707)과 square
# (RMS 1.0)이 체감 +3dB 차이 → 각 파형에 대응 스케일 적용으로 라우드니스 균일화.
# pulse12와 pulse25는 고조파 집중으로 귀 민감대(2~4kHz)에 에너지 몰림 → 추가 감쇠.
_WAVEFORM_GAIN = {
    "sine": 1.00,
    "triangle": 0.95,
    "pulse50": 0.55,
    "square": 0.55,
    "pulse25": 0.50,
    "pulse12": 0.40,
    "saw": 0.55,
    "noise": 0.60,
}

# Precomputed sine table. 1024개 sample이면 표준 tones 대역(130~4000Hz)에서
# 인접 샘플 사이 보간 없이도 청각 구분 불가능 수준의 오차. LUT 키도 1 위상
# (0..1) 기준이라 주파수와 독립적이라 재사용 효율 최대.
_SINE_TABLE_SIZE = 1024
_SINE_TABLE = array.array(
    "d",
    (math.sin(2.0 * math.pi * i / _SINE_TABLE_SIZE) for i in range(_SINE_TABLE_SIZE)),
)


def _sine_at(phase: float) -> float:
    """phase ∈ [0, 1) → sine value ∈ [-1, 1]. phase는 위상 누적값."""
    # phase는 위상 누적(%1.0 처리는 호출자). 정수 인덱스로 변환 후 테이블 룩업.
    i = int(phase * _SINE_TABLE_SIZE) % _SINE_TABLE_SIZE
    return _SINE_TABLE[i]


# ---------------------------------------------------------------------
# 파형 generator — (phase: float ∈ [0, 1)) → sample ∈ [-1, 1]
# ---------------------------------------------------------------------


def _gen_sine(phase: float) -> float:
    return _sine_at(phase)


def _gen_square(phase: float) -> float:
    """Pulse 50% (사각파). NES Pulse1/Pulse2의 기본 듀티."""
    return 1.0 if phase < 0.5 else -1.0


def _gen_pulse25(phase: float) -> float:
    """Pulse 25% — NES 특유의 얇고 밝은 듀티."""
    return 1.0 if phase < 0.25 else -1.0


def _gen_pulse12(phase: float) -> float:
    """Pulse 12.5% — 더 얇고 찢어지는 톤."""
    return 1.0 if phase < 0.125 else -1.0


def _gen_triangle(phase: float) -> float:
    """삼각파. NES Triangle 채널처럼 둥글고 부드러운 톤."""
    # 0..0.5: -1 → 1 상승, 0.5..1: 1 → -1 하강.
    if phase < 0.5:
        return 4.0 * phase - 1.0
    return 3.0 - 4.0 * phase


def _gen_saw(phase: float) -> float:
    """톱니파. 화려하고 거친 톤. 배음 풍부."""
    return 2.0 * phase - 1.0


# 참고: noise는 phase 개념이 없어 별도 경로로 처리(_render_pcm_int16 참조).
WAVEFORMS = {
    "sine": _gen_sine,
    "square": _gen_square,
    "pulse50": _gen_square,  # square의 별칭
    "pulse25": _gen_pulse25,
    "pulse12": _gen_pulse12,
    "triangle": _gen_triangle,
    "saw": _gen_saw,
}


# ---------------------------------------------------------------------
# 엔벨로프 — (i: int, n_samples: int) → amplitude_scale ∈ [0, 1]
# Phase 4 synthSpecs에서 드럼/타악/만화풍 효과를 위해 사용.
# ---------------------------------------------------------------------


def _env_exp_decay(i: int, n_samples: int) -> float:
    """빠른 지수 감쇠. 드럼 타격/킥/스내어 등 짧은 임펄스용.

    duration 경과 시점에 exp(-4) ≈ 0.018 수준으로 거의 무음. 전체 소리가
    "쿵/틱" 같은 타격 느낌.
    """
    if n_samples <= 0:
        return 0.0
    return math.exp(-4.0 * i / n_samples)


def _env_pluck(i: int, n_samples: int) -> float:
    """5% 어택 + 지수 감쇠. 물방울/코인/짧은 픽업 느낌."""
    if n_samples <= 0:
        return 0.0
    attack_end = int(0.05 * n_samples)
    if attack_end <= 0:
        return math.exp(-4.0 * i / n_samples)
    if i < attack_end:
        return i / attack_end
    return math.exp(-4.0 * (i - attack_end) / (n_samples - attack_end))


def _env_boing(i: int, n_samples: int) -> float:
    """바운스 — 감쇠 진동. 만화풍 "뾰용" 느낌.

    주파수가 본 파형에 있으니 엔벨로프 쪽은 저속(3Hz) 진폭 변조로 "통통 튐" 효과.
    """
    if n_samples <= 0:
        return 0.0
    t = i / n_samples
    return math.cos(2.0 * math.pi * 3.0 * t) * math.exp(-3.0 * t)


_ENVELOPES = {
    "exp_decay": _env_exp_decay,
    "pluck": _env_pluck,
    "boing": _env_boing,
}


# ---------------------------------------------------------------------
# 캐시
# ---------------------------------------------------------------------

_cache: dict = {}  # key -> wav file path
_cache_lock = threading.Lock()
_CACHE_MAX = 1024

# 전용 하위 폴더명 — OS temp dir 밑에 생성. 충돌 방지 + OS 청소기 도달 가능.
_CACHE_SUBDIR = "mtwn_wavcache"

# 미지 waveform_name에 대한 경고 스팸 방지. 같은 미지 이름이 매 비프마다
# 경고되면 로그가 무용지물. 이름별 1회만.
_warned_waveforms: set = set()


def _cache_dir() -> str:
    """임시 wav 파일이 저장되는 디렉터리. 필요 시 생성."""
    path = os.path.join(tempfile.gettempdir(), _CACHE_SUBDIR)
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        # 생성 실패 시 fallback으로 temp root 사용. 극단적 경우에만 발생.
        return tempfile.gettempdir()
    return path


def _cache_path(key) -> str:
    """결정론적 파일 경로. 같은 key → 같은 경로(동시 호출 경합 안전)."""
    key_str = "|".join(str(x) for x in key)
    digest = hashlib.sha1(key_str.encode("utf-8")).hexdigest()[:16]
    filename = f"mtwn_{digest}.wav"
    return os.path.join(_cache_dir(), filename)


# ---------------------------------------------------------------------
# 렌더링
# ---------------------------------------------------------------------


def _render_pcm_int16(
    waveform_name: str,
    freq_hz: float,
    duration_ms: int,
    sample_rate: int,
    volume: int = 100,
) -> bytes:
    """16bit signed LE PCM 바이트 생성.

    noise는 waveform_name == "noise"로만 접근. 같은 (freq, duration, sample_rate)
    조합이면 `random.Random` 시드가 같아 결정론적 — 캐시 일관성 확보.
    미지 파형은 sine으로 폴백(beepPlayer/validator가 미리 걸러내지만 방어).
    """
    n_samples = int(sample_rate * duration_ms / 1000)
    if n_samples <= 0:
        return b""
    # Phase 6 §2: 파형별 게인 보정. noise는 §3에서 별도 처리하므로 여기선 dict 조회
    # 결과 그대로 사용.
    # Phase 6 §5: 사용자 beepVolume(50~150%) 반영.
    # 리뷰 S2: amp 계산 결과를 32767로 clamp. volume=150 + wf_gain 1.0(sine) +
    # _AMPLITUDE 0.8 = 39320으로 int16 범위(±32767) 초과 → `array.array('h')`
    # OverflowError 발생 가능. amp 자체를 clamp해 안전.
    wf_gain = _WAVEFORM_GAIN.get(waveform_name, 1.0)
    vol_gain = max(0.0, volume / 100.0)
    amp = min(int(_AMPLITUDE * wf_gain * vol_gain * 32767), 32767)
    samples = array.array("h")  # signed short 16bit

    if waveform_name == "noise":
        # 시드를 문자열로 고정 — Python 3.11에서 random.Random이 튜플 seed를 거부.
        # 같은 (파형, freq, duration, sample_rate) 입력 = 같은 출력 보장.
        seed = f"{waveform_name}|{int(freq_hz)}|{duration_ms}|{sample_rate}"
        rng = random.Random(seed)
        for i in range(n_samples):
            v = rng.uniform(-1.0, 1.0)
            # Phase 6 §1: 양끝 어택/릴리즈 램프로 클릭/팝 제거.
            v *= _edge_ramp(i, n_samples, sample_rate)
            # 방어적 clamp — noise는 이미 ±1 범위지만 fp 오차 대비.
            v = max(-1.0, min(1.0, v))
            samples.append(int(v * amp))
    else:
        gen = WAVEFORMS.get(waveform_name)
        if gen is None:
            # 미지 파형: sine 폴백 + 1회 경고. NVDA 환경에서만 log 사용 가능하지만
            # 테스트/stand-alone에서도 print 없이 조용히 진행되게 logHandler 지연
            # import. NVDA 외부에선 import 실패 → 조용히 sine 폴백.
            if waveform_name not in _warned_waveforms:
                _warned_waveforms.add(waveform_name)
                try:
                    from logHandler import log as _log
                    _log.warning(
                        f"mtwn: unknown waveform={waveform_name!r}, "
                        f"falling back to sine"
                    )
                except Exception:
                    pass
            gen = _gen_sine
        phase_step = freq_hz / sample_rate
        phase = 0.0
        for i in range(n_samples):
            # phase는 [0, 1) 범위로 유지. 부동소수점 누적 오차는 짧은 비프(≤400ms)
            # 기준 무시 가능.
            v = gen(phase)
            # Phase 6 §1: 어택/릴리즈 램프.
            v *= _edge_ramp(i, n_samples, sample_rate)
            # 방어적 clamp — gen은 ±1 범위지만 램프 적용 후도 ±1 이내라 safe.
            v = max(-1.0, min(1.0, v))
            samples.append(int(v * amp))
            phase += phase_step
            if phase >= 1.0:
                phase -= 1.0
    return samples.tobytes()


def _write_wav_file(pcm_bytes: bytes, path: str, sample_rate: int) -> None:
    """PCM int16 LE → wav 파일. atomic write(.tmp 후 rename)로 부분 파일 방지."""
    tmp_path = path + ".tmp"
    with wave.open(tmp_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    # os.replace는 Windows에서도 atomic. 다른 프로세스가 동시에 같은 path를
    # 쓰고 있어도 최종 상태는 일관됨(둘 다 동일 결정론적 내용이라 무해).
    os.replace(tmp_path, path)


def render_wav(
    waveform_name: str,
    freq_hz: float,
    duration_ms: int,
    sample_rate: int = SAMPLE_RATE,
    volume: int = 100,
) -> str:
    """캐시된 wav 파일 경로 반환. 호출자는 `nvwave.playWaveFile(path)`로 재생.

    `nvwave.playWaveFile`이 파일 경로 문자열만 받는 제약(`nvwave.py:82-155`의
    `os.path.basename(fileName)`) 때문에 파일로 영속화. 같은 입력 → 같은 경로
    (결정론적 해시). 첫 호출 시 합성 + 디스크 쓰기, 이후 경로 즉시 반환.

    캐시 dict는 "렌더링 완료된 키" 플래그 역할. 파일이 외부 청소로 삭제돼도
    dict가 있으면 skip되지만 실존하는 파일이 아닐 수 있음 — `os.path.exists`
    검사를 매 호출에 하면 캐시 장점이 깎이므로 hit 시 존재 가정. 희귀한 누락은
    `beepPlayer`의 외곽 try/except에서 `tones.beep` 폴백으로 흡수.
    """
    # Phase 6: _ENGINE_VERSION + volume 포함. §1~§3 도입 전 캐시 분리 + 볼륨 변경
    # 시 새 파일 생성. volume은 보통 프리셋 고정값이라 실제 캐시 분산은 경미.
    key = ("wav", _ENGINE_VERSION, waveform_name, int(freq_hz),
           int(duration_ms), int(sample_rate), int(volume))

    with _cache_lock:
        if key in _cache:
            return _cache[key]

    # 히트가 아닐 때만 경로 계산 + 디렉터리 생성(_cache_path → _cache_dir →
    # makedirs). 핫패스 회피.
    path = _cache_path(key)

    # 렌더링은 락 밖에서 수행 (CPU bound 블로킹 방지). 동일 키에 대한 중복 렌더링은
    # 결과가 결정론적으로 동일하므로 파일 덮어쓰기 안전.
    pcm = _render_pcm_int16(waveform_name, freq_hz, duration_ms, sample_rate, volume)
    _write_wav_file(pcm, path, sample_rate)

    with _cache_lock:
        if len(_cache) >= _CACHE_MAX:
            # FIFO 교체 + 오래된 파일 unlink 시도(실패 무시).
            try:
                old_key = next(iter(_cache))
                old_path = _cache.pop(old_key)
                try:
                    os.unlink(old_path)
                except Exception:
                    pass
            except StopIteration:
                pass
        _cache[key] = path
    return path


# ---------------------------------------------------------------------
# synthSpecs 렌더링 (Phase 4) — 슬롯 = "짧은 SFX 한 덩이"
# ---------------------------------------------------------------------


def _render_spec_pcm(spec: dict, sample_rate: int, volume: int = 100) -> bytes:
    """단일 synthSpec → PCM int16 LE bytes.

    spec 지원 필드:
        - waveform: "sine" | "square" | ... | "noise"  (기본 "sine")
        - freq: 시작 주파수 Hz (기본 440). noise에선 무시.
        - endFreq: 종료 주파수 (옵션). 설정 시 freq→endFreq 선형 portamento.
        - durationMs: 재생 시간 (기본 50).
        - envelope: "exp_decay" | "pluck" | "boing" (옵션). 미설정 시 상수 진폭.
        - amp: 진폭 배율 [0, 1] (기본 1.0).

    결정성: 같은 spec dict → 같은 PCM. noise 시드도 spec 필드 조합으로 고정.
    """
    waveform = spec.get("waveform", "sine")
    start_freq = float(spec.get("freq", 440))
    end_freq = float(spec.get("endFreq", start_freq))
    duration_ms = int(spec.get("durationMs", 50))
    envelope_name = spec.get("envelope")
    amp_scale = float(spec.get("amp", 1.0))
    # Phase 6 §3: 노이즈 colored LPF 컷오프. spec이 명시 안 하면 기본 1200Hz.
    # 중저역 bias로 실제 자연 노이즈(노크/박수/기침 등)에 근접.
    noise_lpf_hz = float(spec.get("noiseLpfHz", 1200))

    n_samples = int(sample_rate * duration_ms / 1000)
    if n_samples <= 0:
        return b""

    # Phase 6 §2: 파형별 게인. noise는 별도 처리(아래) — waveform_gain 적용 후 LPF
    # 볼륨 손실 보정 계수(1.8)을 추가로 곱해 체감 밸런스 유지.
    # Phase 6 §5: 사용자 beepVolume(50~150%) 반영.
    # 리뷰 S2: amp 계산 결과를 int16 상한으로 clamp. volume=150 + amp_scale>1 등
    # 조합에서 `array.array('h')` OverflowError 발생 가능.
    wf_gain = _WAVEFORM_GAIN.get(waveform, 1.0)
    vol_gain = max(0.0, volume / 100.0)
    amp = min(int(_AMPLITUDE * amp_scale * wf_gain * vol_gain * 32767), 32767)
    samples = array.array("h")
    envelope_fn = _ENVELOPES.get(envelope_name) if envelope_name else None

    if waveform == "noise":
        # Phase 6 §3: 1-pole IIR LPF. α = dt / (RC + dt), RC = 1/(2π·fc).
        rc = 1.0 / (2.0 * math.pi * noise_lpf_hz)
        dt = 1.0 / sample_rate
        alpha = dt / (rc + dt)
        # 시드에 cutoff 포함해 동일 spec + 동일 cutoff일 때 결정론성 보장.
        seed = (
            f"spec|noise|{start_freq}|{end_freq}|{duration_ms}|"
            f"{envelope_name}|{amp_scale}|{noise_lpf_hz}|{sample_rate}"
        )
        rng = random.Random(seed)
        y = 0.0
        for i in range(n_samples):
            x = rng.uniform(-1.0, 1.0)
            # 1-pole low-pass 필터
            y = y + alpha * (x - y)
            # LPF 볼륨 손실 보정(cutoff에 따라 다르나 근사 1.8배가 무난)
            v = y * 1.8
            if envelope_fn is not None:
                v *= envelope_fn(i, n_samples)
            # Phase 6 §1: 어택/릴리즈 램프 — 클릭/팝 제거.
            v *= _edge_ramp(i, n_samples, sample_rate)
            # 클리핑 — wf_gain이 작아 대부분 안 걸리나 방어.
            v = max(-1.0, min(1.0, v))
            samples.append(int(v * amp))
    else:
        gen = WAVEFORMS.get(waveform)
        if gen is None:
            if waveform not in _warned_waveforms:
                _warned_waveforms.add(waveform)
                try:
                    from logHandler import log as _log
                    _log.warning(
                        f"mtwn: unknown waveform={waveform!r}, "
                        f"falling back to sine"
                    )
                except Exception:
                    pass
            gen = _gen_sine
        # Portamento: freq를 선형 보간으로 주 루프에서 누적.
        freq = start_freq
        freq_step = (end_freq - start_freq) / n_samples if n_samples > 0 else 0.0
        phase = 0.0
        for i in range(n_samples):
            phase_step = freq / sample_rate
            v = gen(phase)
            if envelope_fn is not None:
                v *= envelope_fn(i, n_samples)
            # Phase 6 §1: 어택/릴리즈 램프.
            v *= _edge_ramp(i, n_samples, sample_rate)
            # 방어적 clamp — envelope boing은 cos 기반이라 ±1 내지만 fp 오차 대비.
            v = max(-1.0, min(1.0, v))
            samples.append(int(v * amp))
            phase += phase_step
            if phase >= 1.0:
                phase -= 1.0
            freq += freq_step
    return samples.tobytes()


def _spec_cache_key(spec: dict, sample_rate: int, volume: int = 100):
    """spec → 결정론적 튜플 키. dict 순서 무관하게 선정된 필드만 사용.

    Phase 6: _ENGINE_VERSION + volume 포함. 어택/게인/LPF 도입 전 캐시 자동 분리 +
    사용자 볼륨 변경 시 새 캐시 생성. noiseLpfHz 포함으로 같은 spec이 다른 LPF면
    다른 캐시 엔트리.
    """
    return (
        "spec",
        _ENGINE_VERSION,
        spec.get("waveform", "sine"),
        int(round(float(spec.get("freq", 440)))),
        int(round(float(spec.get("endFreq", spec.get("freq", 440))))),
        int(spec.get("durationMs", 50)),
        spec.get("envelope"),
        float(spec.get("amp", 1.0)),
        float(spec.get("noiseLpfHz", 1200)),
        int(sample_rate),
        int(volume),
    )


def render_spec(spec: dict, sample_rate: int = SAMPLE_RATE, volume: int = 100) -> str:
    """synthSpec 렌더링 + 파일 캐시. 반환은 wav 파일 경로.

    `render_wav(waveform, freq, duration)`의 풀 기능 버전. synthSpecs 기반
    프리셋(drum_kit/lazer_pack/eight_bit_jump 등)에서 사용.
    """
    key = _spec_cache_key(spec, sample_rate, volume)

    with _cache_lock:
        if key in _cache:
            return _cache[key]

    path = _cache_path(key)
    pcm = _render_spec_pcm(spec, sample_rate, volume)
    _write_wav_file(pcm, path, sample_rate)

    with _cache_lock:
        if len(_cache) >= _CACHE_MAX:
            try:
                old_key = next(iter(_cache))
                old_path = _cache.pop(old_key)
                try:
                    os.unlink(old_path)
                except Exception:
                    pass
            except StopIteration:
                pass
        _cache[key] = path
    return path


def clear_cache() -> None:
    """전체 캐시 제거 + 파일 unlink 시도. GlobalPlugin.terminate() 호출점."""
    with _cache_lock:
        paths = list(_cache.values())
        _cache.clear()
    for p in paths:
        try:
            os.unlink(p)
        except Exception:
            pass


def cache_size() -> int:
    """진단용 — 현재 캐시 엔트리 수."""
    with _cache_lock:
        return len(_cache)
