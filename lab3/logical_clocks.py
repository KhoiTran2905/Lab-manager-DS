"""
Lab 3 - Logical Clock Simulator (Lamport + Vector clock).

- 3 tiến trình P0, P1, P2 chạy trên 3 thread.
- Giao tiếp CHỈ qua queue (mỗi tiến trình có 1 hàng đợi đầu vào), không dùng biến toàn cục chung.
- Mỗi bước, tiến trình chọn ngẫu nhiên: LOCAL / SEND / RECV.
- Khi nhận tin: Lamport = max(local, msg) + 1; Vector = max từng phần tử rồi tăng phần tử của mình.
- Nếu vector nhận được và vector cục bộ (trước khi gộp) song song (||) -> in CONFLICT.

Chạy:  python logical_clocks.py
"""
import queue
import random
import threading
import time

N = 3
STEPS = 6
inboxes = [queue.Queue() for _ in range(N)]
print_lock = threading.Lock()


def log(text):
    with print_lock:
        print(text)


def happened_before(a, b):
    return all(x <= y for x, y in zip(a, b)) and a != b


def concurrent(a, b):
    return not happened_before(a, b) and not happened_before(b, a) and a != b


class Process(threading.Thread):
    def __init__(self, pid, seed):
        super().__init__()
        self.pid = pid
        self.lamport = 0
        self.vector = [0] * N
        self.rng = random.Random(seed)

    def tick(self):
        self.lamport += 1
        self.vector[self.pid] += 1

    def state(self):
        return f"Lamport: {self.lamport:2d} | Vector: {self.vector}"

    def local_event(self):
        self.tick()
        log(f"[P{self.pid}] LOCAL EVENT        | {self.state()}")

    def send(self):
        target = self.rng.choice([p for p in range(N) if p != self.pid])
        self.tick()
        inboxes[target].put((self.pid, self.lamport, list(self.vector)))
        log(f"[P{self.pid}] SEND MSG to P{target}    | {self.state()}")

    def receive(self):
        try:
            sender, lam, vec = inboxes[self.pid].get(timeout=0.05)
        except queue.Empty:
            self.local_event()   # không có tin -> coi như sự kiện cục bộ
            return
        if concurrent(self.vector, vec):
            log(f"[P{self.pid}] CONFLICT DETECTED with P{sender}! Vector {self.vector} || {vec}")
        self.lamport = max(self.lamport, lam) + 1
        self.vector = [max(a, b) for a, b in zip(self.vector, vec)]
        self.vector[self.pid] += 1
        log(f"[P{self.pid}] RECV MSG fr P{sender}    | {self.state()}")

    def run(self):
        for _ in range(STEPS):
            self.rng.choice([self.local_event, self.send, self.receive])()
            time.sleep(self.rng.uniform(0.01, 0.05))
        # nhận nốt các tin còn tồn đọng
        while not inboxes[self.pid].empty():
            self.receive()


if __name__ == "__main__":
    procs = [Process(i, seed=i + 7) for i in range(N)]
    for p in procs:
        p.start()
    for p in procs:
        p.join()
    print("\nĐồng hồ cuối:")
    for p in procs:
        print(f"  P{p.pid}: {p.state()}")
