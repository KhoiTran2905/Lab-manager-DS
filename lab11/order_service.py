"""
Lab 11 - RESTful Order Management Service & OpenAPI Contract Simulator.

Đề (Slide 38-39, Lect11): dịch vụ REST mức Richardson Level 2+ (ở đây làm tới Level 3):
  1. Resource URI /api/v1/orders với các HTTP verb chuẩn (GET, POST, PUT, DELETE).
  2. Dùng đúng status code: 200, 201, 400, 404, 409 (thêm 204, 401, 403).
  3. Bộ lọc xác thực JWT Bearer Token.
  4. HATEOAS: mỗi response có `_links` cho các bước chuyển trạng thái (Pay, Cancel, Ship).
  5. Hợp đồng OpenAPI 3.0 dạng YAML: file openapi.yaml (server cũng trả ở /api/v1/openapi.yaml).

Vòng đời đơn hàng:
      CREATED --pay--> PAID --ship--> SHIPPED
         \\--cancel--> CANCELLED

Server KHÔNG giữ session: mọi thông tin người dùng nằm trong JWT (stateless).
JWT (HS256) tự viết bằng hmac + base64 của thư viện chuẩn để thấy rõ cấu trúc header.payload.signature.

Cần: pip install flask
Chạy server:  python order_service.py        (http://127.0.0.1:5000)
Chạy demo  :  python client_demo.py           (tự bật server rồi gọi thử toàn bộ kịch bản)
"""
import base64
import hashlib
import hmac
import json
import os
import threading
import time

from flask import Flask, g, jsonify, request, send_file
from werkzeug.exceptions import HTTPException

API = "/api/v1"
SECRET = os.environ.get("JWT_SECRET", "").encode() or os.urandom(32)   # khóa ký JWT, chỉ server biết
TOKEN_TTL = 3600
# Tài khoản mẫu cho bài lab (thật thì phải lưu hash mật khẩu trong CSDL)
USERS = {"alice": {"password": "alice123", "role": "customer"},
         "staff": {"password": "staff123", "role": "staff"}}

app = Flask(__name__)
orders = {}                 # id -> đơn hàng (lưu trong bộ nhớ)
next_id = [101]
lock = threading.Lock()


# ---------------- JWT (HS256) ----------------
def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64url_decode(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign(signing_input):
    return b64url(hmac.new(SECRET, signing_input.encode(), hashlib.sha256).digest())


def make_token(username, role, ttl=TOKEN_TTL):
    header = b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = b64url(json.dumps({"sub": username, "role": role, "exp": int(time.time()) + ttl}).encode())
    return f"{header}.{payload}.{sign(header + '.' + payload)}"


def verify_token(token):
    """Trả về claims nếu token hợp lệ; sai thì ném ValueError kèm lý do."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("token sai định dạng")
    header, payload, signature = parts
    # Kiểm tra chữ ký TRƯỚC khi đọc nội dung; luôn tính bằng HS256, không tin trường "alg" của client
    if not hmac.compare_digest(signature.encode(), sign(header + "." + payload).encode()):
        raise ValueError("chữ ký không hợp lệ")
    claims = json.loads(b64url_decode(payload))     # chữ ký đúng -> payload do chính server tạo ra
    if claims.get("exp", 0) < time.time():
        raise ValueError("token đã hết hạn")
    return claims


# ---------------- Tiện ích ----------------
def error(status, message):
    g.note = message
    resp = jsonify({"error": {"status": status, "message": message}})
    resp.status_code = status
    if status == 401:
        resp.headers["WWW-Authenticate"] = "Bearer"
    return resp


def links_for(order):
    """HATEOAS: chỉ đưa ra những bước chuyển HỢP LỆ với trạng thái hiện tại."""
    url = f"{API}/orders/{order['id']}"
    links = {"self": {"href": url, "method": "GET"},
             "collection": {"href": f"{API}/orders", "method": "GET"}}
    if order["status"] == "CREATED":
        links["update"] = {"href": url, "method": "PUT"}
        links["pay"] = {"href": f"{url}/pay", "method": "POST"}
        links["cancel"] = {"href": f"{url}/cancel", "method": "POST"}
        links["delete"] = {"href": url, "method": "DELETE"}
    elif order["status"] == "PAID":
        links["ship"] = {"href": f"{url}/ship", "method": "POST"}
    elif order["status"] == "CANCELLED":
        links["delete"] = {"href": url, "method": "DELETE"}
    return links


def view(order):
    """Representation gửi cho client = dữ liệu + _links (không lộ cấu trúc lưu trữ bên trong)."""
    return dict(order, _links=links_for(order))


def parse_order_body():
    """Kiểm tra body của POST / PUT. Trả về (dữ liệu, None) hoặc (None, thông báo lỗi)."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return None, "Body phải là JSON object"
    item, qty = body.get("item"), body.get("quantity")
    if not isinstance(item, str) or not item.strip():
        return None, "'item' phải là chuỗi khác rỗng"
    if isinstance(qty, bool) or not isinstance(qty, int) or qty < 1:
        return None, "'quantity' phải là số nguyên >= 1"
    return {"item": item.strip(), "quantity": qty}, None


# ---------------- Bộ lọc JWT + ghi trace ----------------
@app.before_request
def jwt_filter():
    g.note = ""
    if not request.path.startswith(f"{API}/orders"):
        return None                         # /auth/login và /openapi.yaml là công khai
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return error(401, "Thiếu header Authorization: Bearer <token>")
    try:
        g.user = verify_token(auth[7:])
    except ValueError as e:
        return error(401, f"JWT không hợp lệ: {e}")
    return None


@app.after_request
def trace(resp):
    who = f"JWT Validated ({g.user['sub']}/{g.user['role']}) | " if "user" in g else ""
    print(f"[HTTP {request.method} {request.path}] -> {resp.status} | {who}{g.get('note', '')}", flush=True)
    return resp


@app.errorhandler(HTTPException)
def http_error(e):
    return error(e.code, e.description)     # 404 / 405 của Flask cũng trả JSON cùng định dạng


# ---------------- Xác thực ----------------
@app.post(f"{API}/auth/login")
def login():
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or "username" not in body or "password" not in body:
        return error(400, "Cần JSON gồm 'username' và 'password'")
    user = USERS.get(body["username"])
    if user is None or not hmac.compare_digest(str(body["password"]), user["password"]):
        return error(401, "Sai tên đăng nhập hoặc mật khẩu")
    g.note = f"Issued JWT for {body['username']} (role={user['role']})"
    return jsonify({"access_token": make_token(body["username"], user["role"]),
                    "token_type": "Bearer", "expires_in": TOKEN_TTL})


# ---------------- Collection: /orders ----------------
@app.get(f"{API}/orders")
def list_orders():
    status = request.args.get("status")
    with lock:
        items = [view(o) for o in orders.values() if status is None or o["status"] == status]
    g.note = f"{len(items)} orders + HATEOAS _links returned."
    return jsonify({"items": items, "_links": {"self": {"href": f"{API}/orders", "method": "GET"},
                                               "create": {"href": f"{API}/orders", "method": "POST"}}})


@app.post(f"{API}/orders")
def create_order():
    data, problem = parse_order_body()
    if problem:
        return error(400, problem)
    with lock:
        oid = next_id[0]
        next_id[0] += 1
        orders[oid] = {"id": oid, "status": "CREATED", "owner": g.user["sub"], **data}
        body = view(orders[oid])
    g.note = f"Order {oid} created (state CREATED)."
    resp = jsonify(body)
    resp.status_code = 201
    resp.headers["Location"] = f"{API}/orders/{oid}"     # 201 Created luôn kèm địa chỉ resource mới
    return resp


# ---------------- Một đơn hàng: /orders/{id} ----------------
@app.get(f"{API}/orders/<int:oid>")
def get_order(oid):
    with lock:
        order = orders.get(oid)
        if order is None:
            return error(404, f"Không có order {oid}")
        g.note = "Payload + HATEOAS _links returned."
        return jsonify(view(order))


@app.put(f"{API}/orders/<int:oid>")
def replace_order(oid):
    """PUT = thay TOÀN BỘ phần client được sửa (item, quantity). Gửi lại nhiều lần vẫn ra cùng kết quả."""
    data, problem = parse_order_body()
    if problem:
        return error(400, problem)
    with lock:
        order = orders.get(oid)
        if order is None:
            return error(404, f"Không có order {oid}")      # id do server cấp nên PUT không tạo mới
        if order["status"] != "CREATED":
            return error(409, f"Cannot modify order in state {order['status']}.")
        order.update(data)
        g.note = "Order replaced."
        return jsonify(view(order))


@app.delete(f"{API}/orders/<int:oid>")
def delete_order(oid):
    with lock:
        order = orders.get(oid)
        if order is None:
            return error(404, f"Không có order {oid}")
        if order["status"] in ("PAID", "SHIPPED"):
            return error(409, f"Cannot delete {order['status'].lower()} order.")
        del orders[oid]
    g.note = "Order deleted."
    return "", 204


# ---------------- Chuyển trạng thái: /orders/{id}/pay | cancel | ship ----------------
TRANSITIONS = {"pay": ("CREATED", "PAID"), "cancel": ("CREATED", "CANCELLED"), "ship": ("PAID", "SHIPPED")}


@app.post(f"{API}/orders/<int:oid>/<any(pay, cancel, ship):action>")
def transition(oid, action):
    need, target = TRANSITIONS[action]
    if action == "ship" and g.user["role"] != "staff":
        return error(403, "Chỉ role 'staff' được ship đơn hàng")
    with lock:
        order = orders.get(oid)
        if order is None:
            return error(404, f"Không có order {oid}")
        if order["status"] != need:
            return error(409, f"Cannot {action} order in state {order['status']} (cần {need}).")
        order["status"] = target
        g.note = f"State Updated to {target}."
        return jsonify(view(order))


# ---------------- Hợp đồng OpenAPI ----------------
@app.get(f"{API}/openapi.yaml")
def openapi():
    g.note = "OpenAPI 3.0 contract returned."
    return send_file(os.path.join(os.path.dirname(os.path.abspath(__file__)), "openapi.yaml"),
                     mimetype="application/yaml")


def seed():
    """Dữ liệu mẫu: order 101 có sẵn, order tạo tiếp theo sẽ là 102 (giống trace mẫu trong slide)."""
    with lock:
        orders.clear()
        orders[101] = {"id": 101, "status": "CREATED", "owner": "alice", "item": "Keyboard", "quantity": 1}
        next_id[0] = 102


if __name__ == "__main__":
    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)   # chỉ giữ trace của mình
    seed()
    print("Order service: http://127.0.0.1:5000/api/v1/orders  (đăng nhập: POST /api/v1/auth/login)")
    app.run(host="127.0.0.1", port=5000)
