"""
Lab 8 - Distributed Gossip Protocol & Quorum Key-Value Store Simulator.

Đề (Slide 36-38, Lect08):
  1. Gifford Quorum: client đọc NR bản sao, ghi NW bản sao (NR, NW cấu hình được).
  2. Push-Pull Anti-Entropy: mỗi 2 giây, mỗi replica chọn ngẫu nhiên 1 peer,
     gửi toàn bộ dữ liệu của mình (push) và nhận dữ liệu của peer (pull),
     bên nào có version cao hơn thì thắng.
  3. Death Certificate (Tombstone): xóa = ghi một bản "DELETED" có version mới,
     để gossip lan việc xóa đi chứ không bị bản cũ "hồi sinh".

- 5 replica S1..S5, mỗi replica là 1 TCP socket server (thread) trên localhost.
- Bộ nhớ: key -> {value, version, writer, tombstone}
- Hai client ghi cùng lúc có thể ra cùng version -> so thêm "writer" (ID client) để phân thắng thua:
  bản mới hơn = (version, writer) lớn hơn. Nhờ vậy mọi replica chọn giống nhau và vẫn hội tụ.

Chạy:  python gossip_quorum.py
"""
import json
import random
import socket
import socketserver
import threading
import time

HOST = "127.0.0.1"
BASE_PORT = 9500
N = 5
GOSSIP_INTERVAL = 2.0
print_lock = threading.Lock()


def say(text):
    with print_lock:
        print(text)


def rpc(port, msg):
    with socket.create_connection((HOST, port), timeout=2) as s:
        s.sendall((json.dumps(msg) + "\n").encode())
        return json.loads(s.makefile().readline())


def rank(entry):
    """Thứ tự toàn phần của các bản ghi: version trước, trùng version thì ID client lớn hơn thắng."""
    return (entry["version"], entry.get("writer", 0)) if entry else (0, 0)


def show(entry):
    if entry is None:
        return "(không có)"
    if entry["tombstone"]:
        return f"TOMBSTONE (Ver {entry['version']})"
    return f"{entry['value']!r} (Ver {entry['version']})"


class Replica:
    def __init__(self, idx):
        self.name = f"S{idx}"
        self.port = BASE_PORT + idx
        self.store = {}               # key -> {"value", "version", "tombstone"}
        self.lock = threading.Lock()
        self.gossip_on = threading.Event()

    # ---------- xử lý message ----------
    def handle(self, msg):
        t = msg["type"]
        with self.lock:
            if t == "READ":
                return {"entry": self.store.get(msg["key"])}
            if t == "WRITE":                # chỉ nhận nếu mới hơn bản đang giữ (không ghi đè bản thắng)
                if rank(msg["entry"]) > rank(self.store.get(msg["key"])):
                    self.store[msg["key"]] = msg["entry"]
                return {"ack": True}
            if t == "HARD_DELETE":         # xóa thật (để so sánh với tombstone)
                self.store.pop(msg["key"], None)
                return {"ack": True}
            if t == "DUMP":
                return {"store": self.store}
            if t == "PUSH_PULL":           # nhận dữ liệu của peer, trả dữ liệu của mình
                mine = dict(self.store)
                changed = self.merge(msg["store"])
                if changed:
                    say(f"[GOSSIP] {msg['from']} -> {self.name} Push-Pull: {self.name} nhận {changed}")
                for key in changed:
                    say(f"[{self.name}] Memory State Updated -> key={key!r} {show(self.store[key])}")
                return {"store": mine}
        return {"error": "unknown"}

    def merge(self, other):
        """Anti-entropy: giữ bản có (version, writer) lớn hơn. Trả về các key bị thay đổi."""
        changed = []
        for key, entry in other.items():
            cur = self.store.get(key)
            if cur is None or rank(entry) > rank(cur):
                self.store[key] = entry
                changed.append(key)
        return changed

    # ---------- gossip ----------
    def gossip_loop(self, peers):
        while True:
            time.sleep(GOSSIP_INTERVAL + random.uniform(-0.3, 0.3))
            if not self.gossip_on.is_set():
                continue
            peer = random.choice(peers)
            with self.lock:
                mine = dict(self.store)
            try:
                theirs = rpc(peer.port, {"type": "PUSH_PULL", "from": self.name, "store": mine})["store"]
            except OSError:
                continue
            with self.lock:
                changed = self.merge(theirs)
            if changed:
                say(f"[GOSSIP] {self.name} <- {peer.name} Push-Pull: {self.name} nhận {changed}")
                for key in changed:
                    say(f"[{self.name}] Memory State Updated -> key={key!r} {show(self.store[key])}")

    def start(self, peers):
        replica = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                msg = json.loads(self.rfile.readline())
                self.wfile.write((json.dumps(replica.handle(msg)) + "\n").encode())

        socketserver.ThreadingTCPServer.allow_reuse_address = True
        srv = socketserver.ThreadingTCPServer((HOST, self.port), Handler)
        srv.daemon_threads = True
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        threading.Thread(target=self.gossip_loop, args=(peers,), daemon=True).start()


class QuorumClient:
    """Client proxy: gửi đọc/ghi tới NR / NW replica."""

    def __init__(self, replicas, nr, nw, client_id=1):
        self.id = client_id             # dùng để phân thắng thua khi 2 client ghi trùng version
        self.replicas = replicas
        self.nr, self.nw = nr, nw
        r1 = nr + nw > N
        r2 = nw > N / 2
        say(f"[CLIENT] Quorum NR={nr}, NW={nw}: NR+NW={nr + nw} > {N}? {'PASS' if r1 else 'FAIL'} | "
            f"NW={nw} > {N / 2}? {'PASS' if r2 else 'FAIL'}")

    def prepare(self, key, entry_value, tombstone, targets):
        """Bước 1 của ghi: hỏi version hiện tại trong quorum ghi -> version mới = lớn nhất + 1
        (NW > N/2 nên 2 quorum ghi luôn giao nhau -> luôn thấy version mới nhất)."""
        versions = [(rpc(r.port, {"type": "READ", "key": key})["entry"] or {"version": 0})["version"]
                    for r in targets]
        return {"value": entry_value, "version": max(versions) + 1, "writer": self.id, "tombstone": tombstone}

    def commit(self, key, entry, targets):
        """Bước 2 của ghi: gửi bản ghi tới quorum."""
        acks = []
        for r in targets:
            rpc(r.port, {"type": "WRITE", "key": key, "entry": entry})
            acks.append(f"[{r.name}] Write ACK Ver {entry['version']}")
        say(" | ".join(acks))
        return entry["version"]

    def _write(self, key, entry_value, tombstone, targets):
        return self.commit(key, self.prepare(key, entry_value, tombstone, targets), targets)

    def write(self, key, value, targets=None):
        targets = targets or self.replicas[:self.nw]
        say(f"[CLIENT] Write key={key!r} val={value!r} (NW={self.nw}) -> {[r.name for r in targets]}")
        self._write(key, value, False, targets)

    def delete(self, key, targets=None):
        targets = targets or self.replicas[:self.nw]
        say(f"[CLIENT] Delete key={key!r} (NW={self.nw}) -> {[r.name for r in targets]}")
        v = self._write(key, None, True, targets)
        say(f"[CLIENT] key={key!r} Written as Tombstone (Ver {v})")

    def read(self, key, targets=None):
        targets = targets or random.sample(self.replicas, self.nr)
        answers = [(r, rpc(r.port, {"type": "READ", "key": key})["entry"]) for r in targets]
        best = max((e for _, e in answers if e), key=rank, default=None)
        detail = ", ".join(f"{r.name}:{(e or {'version': 0})['version']}" for r, e in answers)
        value = None if best is None or best["tombstone"] else best["value"]
        say(f"[CLIENT] Read key={key!r} (NR={self.nr}) versions [{detail}] -> {value!r}")
        return value


def print_states(replicas, key):
    for r in replicas:
        entry = rpc(r.port, {"type": "DUMP"})["store"].get(key)
        say(f"    {r.name}: {key}={show(entry)}")


def wait_converged(replicas, timeout=20):
    t0 = time.time()
    while time.time() - t0 < timeout:
        stores = [json.dumps(rpc(r.port, {"type": "DUMP"})["store"], sort_keys=True) for r in replicas]
        if len(set(stores)) == 1:
            return time.time() - t0
        time.sleep(0.2)
    return None


def set_gossip(replicas, on):
    for r in replicas:
        (r.gossip_on.set if on else r.gossip_on.clear)()


def main():
    random.seed(8)
    replicas = [Replica(i) for i in range(1, N + 1)]
    for r in replicas:
        r.start([p for p in replicas if p is not r])
    S1, S2, S3, S4, S5 = replicas

    client = QuorumClient(replicas, nr=3, nw=3)

    print("\n===== 1. Ghi theo quorum (gossip đang TẮT) =====")
    client.write("user1", "Bob")
    say("[SYSTEM] Write Committed. S4 and S5 are stale (Ver 0):")
    print_states(replicas, "user1")
    # Đọc từ đúng 3 replica "xa nhất": vẫn gặp S3 nhờ NR + NW > N
    client.read("user1", targets=[S3, S4, S5])

    print("\n===== 2. Bật gossip Push-Pull Anti-Entropy =====")
    set_gossip(replicas, True)
    t = wait_converged(replicas)
    say(f"[SYSTEM] Hội tụ sau {t:.1f}s:")
    print_states(replicas, "user1")

    print("\n===== 3. Xóa bằng Tombstone =====")
    set_gossip(replicas, False)
    client.delete("user1", targets=[S1, S2, S3])
    client.read("user1", targets=[S3, S4, S5])
    set_gossip(replicas, True)
    t = wait_converged(replicas)
    say(f"[SYSTEM] All nodes successfully converged via Tombstone gossip ({t:.1f}s):")
    print_states(replicas, "user1")

    print("\n===== 4. So sánh: xóa THẬT (không tombstone) -> dữ liệu bị hồi sinh =====")
    client.write("user2", "Carol")
    wait_converged(replicas)
    set_gossip(replicas, False)
    for r in (S1, S2, S3):
        rpc(r.port, {"type": "HARD_DELETE", "key": "user2"})
    say("[CLIENT] Xóa hẳn key 'user2' trên S1, S2, S3 (S4, S5 vẫn còn 'Carol')")
    set_gossip(replicas, True)
    wait_converged(replicas)
    say("[SYSTEM] Sau gossip:")
    print_states(replicas, "user2")
    say("=> S4/S5 tưởng S1..S3 'chưa nhận' user2 nên gửi lại -> 'Carol' sống lại. "
        "Tombstone giải quyết đúng vấn đề này.")

    print("\n===== 5. Hai client ghi CÙNG LÚC -> trùng version, phân thắng thua bằng ID client =====")
    set_gossip(replicas, False)
    client2 = QuorumClient(replicas, nr=3, nw=3, client_id=2)
    q1, q2 = [S1, S2, S3], [S3, S4, S5]
    e1 = client.prepare("user3", "Dave", False, q1)      # cả 2 client đọc version TRƯỚC khi ai kịp ghi
    e2 = client2.prepare("user3", "Erin", False, q2)
    say(f"[CLIENT 1] chuẩn bị ghi 'Dave' Ver {e1['version']} -> S1,S2,S3 | "
        f"[CLIENT 2] chuẩn bị ghi 'Erin' Ver {e2['version']} -> S3,S4,S5")
    client2.commit("user3", e2, q2)
    client.commit("user3", e1, q1)                       # 'Dave' tới S3 SAU 'Erin' nhưng không được ghi đè
    say("[SYSTEM] Trước gossip (cùng Ver, khác giá trị):")
    print_states(replicas, "user3")
    set_gossip(replicas, True)
    t = wait_converged(replicas)
    result = f"hội tụ sau {t:.1f}s" if t is not None else "KHÔNG hội tụ"
    say(f"[SYSTEM] Sau gossip ({result}): client ID 2 > 1 nên 'Erin' thắng trên mọi replica")
    print_states(replicas, "user3")
    client.read("user3", targets=[S1, S2, S3])


if __name__ == "__main__":
    main()
