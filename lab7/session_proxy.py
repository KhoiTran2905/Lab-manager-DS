"""
Lab 7 - Client-Centric Consistency Session Proxy Simulator.

Đề (Slide 37-38, Lect07):
  - 1 proxy nằm giữa client và 3 server bản sao S1, S2, S3.
  - Proxy giữ 2 vector của phiên làm việc (session):
        V_read  : các write mà client ĐÃ ĐỌC thấy   -> dùng cho Monotonic Reads
        V_write : các write mà client ĐÃ GHI        -> dùng cho Read-Your-Writes
  - Các server lệch nhau (write chỉ nằm ở server nhận nó, chưa lan sang server khác).
  - Khi client đọc ở server cũ (clock < V_read hoặc < V_write), proxy
    lấy các write còn thiếu từ server khác, áp dụng vào rồi mới cho đọc.

Mỗi server có vector clock 3 phần tử: clock[i] = số write gốc từ Si mà server đã có.

Chạy:  python session_proxy.py
"""

N = 3


def vec(v):
    return "(" + ", ".join(map(str, v)) + ")"


def dominates(a, b):
    """a >= b theo từng phần tử (a đã có đủ mọi write mà b biết)."""
    return all(x >= y for x, y in zip(a, b))


def merge(a, b):
    return [max(x, y) for x, y in zip(a, b)]


class Server:
    def __init__(self, idx):
        self.idx = idx
        self.name = f"S{idx + 1}"
        self.clock = [0] * N
        self.data = {}
        self.log = []      # các write đã áp dụng: (origin, seq, key, value)

    def local_write(self, key, value):
        """Write mới do client gửi tới server này."""
        self.clock[self.idx] += 1
        w = (self.idx, self.clock[self.idx], key, value)
        self.log.append(w)
        self.data[key] = value
        return w

    def apply(self, w):
        """Áp dụng write lấy từ server khác (theo đúng thứ tự seq)."""
        origin, seq, key, value = w
        if seq == self.clock[origin] + 1:
            self.clock[origin] = seq
            self.log.append(w)
            self.data[key] = value

    def missing_writes(self, clock):
        """Các write server này có mà một server với `clock` chưa có."""
        return [w for w in self.log if w[1] > clock[w[0]]]


class SessionProxy:
    def __init__(self, client, servers, enforce=True):
        self.client = client
        self.servers = servers
        self.enforce = enforce          # False = tắt bảo đảm để thấy lỗi
        self.v_read = [0] * N
        self.v_write = [0] * N

    def write(self, server, key, value):
        print(f"[{self.client}] Write {key} = {value!r} -> Sent to Server {server.name}")
        server.local_write(key, value)
        self.v_write = merge(self.v_write, server.clock)
        print(f"[{server.name}] Write ACK | Client V_write updated to {vec(self.v_write)}")

    def read(self, server, key):
        print(f"[SYSTEM] Routing {self.client} Read({key}) to Server {server.name}... "
              f"{server.name} Clock = {vec(server.clock)}")
        if self.enforce:
            self.make_fresh(server)
        value = server.data.get(key)
        self.v_read = merge(self.v_read, server.clock)
        print(f"[{server.name}] Read executed -> Returns {value!r} | V_read = {vec(self.v_read)}")
        return value

    def make_fresh(self, server):
        need = merge(self.v_read, self.v_write)
        if dominates(server.clock, need):
            print(f"[PROXY] Validation OK: {vec(server.clock)} >= {vec(need)}")
            return
        why = []
        if not dominates(server.clock, self.v_write):
            why.append(f"< V_write {vec(self.v_write)} (Read-Your-Writes)")
        if not dominates(server.clock, self.v_read):
            why.append(f"< V_read {vec(self.v_read)} (Monotonic Reads)")
        print(f"[PROXY] Validation Failed! {server.name} Clock {vec(server.clock)} " + " và ".join(why))
        # Lấy write còn thiếu từ các server khác (đơn giản: hỏi tất cả server)
        for peer in self.servers:
            if peer is server:
                continue
            for w in peer.missing_writes(server.clock):
                print(f"[PROXY] Fetching missing write {w[2]}={w[3]!r} (S{w[0] + 1}#{w[1]}) "
                      f"from {peer.name} -> Applying to {server.name}...")
                server.apply(w)
        print(f"[{server.name}] State Updated to {vec(server.clock)}")


def new_cluster():
    return [Server(i) for i in range(N)]


def demo_read_your_writes(enforce):
    print(f"\n===== 1. Read-Your-Writes ({'CÓ' if enforce else 'KHÔNG có'} proxy kiểm tra) =====")
    s1, s2, s3 = new_cluster()
    alice = SessionProxy("CLIENT", [s1, s2, s3], enforce)
    alice.write(s1, "profile_name", "Alice")
    # load balancer đẩy lần đọc sang S2, S2 chưa nhận được W1
    v = alice.read(s2, "profile_name")
    ok = v == "Alice"
    print(f"[CLIENT] {'Read-Your-Writes Guarantee Preserved!' if ok else 'VI PHẠM: không thấy dữ liệu mình vừa ghi!'}")


def demo_monotonic_reads(enforce):
    print(f"\n===== 2. Monotonic Reads ({'CÓ' if enforce else 'KHÔNG có'} proxy kiểm tra) =====")
    s1, s2, s3 = new_cluster()
    servers = [s1, s2, s3]
    # Hộp thư ban đầu có 3 email, đã đồng bộ cả 3 server
    w = s1.local_write("inbox", "3 emails")
    s2.apply(w)
    s3.apply(w)
    # Có 2 email mới đến, chỉ S3 nhận được (S1, S2 chưa đồng bộ)
    s3.local_write("inbox", "5 emails")
    print("[SYSTEM] Inbox: S1, S2 = '3 emails' | S3 = '5 emails' (chưa đồng bộ)")

    user = SessionProxy("USER", servers, enforce)
    first = user.read(s3, "inbox")
    second = user.read(s2, "inbox")    # refresh trang, bị chuyển sang S2 cũ
    ok = second == first
    print(f"[USER] {'Monotonic Reads Guarantee Preserved!' if ok else 'VI PHẠM: email vừa thấy đã biến mất!'}")


if __name__ == "__main__":
    demo_read_your_writes(enforce=True)
    demo_monotonic_reads(enforce=True)
    print("\n############ So sánh: tắt proxy kiểm tra ############")
    demo_read_your_writes(enforce=False)
    demo_monotonic_reads(enforce=False)
