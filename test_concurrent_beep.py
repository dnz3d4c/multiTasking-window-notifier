# 동시 비프음 재생 테스트
import threading
import time

# NVDA 환경에서 테스트 불가능하므로 이론적 검증만

def test_threading_approach():
    """스레딩 방식 - 실제로는 동시 재생 안됨"""
    print("=== 테스트 1: 스레딩 ===")

    def beep1():
        print(f"[{time.time():.3f}] Thread 1: 440Hz 시작")
        time.sleep(0.1)  # tones.beep(440, 100, 30, 30) 시뮬레이션
        print(f"[{time.time():.3f}] Thread 1: 440Hz 종료")

    def beep2():
        print(f"[{time.time():.3f}] Thread 2: 466Hz 시작")
        time.sleep(0.1)  # tones.beep(466, 100, 30, 30) 시뮬레이션
        print(f"[{time.time():.3f}] Thread 2: 466Hz 종료")

    start = time.time()
    t1 = threading.Thread(target=beep1)
    t2 = threading.Thread(target=beep2)

    t1.start()
    t2.start()

    t1.join()
    t2.join()

    print(f"총 시간: {time.time() - start:.3f}초")
    print("결과: 스레드는 동시 실행되지만 tones.beep()는 내부적으로 락이 걸려 순차 실행됨\n")


def test_sequential_approach():
    """순차 재생 방식"""
    print("=== 테스트 2: 빠른 순차 재생 ===")
    start = time.time()

    print(f"[{time.time():.3f}] 440Hz 시작")
    time.sleep(0.05)  # 짧게 50ms
    print(f"[{time.time():.3f}] 440Hz 종료")

    time.sleep(0.01)  # 10ms 간격

    print(f"[{time.time():.3f}] 466Hz 시작")
    time.sleep(0.05)  # 짧게 50ms
    print(f"[{time.time():.3f}] 466Hz 종료")

    print(f"총 시간: {time.time() - start:.3f}초")
    print("결과: 약 110ms, 충분히 빠름\n")


if __name__ == "__main__":
    test_threading_approach()
    test_sequential_approach()

    print("=== 결론 ===")
    print("1. 스레딩으로 동시 재생은 NVDA 구조상 불가능")
    print("2. 빠른 순차 재생(50ms+10ms+50ms=110ms)이 현실적")
    print("3. 사람 귀에는 충분히 빠른 간격으로 인식됨")
