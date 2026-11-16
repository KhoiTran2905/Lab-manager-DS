"""
Lab 12 - Distributed File System (NFS / HDFS Protocol) Simulator.

Đề (Slide 38-39, Lect12): 1 Server (VFS / Metadata Manager) dùng socket + 3 Client.
  1. Sinh File Handle và bảng tra VFS (path -> inode -> handle).
  2. Cache phía client theo Close-to-Open consistency, kiểm tra lại bằng mtime khi hết TTL.
  3. HDFS: cắt file thành chunk, mỗi chunk nhân bản 2x trên các thư mục DataNode giả lập.
  4. In trace RPC giữa client và server.

Kiến trúc (1 chương trình, mỗi client có 1 kết nối TCP riêng):
  - Server = NFS server + HDFS NameNode: chỉ giữ METADATA trong RAM
        VFS table : path -> inode
        inode     : generation, mtime, size, danh sách chunk
        chunk     : nằm ở DataNode nào, CRC-32
    Server KHÔNG nhớ client nào đang mở file gì (stateless): RPC nào cũng tự mang File Handle.
  - DataNode = 1 thư mục thật trên đĩa (datanodes/dn1..dn3) + 1 thread gửi heartbeat.
  - Client: cache thuộc tính + dữ liệu trong RAM.
        OPEN  -> luôn GETATTR (so mtime), khác thì bỏ cache và tải lại
        READ  -> còn TTL thì đọc cache, KHÔNG hỏi server (có thể đọc ra dữ liệu cũ);
                 hết TTL thì GETATTR để kiểm tra lại
        WRITE -> chỉ ghi vào bộ đệm cục bộ
        CLOSE -> đẩy bộ đệm lên server (lúc này client khác OPEN mới thấy)

Chạy:  python dfs_simulator.py     (~6 giây)
"""
import hashlib
import json
import os
import shutil
import socket
import socketserver
import threading
import time
import zlib

HOST, PORT = "127.0.0.1", 9801
HERE = os.path.dirname(os.path.abspath(__file__))
DN_ROOT = os.path.join(HERE, "datanodes")
VOLUME_ID = 1
CHUNK_SIZE = 16             # byte. HDFS thật là 128 MB; để nhỏ cho 1 câu văn cũng thành nhiều chunk
REPLICATION = 2
ATTR_TTL = 1.0              # giây. NFS thật là 3-60 s; để ngắn cho demo chạy nhanh
HEARTBEAT = 0.2             # HDFS thật: 3 s
DEAD_AFTER = 0.7            # HDFS thật: 10 phút
print_lock = threading.Lock()


def say(text):
    with print_lock:
        print(text)


# ---------------- DataNode: 1 thư mục + heartbeat ----------------
class DataNode:
    def __init__(self, name, master):
        self.name = name
        self.dir = os.path.join(DN_ROOT, name)
        self.alive = True
        os.makedirs(self.dir)
        threading.Thread(target=self.heartbeat_loop, args=(master,), daemon=True).start()

    def heartbeat_loop(self, master):
        while self.alive:
            master.last_seen[self.name] = time.time()
            time.sleep(HEARTBEAT)

    def path(self, chunk_id):
        return os.path.join(self.dir, f"chunk_{chunk_id}")

    def put(self, chunk_id, data):
        with open(self.path(chunk_id), "wb") as f:
            f.write(data)

    def get(self, chunk_id):
        with open(self.path(chunk_id), "rb") as f:
            return f.read()

    def drop(self, chunk_id):
        if os.path.exists(self.path(chunk_id)):
            os.remove(self.path(chunk_id))

    def crash(self):
        """Máy chết, mất luôn ổ đĩa."""
        self.alive = False
        shutil.rmtree(self.dir)


# ---------------- Server: NFS (VFS + File Handle) + HDFS NameNode ----------------
class Server:
    def __init__(self):
        self.vfs = {}               # path -> inode
        self.inodes = {}            # inode -> {"gen", "mtime", "size", "chunks"}
        self.handles = {}           # file handle -> (inode, generation)
        self.generation = {}        # inode -> generation (còn nhớ sau khi file bị xóa)
        self.free_inodes = []       # inode đã giải phóng, sẽ được dùng lại
        self.next_inode = 1
        self.chunks = {}            # chunk_id -> {"replicas": [tên DataNode], "crc": CRC-32}
        self.next_chunk = 101
        self.clock = 17000000       # mtime logic (ms), luôn tăng
        self.t0 = time.time()
        self.lock = threading.RLock()
        self.last_seen = {}
        self.datanodes = {f"dn{i}": DataNode(f"dn{i}", self) for i in (1, 2, 3)}
        self.dead = set()
        threading.Thread(target=self.monitor, daemon=True).start()

    # ----- NFS: file handle + VFS -----
    def new_mtime(self):
        self.clock = max(self.clock + 1, 17000000 + int((time.time() - self.t0) * 1000))
        return self.clock

    def make_handle(self, inode):
        """File handle = (Volume ID, Inode, Generation) băm lại thành chuỗi mờ (opaque) với client."""
        gen = self.generation[inode]
        fh = "0x" + hashlib.sha1(f"{VOLUME_ID}:{inode}:{gen}".encode()).hexdigest()[:6].upper()
        self.handles[fh] = (inode, gen)
        return fh

    def resolve(self, fh):
        """Handle -> inode. Inode đã bị xóa hoặc đã cấp cho file khác (generation khác) -> ESTALE."""
        inode, gen = self.handles.get(fh, (None, None))
        node = self.inodes.get(inode)
        if node is None or node["gen"] != gen:
            return None
        return node

    def handle(self, msg):
        with self.lock:
            op, who = msg["op"], msg["client"]
            if op == "CREATE":
                inode = self.free_inodes.pop() if self.free_inodes else self.next_inode
                if inode == self.next_inode:
                    self.next_inode += 1
                self.generation[inode] = self.generation.get(inode, 0) + 1
                self.inodes[inode] = {"gen": self.generation[inode], "mtime": self.new_mtime(),
                                      "size": 0, "chunks": []}
                self.vfs[msg["path"]] = inode
                fh = self.make_handle(inode)
                say(f"[SERVER] CREATE path={msg['path']!r} by {who} -> inode {inode}, "
                    f"generation {self.generation[inode]}, FileHandle {fh}.")
                return {"fh": fh}
            if op == "LOOKUP":
                inode = self.vfs.get(msg["path"])
                if inode is None:
                    return {"error": "ENOENT"}
                return {"fh": self.make_handle(inode)}
            if op == "REMOVE":
                inode = self.vfs.pop(msg["path"], None)
                if inode is None:
                    return {"error": "ENOENT"}
                self.free_chunks(self.inodes.pop(inode)["chunks"])
                self.free_inodes.append(inode)
                say(f"[SERVER] REMOVE path={msg['path']!r} by {who} -> inode {inode} freed.")
                return {"ok": True}
            node = self.resolve(msg["fh"])          # các RPC còn lại đều tự mang file handle
            if node is None:
                say(f"[SERVER] {op} FileHandle {msg['fh']} from {who} -> ESTALE (stale file handle).")
                return {"error": "ESTALE"}
            if op == "GETATTR":
                return {"mtime": node["mtime"], "size": node["size"]}
            if op == "READ":
                data = b"".join(self.read_chunk(c) for c in node["chunks"])
                return {"data": data.decode(), "mtime": node["mtime"]}
            if op == "WRITE":
                self.free_chunks(node["chunks"])
                node["chunks"] = self.store(msg["data"].encode())
                node["size"], node["mtime"] = len(msg["data"]), self.new_mtime()
                say(f"[SERVER] WRITE FileHandle {msg['fh']} by {who} -> {node['size']} bytes, "
                    f"{len(node['chunks'])} chunks x{REPLICATION} (mtime={node['mtime']}).")
                return {"mtime": node["mtime"]}
            return {"error": "EINVAL"}

    # ----- HDFS: cắt chunk + nhân bản -----
    def live(self):
        return [d for d in self.datanodes.values() if d.name not in self.dead]

    def load(self, dn):
        return sum(dn.name in c["replicas"] for c in self.chunks.values())

    def store(self, data):
        ids = []
        for i in range(0, len(data), CHUNK_SIZE):
            piece = data[i:i + CHUNK_SIZE]
            cid, self.next_chunk = self.next_chunk, self.next_chunk + 1
            targets = sorted(self.live(), key=self.load)[:REPLICATION]      # chọn DataNode đang ít chunk nhất
            for dn in targets:
                dn.put(cid, piece)
            self.chunks[cid] = {"replicas": [d.name for d in targets], "crc": zlib.crc32(piece)}
            ids.append(cid)
        return ids

    def free_chunks(self, ids):
        for cid in ids:
            for name in self.chunks.pop(cid)["replicas"]:
                if name not in self.dead:
                    self.datanodes[name].drop(cid)

    def read_chunk(self, cid):
        """Đọc từ replica đầu tiên có CRC đúng; replica hỏng thì chép đè lại từ replica lành."""
        meta, good, bad = self.chunks[cid], None, []
        for name in meta["replicas"]:
            data = self.datanodes[name].get(cid)
            if zlib.crc32(data) == meta["crc"]:
                good = data
                break
            bad.append(name)
        for name in bad:
            say(f"[HDFS_MASTER] Checksum mismatch: Chunk {cid} on DataNode_{name[2:]} corrupted -> "
                f"read from another replica and repaired.")
            if good is not None:
                self.datanodes[name].put(cid, good)
        if good is None:
            raise IOError(f"chunk {cid}: mọi replica đều hỏng")
        return good

    def monitor(self):
        """NameNode: DataNode nào im lặng quá DEAD_AFTER giây thì coi là chết -> nhân bản lại."""
        while True:
            time.sleep(HEARTBEAT)
            with self.lock:
                for name, seen in list(self.last_seen.items()):
                    if name not in self.dead and time.time() - seen > DEAD_AFTER:
                        self.dead.add(name)
                        self.re_replicate(name)

    def re_replicate(self, dead_name):
        lost = [cid for cid, c in self.chunks.items() if dead_name in c["replicas"]]
        say(f"[HDFS_MASTER] DataNode_{dead_name[2:]} failed (no heartbeat for {DEAD_AFTER}s)! "
            f"{len(lost)} chunks under-replicated.")
        for cid in lost:
            meta = self.chunks[cid]
            meta["replicas"].remove(dead_name)
            source = self.datanodes[meta["replicas"][0]]
            target = min((d for d in self.live() if d.name not in meta["replicas"]), key=self.load)
            target.put(cid, source.get(cid))
            meta["replicas"].append(target.name)
            say(f"[HDFS_MASTER] Re-replicating Chunk {cid}: DataNode_{source.name[2:]} -> "
                f"DataNode_{target.name[2:]} ({REPLICATION}x restored).")

    def chunk_map(self, path):
        with self.lock:
            node = self.inodes[self.vfs[path]]
            return {cid: sorted(self.chunks[cid]["replicas"]) for cid in node["chunks"]}

    def start(self):
        server = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                for line in self.rfile:
                    self.wfile.write((json.dumps(server.handle(json.loads(line))) + "\n").encode())
                    self.wfile.flush()

        socketserver.ThreadingTCPServer.allow_reuse_address = True
        srv = socketserver.ThreadingTCPServer((HOST, PORT), Handler)
        srv.daemon_threads = True
        threading.Thread(target=srv.serve_forever, daemon=True).start()


# ---------------- Client: cache + Close-to-Open ----------------
class Client:
    def __init__(self, name):
        self.name = name
        self.f = socket.create_connection((HOST, PORT)).makefile("rw", encoding="utf-8")
        self.handles = {}       # path -> file handle (cache kết quả LOOKUP)
        self.cache = {}         # path -> {"mtime", "data", "checked": lúc kiểm tra gần nhất}
        self.dirty = {}         # path -> dữ liệu đã WRITE nhưng chưa CLOSE
        self.rpcs = 0

    def log(self, text):
        say(f"[{self.name}] {text}")

    def rpc(self, op, **args):
        self.rpcs += 1
        self.f.write(json.dumps(dict(args, op=op, client=self.name)) + "\n")
        self.f.flush()
        return json.loads(self.f.readline())

    def lookup(self, path):
        if path not in self.handles:
            reply = self.rpc("LOOKUP", path=path)
            if "error" in reply:
                raise FileNotFoundError(path)
            self.handles[path] = reply["fh"]
            self.log(f"LOOKUP path={path!r} -> Obtained FileHandle {reply['fh']}.")
        return self.handles[path]

    def file_rpc(self, op, path, **args):
        """RPC có kèm file handle. Gặp ESTALE thì bỏ handle + cache cũ, LOOKUP lại rồi gửi lại."""
        reply = self.rpc(op, fh=self.lookup(path), **args)
        if reply.get("error") == "ESTALE":
            self.log(f"{op} -> ESTALE: FileHandle {self.handles[path]} hết hiệu lực. Bỏ cache, LOOKUP lại.")
            del self.handles[path]
            self.cache.pop(path, None)
            reply = self.rpc(op, fh=self.lookup(path), **args)
        return reply

    def revalidate(self, path, why):
        """GETATTR rồi so mtime với bản cache. Khác -> bỏ cache, tải lại."""
        attrs = self.file_rpc("GETATTR", path)
        entry = self.cache.get(path)
        if entry is None:
            self.log(f"{why} -> Fetched Attributes (mtime={attrs['mtime']}). Cached locally.")
        elif entry["mtime"] == attrs["mtime"]:
            entry["checked"] = time.time()
            self.log(f"{why} -> Re-validated mtime ({attrs['mtime']} == {entry['mtime']}). Cache still valid.")
            return
        else:
            self.log(f"{why} -> Re-validated mtime ({attrs['mtime']} != {entry['mtime']}). "
                     f"Local cache invalidated!")
        fresh = self.file_rpc("READ", path)
        self.cache[path] = {"mtime": fresh["mtime"], "data": fresh["data"], "checked": time.time()}

    def create(self, path):
        self.handles[path] = self.rpc("CREATE", path=path)["fh"]
        self.cache[path] = {"mtime": None, "data": "", "checked": 0}

    def open(self, path):
        self.revalidate(path, "OPEN")           # close-to-open: OPEN luôn hỏi server

    def read(self, path):
        entry = self.cache[path]
        if path in self.dirty:
            data, note = self.dirty[path], "đọc bộ đệm của chính mình"
        elif time.time() - entry["checked"] < ATTR_TTL:
            data, note = entry["data"], "cache hit, TTL chưa hết, không gửi RPC nào"
        else:
            self.revalidate(path, "READ -> TTL expired")
            data, note = self.cache[path]["data"], "sau khi kiểm tra lại"
        self.log(f"READ -> {data!r} ({note}).")
        return data

    def write(self, path, data):
        self.dirty[path] = data
        self.log(f"WRITE {data!r} -> buffered locally (chưa gửi server).")

    def close(self, path):
        if path in self.dirty:
            data = self.dirty.pop(path)
            mtime = self.file_rpc("WRITE", path, data=data)["mtime"]
            self.cache[path] = {"mtime": mtime, "data": data, "checked": time.time()}
            self.log(f"CLOSE -> flushed dirty buffer to server (mtime={mtime}).")
        else:
            self.log("CLOSE.")

    def remove(self, path):
        self.rpc("REMOVE", path=path)
        self.handles.pop(path, None)
        self.cache.pop(path, None)


def show_chunks(server, path):
    for cid, replicas in server.chunk_map(path).items():
        print(f"    Chunk {cid}: {', '.join('DataNode_' + r[2:] for r in replicas)}")


def main():
    shutil.rmtree(DN_ROOT, ignore_errors=True)      # xóa dữ liệu của lần chạy trước
    server = Server()
    server.start()
    c1, c2, c3 = Client("CLIENT_1"), Client("CLIENT_2"), Client("CLIENT_3")
    path = "/docs/file.txt"
    results = []

    print("===== 1. File Handle + VFS lookup; ghi file -> cắt chunk, nhân bản 2x =====")
    c1.create(path)
    c1.write(path, "v1: Hello distributed file systems!")
    c1.close(path)
    show_chunks(server, path)
    c2.open(path)
    same = c1.handles[path] == c2.handles[path]
    print(f"  -> 2 client LOOKUP cùng 1 path nhận cùng 1 handle: {same}")
    results.append(("LOOKUP cho cùng handle", same))

    print("\n===== 2. Cache + TTL: đọc ra dữ liệu CŨ trong lúc TTL còn hạn =====")
    c1.open(path)
    c2.write(path, "v2: modified by CLIENT_2")
    c2.close(path)
    stale = c1.read(path)                           # trong TTL: không hỏi server -> vẫn là v1
    results.append(("Trong TTL: đọc bản cũ (điểm yếu của NFS)", stale.startswith("v1")))
    time.sleep(ATTR_TTL + 0.1)
    fresh = c1.read(path)                           # hết TTL: GETATTR, mtime khác -> tải lại
    results.append(("Hết TTL: mtime khác -> tải lại bản mới", fresh.startswith("v2")))

    print("\n===== 3. Close-to-Open: chỉ thấy bản mới sau khi bên ghi CLOSE và bên đọc OPEN lại =====")
    c3.open(path)
    c3.write(path, "v3: written by CLIENT_3, chua close")
    c1.open(path)
    before = c1.read(path)                          # C3 chưa close -> server vẫn là v2
    c3.close(path)
    c1.open(path)                                   # OPEN lại: luôn GETATTR, không chờ TTL
    after = c1.read(path)
    results.append(("Trước khi CLOSE: client khác chưa thấy", before.startswith("v2")))
    results.append(("Sau CLOSE + OPEN lại: thấy ngay", after.startswith("v3")))

    print("\n===== 4. Generation trong File Handle: xóa rồi tạo lại file cùng tên -> ESTALE =====")
    old = c1.handles[path]
    c2.remove(path)
    c2.create(path)                                 # dùng lại đúng inode cũ, generation tăng
    c2.write(path, "v4: file MOI cung ten")
    c2.close(path)
    time.sleep(ATTR_TTL + 0.1)
    data = c1.read(path)                            # handle cũ -> ESTALE -> LOOKUP lại
    results.append(("Handle cũ bị từ chối, LOOKUP lại ra handle mới",
                    data.startswith("v4") and c1.handles[path] != old))

    print("\n===== 5. HDFS: DataNode_2 chết -> NameNode tự nhân bản lại cho đủ 2x =====")
    show_chunks(server, path)
    say("[SYSTEM] DataNode_2 crashed (mất cả ổ đĩa, ngừng gửi heartbeat).")
    server.datanodes["dn2"].crash()
    time.sleep(DEAD_AFTER + 3 * HEARTBEAT)
    show_chunks(server, path)
    chunk_map = server.chunk_map(path)
    ok = all(len(r) == REPLICATION and "dn2" not in r for r in chunk_map.values())
    results.append(("Mọi chunk lại đủ 2 bản, không còn ở DataNode_2", ok))

    print("\n===== 6. HDFS: 1 replica bị hỏng dữ liệu -> CRC-32 phát hiện, đọc bản còn lại =====")
    cid, replicas = next(iter(chunk_map.items()))
    with open(server.datanodes[replicas[0]].path(cid), "r+b") as f:
        f.write(b"X")                               # làm hỏng 1 byte trên đĩa
    say(f"[SYSTEM] Làm hỏng 1 byte của Chunk {cid} trên DataNode_{replicas[0][2:]}.")
    c3.open(path)
    data = c3.read(path)
    results.append(("Đọc vẫn đúng dù 1 replica hỏng", data == "v4: file MOI cung ten"))

    print("\n===== Tổng kết =====")
    for name, good in results:
        print(f"  {'PASS' if good else 'FAIL'}  {name}")
    print(f"  Số RPC đã gửi: CLIENT_1 = {c1.rpcs}, CLIENT_2 = {c2.rpcs}, CLIENT_3 = {c3.rpcs}")
    if not all(good for _, good in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
