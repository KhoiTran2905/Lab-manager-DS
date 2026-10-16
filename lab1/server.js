const express = require('express');
const validateForm = require('./public/rules.js');
const app = express();

// Độ trễ giả lập WAN (ms). Đổi bằng: LATENCY_MS=500 node server.js
const LATENCY_MS = Number(process.env.LATENCY_MS || 300);

app.use(express.urlencoded({ extended: false }));

// File tĩnh (validate.js) đặt TRƯỚC middleware delay để không bị cộng độ trễ
app.use(express.static('public'));

// Giả lập độ trễ mạng cho các request còn lại
app.use((req, res, next) => setTimeout(next, LATENCY_MS));

const esc = (s = '') =>
  String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function renderPage(errors = [], v = {}) {
  return `<!DOCTYPE html>
<html lang="vi">
<head><meta charset="utf-8"><title>Đăng ký (client + server)</title></head>
<body>
  <h1>Đăng ký tài khoản</h1>
  <ul id="errors" style="color:red">${errors.map(e => `<li>${esc(e)}</li>`).join('')}</ul>
  <form id="f" method="POST" action="/register" novalidate>
    <p><label>Username: <input name="username" value="${esc(v.username)}"></label></p>
    <p><label>Email: <input name="email" value="${esc(v.email)}"></label></p>
    <p><label>Mật khẩu: <input type="password" name="password"></label></p>
    <p><label>Nhập lại mật khẩu: <input type="password" name="confirm"></label></p>
    <button type="submit">Đăng ký</button>
  </form>
  <script src="/rules.js"></script>
  <script src="/validate.js"></script>
</body>
</html>`;
}

app.get('/', (req, res) => res.send(renderPage()));

app.post('/register', (req, res) => {
  // Express 5: req.body là undefined nếu request không có body -> dùng {}
  const body = req.body || {};
  // Server vẫn kiểm tra lại: không bao giờ tin dữ liệu từ client
  const errors = validateForm(body);

  if (errors.length) return res.status(400).send(renderPage(errors, body));
  res.send('<h1>Đăng ký thành công!</h1><a href="/">Quay lại</a>');
});

app.listen(3000, () => console.log(`http://localhost:3000 (latency giả lập: ${LATENCY_MS}ms)`));