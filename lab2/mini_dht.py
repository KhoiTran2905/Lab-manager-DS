"""
Lab 2 - Mini DHT registry (Chord đơn giản) + messaging client.

- Mỗi node là một TCP socket server (thread) trên localhost.
- ID không gian m = 6 bit (0..63). Mỗi node có finger table m dòng:
      finger[i] = successor(n + 2^i)
  -> tra cứu chỉ mất O(log N) bước nhảy.
- Registry: tên (vd "alice") -> địa chỉ thật (host:port), lưu ở node
  successor(hash(tên)). Khi địa chỉ đổi, chỉ cần đăng ký lại; client
  vẫn tìm được bằng tên (flat naming không phụ thuộc IP).

Chạy:  python mini_dht.py
"""
import hashlib
import json
import socket
import socketserver
import threading

M = 6
RING = 2 ** M
HOST = "127.0.0.1"


def h(key):
    return int(hashlib.sha1(key.encode()).hexdigest(), 16) % RING


def between(x, a, b):
    """x thuộc (a, b] trên vòng tròn."""
    if a < b:
        return a < x <= b
    return x > a or x <= b


def rpc(port, msg):
    """Gửi 1 message JSON qua socket, nhận 1 message JSON."""
    with socket.create_connection((HOST, port), timeout=2) as s:
        s.sendall((json.dumps(msg) + "\n").encode())
        return json.loads(s.makefile().readline())


class Node:
    def __init__(self, node_id, port):
        self.id = node_id
        self.port = port
        self.fingers = []      # [(start, succ_id, succ_port)]
        self.store = {}        # tên -> địa chỉ

    def successor(self):
        return self.fingers[0][1], self.fingers[0][2]

    def build_fingers(self, ring):
        """ring: danh sách (id, port) đã sắp xếp. Bản đơn giản: tính trực tiếp."""
        self.fingers = []
        for i in range(M):
            start = (self.id + 2 ** i) % RING
            succ = next(((nid, p) for nid, p in ring if nid >= start), ring[0])
            self.fingers.append((start, succ[0], succ[1]))

    def closest_preceding(self, key):
        for _, fid, fport in reversed(self.fingers):
            if between(fid, self.id, key) and fid != key:
                return fid, fport
        return self.successor()

    def handle(self, msg):
        t = msg["type"]
        if t == "find_successor":
            key = msg["key"]
            hops = msg.get("hops", 0)
            sid, sport = self.successor()
            if between(key, self.id, sid):
                return {"id": sid, "port": sport, "hops": hops + 1}
            nid, nport = self.closest_preceding(key)
            if nid == self.id:
                return {"id": sid, "port": sport, "hops": hops + 1}
            return rpc(nport, {"type": "find_successor", "key": key, "hops": hops + 1})
        if t == "put":
            self.store[msg["name"]] = msg["addr"]
            return {"ok": True}
        if t == "get":
            return {"addr": self.store.get(msg["name"])}
        return {"error": "unknown"}

    def start(self):
        node = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                msg = json.loads(self.rfile.readline())
                self.wfile.write((json.dumps(node.handle(msg)) + "\n").encode())

        srv = socketserver.ThreadingTCPServer((HOST, self.port), Handler)
        srv.daemon_threads = True
        self.server = srv
        threading.Thread(target=srv.serve_forever, daemon=True).start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


class Client:
    def __init__(self, entry_port):
        self.entry = entry_port

    def lookup_node(self, name):
        r = rpc(self.entry, {"type": "find_successor", "key": h(name)})
        return r

    def register(self, name, addr):
        r = self.lookup_node(name)
        rpc(r["port"], {"type": "put", "name": name, "addr": addr})
        print(f"[CLIENT] register {name} (hash={h(name)}) -> {addr} lưu ở Node {r['id']} ({r['hops']} hops)")

    def resolve(self, name):
        r = self.lookup_node(name)
        addr = rpc(r["port"], {"type": "get", "name": name})["addr"]
        print(f"[CLIENT] resolve {name} -> {addr} (qua Node {r['id']}, {r['hops']} hops)")
        return addr

    def send(self, name, text):
        addr = self.resolve(name)
        port = int(addr.split(":")[1])
        rpc(port, {"type": "message", "text": text})


def start_service(name, port):
    """Một dịch vụ người dùng (vd "alice") lắng nghe tin nhắn tại port riêng."""
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            msg = json.loads(self.rfile.readline())
            print(f"    [{name}@{port}] nhận tin: {msg['text']!r}")
            self.wfile.write(b'{"ok": true}\n')

    srv = socketserver.ThreadingTCPServer((HOST, port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main():
    ids = [1, 8, 14, 21, 32, 38, 42, 48, 51, 56]
    nodes = [Node(nid, 9100 + i) for i, nid in enumerate(ids)]
    ring = sorted((n.id, n.port) for n in nodes)
    for n in nodes:
        n.build_fingers(ring)
        n.start()
    print(f"DHT gồm {len(nodes)} node: {ids}")

    print("Finger table của Node 8:")
    for start, fid, _ in nodes[1].fingers:
        print(f"   start={start:2d} -> Node {fid}")

    c = Client(entry_port=nodes[0].port)

    alice = start_service("alice", 9200)
    c.register("alice", f"{HOST}:9200")
    c.send("alice", "Xin chào Alice!")

    # Mô phỏng địa chỉ của alice thay đổi (vd đổi mạng -> đổi IP/port)
    print("\n[SYSTEM] alice đổi địa chỉ 9200 -> 9201")
    alice.shutdown()
    alice.server_close()
    start_service("alice", 9201)
    c.register("alice", f"{HOST}:9201")
    c.send("alice", "Vẫn tìm được bạn bằng tên!")


if __name__ == "__main__":
    main()
