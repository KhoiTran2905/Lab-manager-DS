"""
Lab 6 - Quorum-based Replication (N, NR, NW).

Slide Lect06 không có đề lab riêng, bài này làm theo phần "Quorum Systems"
(Slide 37-38): mô phỏng N = 5 bản sao, mỗi lần ghi gửi tới NW bản sao,
mỗi lần đọc lấy NR bản sao và chọn version mới nhất.

  Rule 1: NR + NW > N   -> đọc luôn gặp ít nhất 1 bản sao có dữ liệu mới nhất
  Rule 2: NW > N / 2    -> hai lần ghi luôn giao nhau, tránh ghi xung đột

Chạy:  python quorum.py
"""
import random

N = 5


class Replica:
    def __init__(self, rid):
        self.rid = rid
        self.version = 0
        self.value = None
        self.up = True


class QuorumStore:
    def __init__(self, nr, nw, seed=1):
        self.nr, self.nw = nr, nw
        self.replicas = [Replica(i) for i in range(N)]
        self.rng = random.Random(seed)

    def check_rules(self):
        r1 = self.nr + self.nw > N
        r2 = self.nw > N / 2
        print(f"  NR={self.nr}, NW={self.nw}: "
              f"NR+NW={self.nr + self.nw} > {N}? {'OK' if r1 else 'FAIL'} | "
              f"NW={self.nw} > {N / 2}? {'OK' if r2 else 'FAIL'}")
        return r1 and r2

    def pick(self, k):
        alive = [r for r in self.replicas if r.up]
        if len(alive) < k:
            return None
        return self.rng.sample(alive, k)

    def write(self, value):
        quorum = self.pick(self.nw)
        if quorum is None:
            print(f"  WRITE {value!r}: THẤT BẠI (không đủ {self.nw} bản sao sống)")
            return False
        # lấy version mới nhất trong quorum ghi rồi +1
        new_version = max(r.version for r in quorum) + 1
        for r in quorum:
            r.version, r.value = new_version, value
        print(f"  WRITE {value!r} v{new_version} -> replicas {[r.rid for r in quorum]}")
        return True

    def read(self):
        quorum = self.pick(self.nr)
        if quorum is None:
            print(f"  READ: THẤT BẠI (không đủ {self.nr} bản sao sống)")
            return None
        newest = max(quorum, key=lambda r: r.version)
        print(f"  READ  <- replicas {[r.rid for r in quorum]} -> {newest.value!r} (v{newest.version})")
        return newest.value


def scenario(title, nr, nw, crashes=0):
    print(f"\n=== {title} ===")
    store = QuorumStore(nr, nw)
    store.check_rules()
    store.write("x=1")
    store.write("x=2")
    for r in store.replicas[:crashes]:
        r.up = False
    if crashes:
        print(f"  [SYSTEM] {crashes} bản sao bị crash: {[r.rid for r in store.replicas[:crashes]]}")
    stale = 0
    for _ in range(10):
        if store.read() != "x=2":
            stale += 1
    print(f"  => Số lần đọc dữ liệu CŨ trong 10 lần: {stale}")


if __name__ == "__main__":
    scenario("Read-Heavy (NR=1, NW=5)", 1, 5)
    scenario("Balanced Majority (NR=3, NW=3), 2 bản sao crash", 3, 3, crashes=2)
    scenario("INVALID (NR=2, NW=2) - đọc có thể ra dữ liệu cũ", 2, 2)
