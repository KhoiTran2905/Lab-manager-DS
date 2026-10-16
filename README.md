# Bài lab Hệ thống phân tán (bản thu gọn)

Mỗi bài lab làm theo phần cuối slide trong thư mục tương ứng, chỉ giữ phần cốt lõi.
Lab 2–6 viết bằng Python 3, không cần cài thư viện ngoài. Trên Windows, nếu tiếng Việt bị lỗi font, chạy
`set PYTHONIOENCODING=utf-8` trước.

| Lab | Slide | Nội dung | Chạy |
|---|---|---|---|
| lab1 | Lect01 – Latency Hiding | Form đăng ký: kiểm tra ở server và ở client, đo chênh lệch | `cd lab1 && npm install && node server.js` rồi `node measure.js` (xem `lab1/README.md`) |
| lab2 | Lect02 – Mini DHT | Vòng Chord 10 node trên TCP socket, finger table O(log N), đăng ký tên → địa chỉ, nhắn tin cho dịch vụ kể cả sau khi nó đổi port | `python lab2/mini_dht.py` |
| lab3 | Lect03 – Logical Clock Simulator | 3 thread giao tiếp qua queue, Lamport + Vector clock, phát hiện sự kiện song song (`\|\|`) | `python lab3/logical_clocks.py` |
| lab4 | Lect04 – Leader Election | Thuật toán Bully, 5 tiến trình dùng UDP socket, heartbeat, tắt leader P5 → bầu được P4 | `python lab4/bully_election.py` |
| lab5 | Lect05 – 2PC Simulator | 1 Coordinator + 3 Participant trên TCP, ghi WAL ra `lab5/logs/`; Tx 101 bị abort vì P3 xung đột khóa; Tx 102 có P2 crash rồi khôi phục từ WAL | `python lab5/two_phase_commit.py` |
| lab6 | Lect06 – Quorum (*) | N=5 bản sao, kiểm tra luật NR+NW>N và NW>N/2, so sánh cấu hình hợp lệ và không hợp lệ (đọc ra dữ liệu cũ) | `python lab6/quorum.py` |

(*) Lect06 không có đề lab riêng nên lab6 lấy theo phần Quorum Systems (slide 37–38).

## Những phần đã lược bớt so với đề gốc
- Không viết báo cáo thiết kế 2 trang (lab4, lab5).
- Lab2: dựng finger table trực tiếp từ danh sách node, không có giao thức join/stabilize; dùng socket, không dùng MPI.
- Lab4: tất cả tiến trình chạy trong 1 chương trình (các thread, mỗi thread một socket riêng).
