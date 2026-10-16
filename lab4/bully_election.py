"""
Lab 4 - Bầu chọn leader bằng thuật toán Bully.

- 5 tiến trình P1..P5, mỗi tiến trình là 1 thread có UDP socket riêng (localhost).
- Leader gửi HEARTBEAT định kỳ. Nếu quá hạn không nghe thấy -> phát hiện leader chết.
- Bully: gửi ELECTION cho các tiến trình có ID lớn hơn.
    + Nếu có ai trả OK -> chờ COORDINATOR.
    + Nếu không ai trả lời (timeout) -> tự làm leader, broadcast COORDINATOR.
- Fault injection: tắt P5 (leader), sau đó hệ thống bầu ra P4.

Chạy:  python bully_election.py
"""
import socket
import threading
import time

IDS = [1, 2, 3, 4, 5]
BASE_PORT = 9300
HEARTBEAT = 0.3
FAIL_TIMEOUT = 1.0
OK_TIMEOUT = 0.5
print_lock = threading.Lock()


def log(text):
    with print_lock:
        print(text)


def port_of(pid):
    return BASE_PORT + pid


class Process(threading.Thread):
    def __init__(self, pid):
        super().__init__(daemon=True)
        self.pid = pid
        self.leader = max(IDS)
        self.alive = True
        self.last_heartbeat = time.time()
        self.got_ok = threading.Event()
        self.in_election = False
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", port_of(pid)))
        self.sock.settimeout(0.1)

    def send(self, to, msg):
        if self.alive:
            self.sock.sendto(f"{msg}:{self.pid}".encode(), ("127.0.0.1", port_of(to)))

    def start_election(self):
        if self.in_election:
            return
        self.in_election = True
        higher = [p for p in IDS if p > self.pid]
        log(f"[P{self.pid}] Send ELECTION -> {', '.join(f'P{p}' for p in higher)}")
        self.got_ok.clear()
        for p in higher:
            self.send(p, "ELECTION")
        if not self.got_ok.wait(OK_TIMEOUT):
            log(f"[P{self.pid}] Timeout waiting for higher nodes -> NEW LEADER!")
            self.leader = self.pid
            others = [p for p in IDS if p != self.pid]
            log(f"[P{self.pid}] Broadcast COORDINATOR to {', '.join(f'P{p}' for p in others)}")
            for p in others:
                self.send(p, "COORDINATOR")
        self.in_election = False
        self.last_heartbeat = time.time()

    def on_message(self, kind, sender):
        if kind == "HEARTBEAT":
            self.last_heartbeat = time.time()
        elif kind == "ELECTION":
            log(f"[P{self.pid}] Recv ELECTION from P{sender} -> Reply OK")
            self.send(sender, "OK")
            threading.Thread(target=self.start_election, daemon=True).start()
        elif kind == "OK":
            self.got_ok.set()
        elif kind == "COORDINATOR":
            self.leader = sender
            self.last_heartbeat = time.time()
            log(f"[P{self.pid}] Accept P{sender} as leader")

    def run(self):
        last_sent = 0
        while self.alive:
            # leader gửi heartbeat
            if self.leader == self.pid and time.time() - last_sent > HEARTBEAT:
                for p in IDS:
                    if p != self.pid:
                        self.send(p, "HEARTBEAT")
                last_sent = time.time()
            try:
                data, _ = self.sock.recvfrom(1024)
                kind, sender = data.decode().split(":")
                self.on_message(kind, int(sender))
            except (socket.timeout, ConnectionResetError):
                # Windows báo ConnectionResetError khi UDP gửi tới tiến trình đã chết -> bỏ qua
                pass
            # phát hiện leader chết
            if (self.leader != self.pid and not self.in_election
                    and time.time() - self.last_heartbeat > FAIL_TIMEOUT):
                log(f"[P{self.pid}] Timeout detected! Leader P{self.leader} không phản hồi. Initiating Election...")
                threading.Thread(target=self.start_election, daemon=True).start()
                self.last_heartbeat = time.time()
        self.sock.close()


if __name__ == "__main__":
    procs = {pid: Process(pid) for pid in IDS}
    for p in procs.values():
        p.start()
    log("[SYSTEM] Hệ thống khởi động, leader = P5")
    time.sleep(1.5)

    log("[SYSTEM] Active Leader P5 terminated.")
    procs[5].alive = False

    # Cho P2 phát hiện lỗi trước (giống trace mẫu); các tiến trình khác vẫn tự phát hiện nếu cần
    for pid in (1, 3, 4):
        procs[pid].last_heartbeat = time.time() + 0.5
    time.sleep(3)

    print("\nKết quả:")
    for pid, p in procs.items():
        status = "DEAD" if not p.alive else f"leader = P{p.leader}"
        print(f"  P{pid}: {status}")
