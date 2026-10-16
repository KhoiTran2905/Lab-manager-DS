"""
Lab 5 - Two-Phase Commit (2PC) Simulator.

- 1 Coordinator + 3 Participant, mỗi Participant là 1 TCP socket server (thread).
- Stable storage: mỗi bên ghi WAL (write-ahead log) vào file logs/<tên>.log,
  ghi + flush + fsync TRƯỚC khi gửi trả lời.
- Kịch bản:
    Tx 101: P3 bị xung đột khóa -> VOTE_ABORT -> GLOBAL_ABORT.
    Tx 102: mọi người VOTE_COMMIT, nhưng P2 "crash" ngay sau khi vote
            (chưa nhận quyết định). P2 khởi động lại, đọc WAL, thấy đang
            ở trạng thái READY -> hỏi Coordinator kết quả -> COMMIT.

Chạy:  python two_phase_commit.py
"""
import json
import os
import socket
import socketserver
import threading
import time

HOST = "127.0.0.1"
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
COORD_PORT = 9400
print_lock = threading.Lock()


def say(text):
    with print_lock:
        print(text)


def rpc(port, msg, timeout=2):
    with socket.create_connection((HOST, port), timeout=timeout) as s:
        s.sendall((json.dumps(msg) + "\n").encode())
        return json.loads(s.makefile().readline())


class WAL:
    def __init__(self, name):
        self.path = os.path.join(LOG_DIR, f"{name}.log")

    def append(self, record):
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(record + "\n")
            f.flush()
            os.fsync(f.fileno())

    def records(self):
        if not os.path.exists(self.path):
            return []
        with open(self.path, encoding="utf-8") as f:
            return [line.split() for line in f if line.strip()]


def serve(port, handler_fn):
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            msg = json.loads(self.rfile.readline())
            reply = handler_fn(msg)
            if reply is not None:
                self.wfile.write((json.dumps(reply) + "\n").encode())

    socketserver.ThreadingTCPServer.allow_reuse_address = True
    srv = socketserver.ThreadingTCPServer((HOST, port), Handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class Participant:
    def __init__(self, name, port):
        self.name, self.port = name, port
        self.wal = WAL(name)
        self.locked = set()          # tài nguyên đang bị khóa bởi giao dịch khác
        self.crash_after_vote = None  # tx_id để giả lập crash
        self.srv = None

    def start(self):
        self.srv = serve(self.port, self.handle)

    def crash(self):
        say(f"[{self.name}] *** CRASH ***")
        self.srv.shutdown()
        self.srv.server_close()

    def handle(self, msg):
        tx, kind = msg["tx"], msg["type"]
        if kind == "VOTE_REQUEST":
            if msg["item"] in self.locked:
                self.wal.append(f"VOTE_ABORT {tx}")
                say(f"[{self.name}] Lock Conflict! -> Log VOTE_ABORT -> Reply VOTE_ABORT")
                return {"vote": "VOTE_ABORT"}
            self.wal.append(f"VOTE_COMMIT {tx}")       # trạng thái READY
            say(f"[{self.name}] Log VOTE_COMMIT -> Reply VOTE_COMMIT")
            if self.crash_after_vote == tx:
                threading.Timer(0.05, self.crash).start()
            return {"vote": "VOTE_COMMIT"}
        if kind in ("GLOBAL_COMMIT", "GLOBAL_ABORT"):
            self.wal.append(f"{kind} {tx}")
            action = "Commit" if kind == "GLOBAL_COMMIT" else "Rollback"
            say(f"[{self.name}] Recv {kind} -> {action} -> Reply ACK")
            return {"ack": True}

    def recover(self):
        """Khởi động lại: đọc WAL để biết giao dịch nào còn dở dang."""
        say(f"[{self.name}] Reboot -> đọc WAL {os.path.basename(self.wal.path)}")
        state = {}
        for rec, tx in self.wal.records():
            state[tx] = rec
        for tx, rec in state.items():
            if rec == "VOTE_COMMIT":   # READY nhưng chưa biết kết quả -> hỏi coordinator
                decision = rpc(COORD_PORT, {"type": "DECISION_REQUEST", "tx": tx})["decision"]
                self.wal.append(f"{decision} {tx}")
                say(f"[{self.name}] Tx {tx} đang READY -> hỏi COORD -> {decision} -> hoàn tất")
            else:
                say(f"[{self.name}] Tx {tx} đã kết thúc ({rec}), không cần làm gì")
        self.start()


class Coordinator:
    def __init__(self, participants):
        self.parts = participants
        self.wal = WAL("coordinator")
        serve(COORD_PORT, self.handle)

    def handle(self, msg):
        if msg["type"] == "DECISION_REQUEST":
            decision = "GLOBAL_ABORT"   # mặc định: không tìm thấy quyết định -> abort
            for rec, tx in self.wal.records():
                if tx == msg["tx"] and rec in ("GLOBAL_COMMIT", "GLOBAL_ABORT"):
                    decision = rec
            return {"decision": decision}

    def multicast(self, msg):
        replies = {}
        for p in self.parts:
            try:
                replies[p.name] = rpc(p.port, msg)
            except OSError:
                replies[p.name] = None   # không trả lời
        return replies

    def execute(self, tx, item):
        self.wal.append(f"START_2PC {tx}")
        say(f"[COORD] Tx {tx} Started -> Log START_2PC")
        say("[COORD] Multicast VOTE_REQUEST")
        votes = self.multicast({"type": "VOTE_REQUEST", "tx": tx, "item": item})
        if all(v and v["vote"] == "VOTE_COMMIT" for v in votes.values()):
            decision = "GLOBAL_COMMIT"
        else:
            decision = "GLOBAL_ABORT"
            say("[COORD] Recv VOTE_ABORT -> Log GLOBAL_ABORT")
        self.wal.append(f"{decision} {tx}")
        say(f"[COORD] Multicast {decision}")
        time.sleep(0.2)
        acks = self.multicast({"type": decision, "tx": tx})
        missing = [n for n, a in acks.items() if a is None]
        if missing:
            say(f"[COORD] Không nhận ACK từ {missing} (sẽ tự phục hồi từ WAL)")
        result = "Committed" if decision == "GLOBAL_COMMIT" else "Aborted"
        say(f"[SYSTEM] Tx {tx} {result}.")


if __name__ == "__main__":
    os.makedirs(LOG_DIR, exist_ok=True)
    for f in os.listdir(LOG_DIR):
        os.remove(os.path.join(LOG_DIR, f))

    parts = [Participant(f"P{i}", 9400 + i) for i in (1, 2, 3)]
    for p in parts:
        p.start()
    coord = Coordinator(parts)

    print("===== Tx 101: P3 xung đột khóa =====")
    parts[2].locked.add("account_A")
    coord.execute(101, "account_A")
    parts[2].locked.clear()

    print("\n===== Tx 102: P2 crash sau khi vote =====")
    parts[1].crash_after_vote = 102
    coord.execute(102, "account_B")

    print("\n===== Khôi phục P2 từ WAL =====")
    time.sleep(0.3)
    parts[1].crash_after_vote = None
    parts[1].recover()

    print("\nNội dung WAL:")
    for name in ("coordinator", "P1", "P2", "P3"):
        recs = [" ".join(r) for r in WAL(name).records()]
        print(f"  {name:12s}: {recs}")
