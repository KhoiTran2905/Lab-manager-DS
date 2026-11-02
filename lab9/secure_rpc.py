"""
Lab 9 - Secure RPC & KDC Authentication Proxy Simulator.

Đề (Slide 39-40, Lect09): 3 tiến trình giao tiếp qua socket:
  KDC (cấp khóa phiên), Client (Alice), Resource Server (Bob).
  1. KDC: giao thức Needham-Schroeder (khóa đối xứng):
       (1) A -> KDC : A, B, R_A1
       (2) KDC -> A : E_KA( R_A1, B, K_AB, Ticket )   với Ticket = E_KB( A, K_AB )
       (3) A -> B   : Ticket, E_KAB( R_A2 )
       (4) B -> A   : E_KAB( R_A2 - 1, R_B )
       (5) A -> B   : E_KAB( R_B - 1 )
  2. RPC mã hóa bằng AES-CBC với khóa phiên K_AB.
  3. Mỗi message có HMAC-SHA256 để phát hiện bị sửa.
  4. Mỗi RPC có nonce; server nhớ nonce đã dùng -> gói tin bị gửi lại (replay) bị từ chối.

Mỗi "khóa" là 32 byte; từ đó tách ra khóa AES và khóa HMAC riêng.
Cần: pip install cryptography

Chạy:  python secure_rpc.py
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import socket
import socketserver
import threading

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

HOST = "127.0.0.1"
KDC_PORT, BOB_PORT = 9601, 9602
print_lock = threading.Lock()


def say(text):
    with print_lock:
        print(text)


# ---------------- Mật mã: AES-CBC + HMAC-SHA256 (encrypt-then-MAC) ----------------
def subkeys(key):
    return hashlib.sha256(key + b"enc").digest(), hashlib.sha256(key + b"mac").digest()


def seal(key, obj):
    """Mã hóa obj (dict) -> chuỗi base64: IV | ciphertext | HMAC."""
    enc_key, mac_key = subkeys(key)
    iv = os.urandom(16)
    padder = padding.PKCS7(128).padder()
    data = padder.update(json.dumps(obj).encode()) + padder.finalize()
    enc = Cipher(algorithms.AES(enc_key), modes.CBC(iv)).encryptor()
    ct = iv + enc.update(data) + enc.finalize()
    tag = hmac.new(mac_key, ct, hashlib.sha256).digest()
    return base64.b64encode(ct + tag).decode()


def unseal(key, blob):
    """Kiểm tra HMAC trước, đúng thì mới giải mã. Sai -> ValueError."""
    enc_key, mac_key = subkeys(key)
    raw = base64.b64decode(blob)
    ct, tag = raw[:-32], raw[-32:]
    if not hmac.compare_digest(tag, hmac.new(mac_key, ct, hashlib.sha256).digest()):
        raise ValueError("HMAC mismatch")
    dec = Cipher(algorithms.AES(enc_key), modes.CBC(ct[:16])).decryptor()
    data = dec.update(ct[16:]) + dec.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return json.loads(unpadder.update(data) + unpadder.finalize())


def b64(key):
    return base64.b64encode(key).decode()


def nonce():
    # số ngẫu nhiên đủ lớn để gần như không bao giờ trùng (trùng sẽ bị coi là replay)
    return secrets.randbelow(10 ** 9)


# ---------------- Mạng ----------------
def serve(port, handler_fn):
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            for line in self.rfile:          # 1 kết nối có thể gửi nhiều message
                reply = handler_fn(json.loads(line))
                self.wfile.write((json.dumps(reply) + "\n").encode())
                self.wfile.flush()

    socketserver.ThreadingTCPServer.allow_reuse_address = True
    srv = socketserver.ThreadingTCPServer((HOST, port), Handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()


class Conn:
    def __init__(self, port):
        self.sock = socket.create_connection((HOST, port), timeout=3)
        self.f = self.sock.makefile("rw", encoding="utf-8")

    def call(self, msg):
        self.f.write(json.dumps(msg) + "\n")
        self.f.flush()
        return json.loads(self.f.readline())


# ---------------- KDC ----------------
class KDC:
    def __init__(self, keys):
        self.keys = keys            # khóa dài hạn dùng chung với từng người: {"Alice": K_A, "Server_Bob": K_B}

    def handle(self, msg):
        a, b, r_a = msg["from"], msg["to"], msg["nonce"]
        k_ab = os.urandom(32)
        ticket = seal(self.keys[b], {"client": a, "k_ab": b64(k_ab)})
        say(f"[KDC] Ticket_Bob Generated | Session Key K_AB Created.")
        return {"reply": seal(self.keys[a], {"nonce": r_a, "to": b, "k_ab": b64(k_ab), "ticket": ticket})}


# ---------------- Resource Server (Bob) ----------------
class Bob:
    def __init__(self, k_b):
        self.k_b = k_b
        self.sessions = {}          # client -> {"k_ab", "r_b", "ok", "seen"}
        self.data = {}

    def handle(self, msg):
        t = msg["type"]
        if t == "TICKET":                                    # bước (3) -> trả bước (4)
            tk = unseal(self.k_b, msg["ticket"])
            k_ab = base64.b64decode(tk["k_ab"])
            r_a2 = unseal(k_ab, msg["challenge"])["nonce"]
            r_b = nonce()
            self.sessions[tk["client"]] = {"k_ab": k_ab, "r_b": r_b, "ok": False, "seen": set()}
            say(f"[SERVER] Ticket_Bob Decrypted (client={tk['client']}) | Send R_A2-1, Challenge R_B = {r_b}")
            return {"reply": seal(k_ab, {"answer": r_a2 - 1, "nonce": r_b})}
        s = self.sessions.get(msg["client"])
        if s is None:
            return {"error": "no session"}
        if t == "CHALLENGE_REPLY":                           # bước (5)
            ok = unseal(s["k_ab"], msg["body"])["answer"] == s["r_b"] - 1
            s["ok"] = ok
            say(f"[SERVER] Nonce Challenge R_B = {s['r_b']} {'Verified' if ok else 'FAILED'}.")
            return {"ok": ok}
        if t == "RPC":
            if not s["ok"]:
                return {"error": "not authenticated"}
            try:
                req = unseal(s["k_ab"], msg["body"])
            except ValueError:
                say("[SERVER] HMAC Verification FAILED -> Packet bị sửa, từ chối!")
                return {"error": "integrity"}
            if req["nonce"] in s["seen"]:
                say(f"[SERVER] REPLAY DETECTED! Nonce {req['nonce']} đã dùng -> từ chối RPC.")
                return {"error": "replay"}
            s["seen"].add(req["nonce"])
            say(f"[SERVER] HMAC Verified OK | Nonce {req['nonce']} mới | Decrypted RPC Execution Successful.")
            result = self.execute(req["op"], req["args"])
            return {"body": seal(s["k_ab"], {"nonce": req["nonce"], "result": result})}
        return {"error": "unknown"}

    def execute(self, op, args):
        if op == "Write":
            self.data[args[0]] = args[1]
            say(f"[SERVER] Write({args[0]!r}, {args[1]}) -> data = {self.data}")
            return "OK"
        if op == "Read":
            return self.data.get(args[0])
        return "unknown op"


# ---------------- Client (Alice) ----------------
class Alice:
    def __init__(self, k_a):
        self.k_a = k_a
        self.k_ab = None
        self.bob = None
        self.last_packet = None     # "kẻ tấn công" bắt được gói này để replay

    def login(self):
        r_a1 = nonce()
        say(f"[CLIENT] Requesting Session Key for Server_Bob from KDC (Nonce R_A = {r_a1})...")
        resp = unseal(self.k_a, Conn(KDC_PORT).call({"from": "Alice", "to": "Server_Bob", "nonce": r_a1})["reply"])
        assert resp["nonce"] == r_a1 and resp["to"] == "Server_Bob", "KDC reply không khớp nonce!"
        self.k_ab = base64.b64decode(resp["k_ab"])
        say("[CLIENT] Decrypted Response (nonce khớp) | Ticket_Bob Forwarded to Server_Bob.")

        self.bob = Conn(BOB_PORT)
        r_a2 = nonce()
        r = unseal(self.k_ab, self.bob.call({"type": "TICKET", "ticket": resp["ticket"],
                                             "challenge": seal(self.k_ab, {"nonce": r_a2})})["reply"])
        assert r["answer"] == r_a2 - 1, "Bob không chứng minh được có K_AB!"
        say(f"[CLIENT] Bob trả R_A2-1 đúng -> Bob là thật. Gửi lại R_B-1.")
        ok = self.bob.call({"type": "CHALLENGE_REPLY", "client": "Alice",
                            "body": seal(self.k_ab, {"answer": r["nonce"] - 1})})["ok"]
        if ok:
            say("[CLIENT] Secure Channel Established with Server_Bob!")

    def make_packet(self, op, *args):
        n = nonce()
        packet = {"type": "RPC", "client": "Alice", "body": seal(self.k_ab, {"nonce": n, "op": op, "args": args})}
        say(f"[CLIENT] Executing Secure RPC: {op}{args} | Encrypted Payload + HMAC Sent (nonce {n}).")
        self.last_packet = packet       # kẻ nghe lén trên mạng cũng thấy được gói này
        return packet

    def send(self, packet):
        resp = self.bob.call(packet)
        if "body" in resp:
            res = unseal(self.k_ab, resp["body"])["result"]
            say(f"[CLIENT] RPC result = {res!r}")
            return res
        say(f"[CLIENT] RPC bị từ chối: {resp['error']}")

    def rpc(self, op, *args):
        return self.send(self.make_packet(op, *args))


def tamper(packet):
    """Kẻ tấn công lật 1 bit trong ciphertext."""
    raw = bytearray(base64.b64decode(packet["body"]))
    raw[20] ^= 0x01
    return dict(packet, body=base64.b64encode(bytes(raw)).decode())


def main():
    k_a, k_b = os.urandom(32), os.urandom(32)     # khóa dài hạn, đăng ký trước với KDC
    serve(KDC_PORT, KDC({"Alice": k_a, "Server_Bob": k_b}).handle)
    serve(BOB_PORT, Bob(k_b).handle)

    alice = Alice(k_a)
    print("===== 1. Xác thực qua KDC (Needham-Schroeder) =====")
    alice.login()

    print("\n===== 2. Secure RPC (AES-CBC + HMAC-SHA256) =====")
    alice.rpc("Write", "Balance", 500)
    alice.rpc("Read", "Balance")

    print("\n===== 3. Tấn công REPLAY: gửi lại y nguyên gói đã nghe lén =====")
    alice.rpc("Write", "Balance", 600)
    say("[ATTACKER] Gửi lại y nguyên gói Write('Balance', 600) vừa bắt được...")
    alice.send(alice.last_packet)

    print("\n===== 4. Tấn công SỬA GÓI TIN trên đường truyền =====")
    packet = alice.make_packet("Write", "Balance", 999)
    say("[ATTACKER] Chặn gói tin, lật 1 bit trong ciphertext rồi mới chuyển tiếp...")
    alice.send(tamper(packet))
    alice.rpc("Read", "Balance")


if __name__ == "__main__":
    main()
