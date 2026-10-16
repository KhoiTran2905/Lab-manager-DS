// Task 3: đo chênh lệch thời gian phản hồi khi gửi dữ liệu SAI
// - Server-side: phải đi một vòng mạng (round-trip) + độ trễ WAN giả lập
// - Client-side: kiểm tra ngay tại máy, không đi qua mạng
// Chạy server trước: node server.js   (rồi ở terminal khác) node measure.js
const validateLocal = require('./public/rules.js'); // đúng luật trình duyệt đang dùng

const N = 5;
const bad = { username: 'ab', email: 'sai-email', password: '123', confirm: '456' };

async function main() {
  let server = 0, local = 0;
  for (let i = 0; i < N; i++) {
    let t0 = performance.now();
    const res = await fetch('http://localhost:3000/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams(bad),
    });
    await res.text();
    server += performance.now() - t0;

    t0 = performance.now();
    validateLocal(bad);
    local += performance.now() - t0;
  }
  console.log(`Server-side validation (TB ${N} lần): ${(server / N).toFixed(2)} ms`);
  console.log(`Client-side validation (TB ${N} lần): ${(local / N).toFixed(4)} ms`);
  console.log(`=> Nhanh hơn khoảng ${(server / Math.max(local, 0.001)).toFixed(0)} lần`);
}

main().catch(e => console.error('Lỗi: hãy chạy "node server.js" trước.', e.message));
