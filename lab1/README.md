# Lab 1 – Architecting Latency Hiding

Đề (slide cuối Lect01): xây form đăng ký, so sánh kiểm tra dữ liệu ở server và ở client (JavaScript) để che giấu độ trễ WAN.

## Chạy

```
npm install
npm start                   # = node server.js, mặc định giả lập trễ 300ms (đổi: LATENCY_MS=800 node server.js)
npm run measure             # (terminal khác) đo chênh lệch
```

Mở http://localhost:3000.

- **Task 1** – `server.js`: form được kiểm tra ở server (`POST /register`), mỗi lần nhập sai phải chờ một vòng mạng.
- **Task 2** – `public/validate.js`: kiểm tra ngay trên trình duyệt, chặn submit nếu sai → phản hồi tức thì.
  Server vẫn kiểm tra lại (không tin client).
- `public/rules.js`: luật kiểm tra **dùng chung** cho trình duyệt, server và `measure.js`,
  nên dữ liệu nào client cho qua thì server cũng chấp nhận (không mất thêm một vòng mạng vì hai bên lệch luật).
- **Task 3** – `measure.js`: đo thời gian phản hồi khi gửi dữ liệu sai.

## Kết quả đo (LATENCY_MS=300)

| Cách kiểm tra | Thời gian phản hồi |
|---|---|
| Server-side | ~325–360 ms (trễ mạng + xử lý) |
| Client-side | ~0.03–0.05 ms |

## Các "8 False Assumptions" (Peter Deutsch) được giảm nhẹ

1. **The network is reliable** – lỗi nhập liệu được bắt ngay tại client, không cần mạng.
2. **Latency is zero** – đây là giả định chính: client không phải chờ round-trip để biết mình nhập sai.
3. **Bandwidth is infinite** – bớt các request lỗi gửi lên server.
4. **Transport cost is zero** – ít request hơn nên server/mạng tốn ít tài nguyên hơn.

Lưu ý: validate ở client chỉ để trải nghiệm người dùng nhanh; server **vẫn phải** kiểm tra lại.
