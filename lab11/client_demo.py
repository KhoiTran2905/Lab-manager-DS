"""
Lab 11 - Client demo: tự bật order_service trên 1 thread rồi gọi thử toàn bộ kịch bản qua HTTP thật.

Dòng "[HTTP ...]" là trace của SERVER; dòng "   client:" là thứ client nhìn thấy.
Client KHÔNG tự ghép URL /pay, /cancel, /ship: nó đi theo `_links` trong response (HATEOAS).

Chạy:  python client_demo.py
"""
import json
import logging
import threading
import urllib.error
import urllib.request

from werkzeug.serving import make_server

import order_service as svc

HOST, PORT = "127.0.0.1", 5011
BASE = f"http://{HOST}:{PORT}"


def call(method, path, token=None, body=None):
    """Gửi 1 request. Trả về (status, headers, json hoặc None)."""
    req = urllib.request.Request(BASE + path, method=method,
                                 data=None if body is None else json.dumps(body).encode())
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        resp = urllib.request.urlopen(req, timeout=5)
    except urllib.error.HTTPError as e:
        resp = e                        # 4xx cũng là một response bình thường
    raw = resp.read()
    return resp.status, resp.headers, json.loads(raw) if raw else None


def show(status, data):
    if data and "error" in data:
        print(f"   client: {status} | {data['error']['message']}")
    elif data and "status" in data:
        print(f"   client: {status} | order {data['id']} {data['status']} item={data['item']!r} "
              f"x{data['quantity']} | _links: {sorted(data['_links'])}")
    else:
        print(f"   client: {status}")


def follow(order, rel, token):
    """HATEOAS: lấy href + method từ _links của response trước đó."""
    link = order["_links"][rel]
    return call(link["method"], link["href"], token)


def login(username, password):
    status, _, data = call("POST", "/api/v1/auth/login", body={"username": username, "password": password})
    return data.get("access_token")


def main():
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    svc.seed()
    server = make_server(HOST, PORT, svc.app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    checks = []                         # (mô tả, đúng/sai) để tổng kết cuối bài

    def expect(name, status, want):
        checks.append((name, status == want, status, want))

    print("===== 1. Bộ lọc JWT =====")
    s, _, d = call("GET", "/api/v1/orders")
    show(s, d); expect("Không có token", s, 401)
    alice = login("alice", "alice123")
    s, _, d = call("POST", "/api/v1/auth/login", body={"username": "alice", "password": "sai"})
    show(s, d); expect("Sai mật khẩu", s, 401)
    head, payload, sig = alice.split(".")
    forged = svc.b64url(json.dumps({"sub": "alice", "role": "staff", "exp": 9999999999}).encode())
    s, _, d = call("GET", "/api/v1/orders", token=f"{head}.{forged}.{sig}")     # tự sửa role thành staff
    show(s, d); expect("Token bị sửa payload", s, 401)
    s, _, d = call("GET", "/api/v1/orders", token=svc.make_token("alice", "customer", ttl=-1))
    show(s, d); expect("Token hết hạn", s, 401)

    print("\n===== 2. POST tạo đơn: 400 và 201 =====")
    s, _, d = call("POST", "/api/v1/orders", alice, {"item": "Laptop", "quantity": 0})
    show(s, d); expect("POST body sai", s, 400)
    s, h, order = call("POST", "/api/v1/orders", alice, {"item": "Laptop", "quantity": 2})
    show(s, order); expect("POST tạo đơn", s, 201)
    print(f"   client: header Location = {h['Location']}")

    print("\n===== 3. GET + PUT (idempotent) =====")
    s, _, order = call("GET", h["Location"], alice)
    show(s, order); expect("GET đơn hàng", s, 200)
    for _ in range(2):                  # gửi PUT 2 lần giống hệt -> trạng thái server như gửi 1 lần
        s, _, order = call("PUT", order["_links"]["update"]["href"], alice, {"item": "Laptop", "quantity": 3})
        show(s, order)
    expect("PUT thay đơn hàng", s, 200)
    s, _, d = call("GET", "/api/v1/orders/999", alice)
    show(s, d); expect("GET đơn không tồn tại", s, 404)

    print("\n===== 4. HATEOAS: đi theo _links.pay rồi thử xóa đơn đã thanh toán =====")
    s, _, order = follow(order, "pay", alice)
    show(s, order); expect("Pay", s, 200)
    s, _, d = call("DELETE", order["_links"]["self"]["href"], alice)
    show(s, d); expect("DELETE đơn PAID", s, 409)
    s, _, d = call("POST", order["_links"]["self"]["href"] + "/pay", alice)     # cố gọi lại pay (không còn trong _links)
    show(s, d); expect("Pay lần 2", s, 409)

    print("\n===== 5. Ship: role lấy từ JWT (403 với customer, 200 với staff) =====")
    s, _, d = follow(order, "ship", alice)
    show(s, d); expect("Ship bằng customer", s, 403)
    staff = login("staff", "staff123")
    s, _, order = follow(order, "ship", staff)
    show(s, order); expect("Ship bằng staff", s, 200)

    print("\n===== 6. Cancel rồi DELETE (idempotent) =====")
    s, _, other = call("GET", "/api/v1/orders/101", alice)
    show(s, other)
    s, _, other = follow(other, "cancel", alice)
    show(s, other); expect("Cancel", s, 200)
    s, _, d = follow(other, "delete", alice)
    show(s, d); expect("DELETE đơn CANCELLED", s, 204)
    s, _, d = call("DELETE", other["_links"]["self"]["href"], alice)    # xóa lại: 404, server không đổi gì thêm
    show(s, d); expect("DELETE lần 2", s, 404)
    s, _, d = call("GET", "/api/v1/orders", alice)
    print(f"   client: {s} | còn {len(d['items'])} đơn: {[(o['id'], o['status']) for o in d['items']]}")

    print("\n===== 7. Hợp đồng OpenAPI =====")
    resp = urllib.request.urlopen(f"{BASE}/api/v1/openapi.yaml")
    spec = resp.read().decode()
    print(f"   client: {resp.status} | {spec.splitlines()[0]} | {len(spec.splitlines())} dòng YAML")
    expect("GET openapi.yaml", resp.status, 200)

    print("\n===== Tổng kết status code =====")
    for name, ok, got, want in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name:26s} -> {got} (mong đợi {want})")
    server.shutdown()
    if not all(ok for _, ok, _, _ in checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
