"""
Lab 10 - Secure Group Multicast & ABAC Policy Simulator.

Đề (Slide 36-40, Lect10):
  1. Cây khóa nhị phân LKH (Logical Key Hierarchy) để đổi khóa nhóm khi có Join / Leave.
  2. Mã hóa payload multicast bằng AES-256-GCM với khóa gốc (root group key).
  3. ABAC Policy Engine kiểm tra Subject (Role), Action và Time trước khi phát tin.
  4. In trace cho thấy số rekey block là O(log N).

Kiến trúc:
  - KeyServer: 1 TCP socket server, giữ cây LKH trong bộ nhớ.
      Cây nhị phân đầy đủ N = 8 lá, cao h = 3, đánh số kiểu heap:
                       K_0                 <- khóa gốc = khóa nhóm
                 K_1         K_2           <- KEK (Key Encrypting Key)
               K_3  K_4    K_5  K_6
              7  8  9 10  11 12 13 14      <- lá: khóa riêng của từng thành viên
  - Client: mỗi client là 1 kết nối TCP + 1 thread nghe. Client chỉ giữ khóa lá của mình
    và các khóa trên đường từ lá lên gốc (h + 1 = 4 khóa).
  - "Multicast" = server gửi cùng 1 frame cho MỌI socket đang nối, kể cả client chưa vào
    nhóm hoặc đã rời nhóm (ai cũng nghe được kênh multicast). Bảo mật là nhờ khóa.

Rekey:
  - JOIN : mỗi khóa trên đường đi được đổi mới, khóa mới mã hóa bằng khóa CŨ của chính nút đó
           -> h block multicast. Người mới nhận khóa qua unicast, mã hóa bằng khóa lá của họ.
  - LEAVE: mỗi khóa trên đường đi được đổi mới, khóa mới mã hóa bằng khóa của từng nút CON
           (bỏ qua lá của người rời) -> tối đa d*h block, thực tế d*h - 1.

Cần: pip install cryptography
Chạy:  python secure_group.py
"""
import base64
import json
import os
import socket
import socketserver
import threading
import time

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

HOST, PORT = "127.0.0.1", 9701
N = 8                       # số lá (sức chứa của nhóm)
H = 3                       # chiều cao cây = log2(N)
FIRST_LEAF = N - 1          # nút 7..14 là lá
print_lock = threading.Lock()


def say(text):
    with print_lock:
        print(text)


# ---------------- AES-256-GCM ----------------
def encrypt(key, data, aad):
    """Trả về chuỗi base64 của nonce(12 byte) | ciphertext | tag. aad được xác thực nhưng không mã hóa."""
    nonce = os.urandom(12)
    return base64.b64encode(nonce + AESGCM(key).encrypt(nonce, data, aad.encode())).decode()


def decrypt(key, blob, aad):
    """Sai khóa hoặc gói bị sửa -> InvalidTag."""
    raw = base64.b64decode(blob)
    return AESGCM(key).decrypt(raw[:12], raw[12:], aad.encode())


def parent(node):
    return (node - 1) // 2


def path_to_root(leaf):
    """Các nút cha từ dưới lên: lá 9 -> [4, 1, 0]."""
    out = []
    while leaf:
        leaf = parent(leaf)
        out.append(leaf)
    return out


# ---------------- ABAC ----------------
def abac_check(subject, action, env_time):
    """Rule (slide 38): ALLOW IF Role == 'Publisher' AND Action == 'publish' AND 08:00 <= Time <= 18:00."""
    if subject.get("role") != "Publisher":
        return False, f"Subject.Role = {subject.get('role')!r} != 'Publisher'"
    if action != "publish":
        return False, f"Action = {action!r} không được phép"
    if not "08:00" <= env_time <= "18:00":      # chuỗi "HH:MM" so sánh được theo thứ tự chữ
        return False, f"Env.Time = {env_time} ngoài khung 08:00-18:00"
    return True, f"Role = 'Publisher', Action = 'publish', Time = {env_time}"


# ---------------- Key Server ----------------
class KeyServer:
    def __init__(self, registered):
        self.registered = registered            # {client_id: {"key": khóa riêng, "role": ...}} đăng ký từ trước
        self.keys = {n: os.urandom(32) for n in range(FIRST_LEAF)}     # khóa của các nút trong
        self.version = {n: 1 for n in range(FIRST_LEAF)}
        self.leaf_of = {}                       # client_id -> nút lá
        self.member_at = {}                     # nút lá -> client_id
        self.conns = []                         # mọi socket đang nghe kênh multicast
        self.lock = threading.Lock()
        self.verbose = True                     # False khi dựng nhóm ban đầu cho đỡ rối log
        self.stats = {}                         # số block của lần JOIN / LEAVE gần nhất
        say(f"[KEY_SERVER] LKH Binary Tree Initialized (N={N} Members, Height h={H}).")

    def node_key(self, node):
        if node >= FIRST_LEAF:
            return self.registered[self.member_at[node]]["key"]
        return self.keys[node]

    def has_member(self, node):
        """Cây con gốc `node` còn thành viên nào không (cây con rỗng thì không cần gửi block)."""
        if node >= FIRST_LEAF:
            return node in self.member_at
        return self.has_member(2 * node + 1) or self.has_member(2 * node + 2)

    def refresh(self, node):
        self.keys[node] = os.urandom(32)
        self.version[node] += 1

    def block(self, node, under, under_key):
        """1 rekey block: khóa mới của `node`, mã hóa bằng khóa của nút `under`."""
        aad = f"K_{node}v{self.version[node]}"
        return {"node": node, "ver": self.version[node], "under": under,
                "ct": encrypt(under_key, self.keys[node], aad)}

    def multicast(self, frame):
        data = (json.dumps(frame) + "\n").encode()
        for wfile in self.conns:
            wfile.write(data)
            wfile.flush()

    # ----- xử lý message từ client -----
    def handle(self, msg, wfile):
        t, cid = msg["type"], msg.get("id")
        if t == "LISTEN":                       # chỉ nghe kênh multicast, chưa là thành viên
            self.conns.append(wfile)
            return {"type": "OK"}
        if t == "JOIN":
            return self.join(cid)
        if t == "LEAVE":
            return self.leave(cid)
        if t == "PUBLISH":
            return self.publish(cid, msg)
        return {"type": "ERROR", "why": "unknown"}

    def join(self, cid):
        leaf = next(n for n in range(FIRST_LEAF, FIRST_LEAF + N) if n not in self.member_at)
        path = path_to_root(leaf)
        old = {n: self.keys[n] for n in path}
        for n in path:
            self.refresh(n)
        self.member_at[leaf], self.leaf_of[cid] = cid, leaf
        # Người cũ: khóa mới mã hóa bằng khóa cũ của chính nút đó -> h block
        blocks = [self.block(n, n, old[n]) for n in path]
        self.stats["JOIN"] = len(blocks)
        if self.verbose:
            say(f"[{cid.upper()}] Joining Group... LKH Rekey Sent: {len(blocks)} Encrypted Blocks "
                f"(h = log2 {N} = {H}).")
        self.multicast({"type": "REKEY", "why": "JOIN", "who": cid, "blocks": blocks})
        # Người mới: nhận khóa đường đi qua unicast, mã hóa bằng khóa riêng (khóa lá)
        welcome = [self.block(n, leaf, self.registered[cid]["key"]) for n in path]
        return {"type": "WELCOME", "leaf": leaf, "blocks": welcome}

    def leave(self, cid):
        leaf = self.leaf_of.pop(cid)
        del self.member_at[leaf]
        say(f"[{cid.upper()}] Leaving Group... Executing Backward Secrecy Rekey.")
        blocks = []
        for n in path_to_root(leaf):            # từ dưới lên: khóa con đã mới thì mới mã hóa khóa cha
            self.refresh(n)
            for child in (2 * n + 1, 2 * n + 2):
                if self.has_member(child):      # lá của người rời đã trống -> không có block nào cho họ
                    blocks.append(self.block(n, child, self.node_key(child)))
        self.stats["LEAVE"] = len(blocks)
        say(f"[KEY_SERVER] Generated {len(blocks)} Rekey Blocks (<= d*h = 2*{H} = {2 * H}; "
            f"Flat Group Key cần {len(self.leaf_of)} unicast). Revoked {cid}.")
        self.multicast({"type": "REKEY", "why": "LEAVE", "who": cid, "blocks": blocks})
        return {"type": "OK"}

    def publish(self, cid, msg):
        me = self.registered[cid]
        # Yêu cầu đi trên kênh riêng, mã hóa bằng khóa riêng của client -> xác thực được người gửi
        try:
            req = json.loads(decrypt(me["key"], msg["body"], f"PUBLISH:{cid}"))
        except InvalidTag:
            return {"type": "DENIED", "why": "sai khóa"}
        subject = {"id": cid, "role": me["role"], "member": cid in self.leaf_of}
        if not subject["member"]:
            say(f"[ABAC_ENGINE] Policy Evaluation DENIED ({cid} không còn trong nhóm) -> Multicast Blocked.")
            return {"type": "DENIED", "why": "not a member"}
        ok, why = abac_check(subject, req["action"], req["time"])
        if not ok:
            say(f"[ABAC_ENGINE] Policy Evaluation DENIED ({why}) -> Multicast Blocked.")
            return {"type": "DENIED", "why": why}
        say(f"[ABAC_ENGINE] Policy Evaluation PASSED ({why}) -> Multicast Delivered.")
        ver = self.version[0]
        ct = encrypt(self.keys[0], req["text"].encode(), f"DATA:v{ver}")
        say(f"[KEY_SERVER] Multicast Dispatch: AES-256-GCM Payload Encrypted under Root Key K_0 (v{ver}).")
        self.multicast({"type": "DATA", "from": cid, "ver": ver, "ct": ct})
        return {"type": "OK"}

    def start(self):
        server = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                for line in self.rfile:
                    with server.lock:           # 1 khóa cho cả cây lẫn việc ghi socket -> frame không bị trộn
                        reply = server.handle(json.loads(line), self.wfile)
                        reply["reply"] = True   # phân biệt câu trả lời (unicast) với frame multicast
                        self.wfile.write((json.dumps(reply) + "\n").encode())
                        self.wfile.flush()

        socketserver.ThreadingTCPServer.allow_reuse_address = True
        srv = socketserver.ThreadingTCPServer((HOST, PORT), Handler)
        srv.daemon_threads = True
        threading.Thread(target=srv.serve_forever, daemon=True).start()


# ---------------- Group Client ----------------
class Client:
    def __init__(self, cid, key, quiet=False):
        self.cid, self.quiet = cid, quiet
        self.keys = {}              # mảng khóa cục bộ: {nút: (khóa, version)}
        self.my_key = key           # khóa riêng dùng chung với Key Server (khóa lá)
        self.leaf = None
        self.recorded = []          # mọi frame DATA nghe được trên kênh multicast (kể cả không giải mã được)
        self.reply = None
        self.got_reply = threading.Event()
        self.sock = socket.create_connection((HOST, PORT))
        self.f = self.sock.makefile("rw", encoding="utf-8")
        threading.Thread(target=self.listen, daemon=True).start()
        self.call({"type": "LISTEN"})

    def say(self, text):
        if not self.quiet:
            say(f"[{self.cid.upper()}] {text}")

    def call(self, msg):
        self.got_reply.clear()
        self.f.write(json.dumps(dict(msg, id=self.cid)) + "\n")
        self.f.flush()
        self.got_reply.wait(3)
        return self.reply

    def listen(self):
        for line in self.f:
            frame = json.loads(line)
            if frame.get("reply"):
                if frame["type"] == "WELCOME":      # cài khóa trước khi báo cho luồng chính
                    self.leaf = frame["leaf"]
                    self.keys[self.leaf] = (self.my_key, 0)
                    self.apply_blocks(frame["blocks"])
                self.reply = frame
                self.got_reply.set()
            elif frame["type"] == "REKEY":
                self.on_rekey(frame)
            elif frame["type"] == "DATA":
                self.recorded.append(frame)
                self.say(self.try_decrypt(frame))

    def apply_blocks(self, blocks):
        """Tìm block mã hóa bằng khóa mình đang giữ -> giải mã -> cập nhật khóa. Trả về số khóa đổi được."""
        updated = []
        for b in blocks:            # block xếp từ dưới lên, nên khóa vừa nhận dùng được cho block sau
            held = self.keys.get(b["under"])
            if held is None:
                continue
            try:
                new_key = decrypt(held[0], b["ct"], f"K_{b['node']}v{b['ver']}")
            except InvalidTag:
                continue            # giữ khóa cũ của nút này, không mở được block
            self.keys[b["node"]] = (new_key, b["ver"])
            updated.append(b["node"])
        return updated

    def on_rekey(self, frame):
        if frame["who"] == self.cid and frame["why"] == "JOIN":
            return                  # block này dành cho người cũ; mình nhận khóa qua WELCOME
        updated = self.apply_blocks(frame["blocks"])
        if updated:
            names = ", ".join(f"K_{n}" for n in updated)
            self.say(f"Received Rekey Msg ({frame['why']} {frame['who']}) -> Updated Path Keys [{names}] "
                     f"to Root Key K_0 v{self.keys[0][1]}.")
        elif self.leaf is not None:
            self.say(f"Received Rekey Msg ({frame['why']} {frame['who']}) -> KHÔNG mở được block nào "
                     f"(vẫn giữ K_0 v{self.keys[0][1]} cũ).")

    def try_decrypt(self, frame):
        """Thử mọi khóa đang giữ (kẻ tấn công cũng sẽ làm vậy)."""
        for key, _ in self.keys.values():
            try:
                text = decrypt(key, frame["ct"], f"DATA:v{frame['ver']}").decode()
                return f"Decrypted (K_0 v{frame['ver']}): {text!r}"
            except InvalidTag:
                pass
        return f"CANNOT decrypt message from {frame['from']} (không có K_0 v{frame['ver']})."

    def join(self):
        self.call({"type": "JOIN"})
        held = ", ".join(f"K_{n}" for n in sorted(self.keys))
        self.say(f"Joined at leaf {self.leaf}. Local keys: [{held}] ({len(self.keys)} khóa = h + 1).")

    def leave(self):
        self.call({"type": "LEAVE"})

    def publish(self, text, at):
        body = encrypt(self.my_key, json.dumps({"action": "publish", "text": text, "time": at}).encode(),
                       f"PUBLISH:{self.cid}")
        self.say(f"Request PUBLISH at {at}: {text!r}")
        return self.call({"type": "PUBLISH", "body": body})


def settle():
    time.sleep(0.4)     # chờ các client xử lý xong frame multicast để log in theo đúng thứ tự


def main():
    roles = {1: "Publisher", 2: "Subscriber"}
    registered = {f"client_{i}": {"key": os.urandom(32), "role": roles.get(i, "Subscriber")}
                  for i in range(1, 9)}
    server = KeyServer(registered)
    server.start()

    # Chỉ in log của vài client tiêu biểu cho gọn: 1 (publisher), 3 (vào sau), 5 (cùng nửa cây với 7), 7 (rời)
    clients = {i: Client(f"client_{i}", registered[f"client_{i}"]["key"], quiet=i not in (1, 3, 5, 7))
               for i in range(1, 9)}

    print("\n===== 0. Nhóm ban đầu: 7 thành viên (client_3 chưa vào, chỉ nghe lén kênh multicast) =====")
    server.verbose = False                  # dựng nhóm ban đầu: tắt log cho gọn
    shown = [c for c in clients.values() if not c.quiet]
    for c in shown:
        c.quiet = True
    for i in (1, 2, 4, 5, 6, 7, 8):
        clients[i].join()
    settle()
    server.verbose = True
    for c in shown:
        c.quiet = False
    say("[KEY_SERVER] Thành viên theo lá: " + ", ".join(f"{n}:{server.member_at.get(n, '(trống)')}"
                                                         for n in range(FIRST_LEAF, FIRST_LEAF + N)))

    print("\n===== 1. Multicast M1 (trước khi client_3 vào nhóm) =====")
    clients[1].publish("M1: bao cao quy 1", at="09:00")
    settle()

    print("\n===== 2. JOIN: client_3 vào nhóm =====")
    clients[3].join()
    settle()
    m1 = clients[3].recorded[0]
    say(f"[CLIENT_3] Thử giải mã M1 đã ghi lại từ trước: {clients[3].try_decrypt(m1)}")
    clients[1].publish("M2: chao mung client_3", at="10:00")
    settle()

    print("\n===== 3. LEAVE: client_7 rời nhóm (vẫn nghe lén kênh multicast) =====")
    clients[7].leave()
    settle()
    clients[1].publish("M3: tin mat sau khi client_7 roi", at="11:00")
    settle()

    print("\n===== 4. ABAC Policy Engine =====")
    clients[2].quiet = False
    clients[2].publish("toi la Subscriber", at="10:00")           # sai Role
    clients[1].publish("gui luc nua dem", at="23:30")             # sai Time
    clients[7].publish("toi da roi nhom", at="10:00")             # không còn là thành viên
    clients[1].publish("M4: hop le", at="17:59")
    settle()

    print("\n===== Kiểm tra (Verification Checklist, slide 39) =====")
    c3_m1 = "CANNOT" in clients[3].try_decrypt(clients[3].recorded[0])
    c7_m3 = "CANNOT" in clients[7].try_decrypt(clients[7].recorded[2])
    others = all("Decrypted" in clients[i].try_decrypt(clients[i].recorded[-1]) for i in (1, 2, 3, 4, 5, 6, 8))
    print(f"  Thành viên mới (client_3) KHÔNG đọc được tin cũ M1 : {'PASS' if c3_m1 else 'FAIL'}")
    print(f"  Thành viên đã rời (client_7) KHÔNG đọc được tin M3  : {'PASS' if c7_m3 else 'FAIL'}")
    print(f"  7 thành viên còn lại đọc được tin mới nhất M4       : {'PASS' if others else 'FAIL'}")
    print(f"  Mỗi client giữ {len(clients[1].keys)} khóa (h + 1 = {H + 1}); "
          f"Join = {server.stats['JOIN']} block, Leave = {server.stats['LEAVE']} block, "
          f"Flat Group Key Leave = N - 1 = {N - 1} unicast.")


if __name__ == "__main__":
    main()
