# Bài lab Hệ thống phân tán (bản thu gọn)

Mỗi bài lab làm theo phần cuối slide trong thư mục tương ứng, chỉ giữ phần cốt lõi.
Lab 2–9 viết bằng Python 3. Lab 2–8 không cần thư viện ngoài; lab 9 cần `pip install cryptography` (để có AES).
Trên Windows, nếu tiếng Việt bị lỗi font, chạy `set PYTHONIOENCODING=utf-8` trước.

| Lab | Slide | Nội dung | Chạy |
|---|---|---|---|
| lab1 | Lect01 – Latency Hiding | Form đăng ký: kiểm tra ở server và ở client, đo chênh lệch | `cd lab1 && npm install && node server.js` rồi `node measure.js` (xem `lab1/README.md`) |
| lab2 | Lect02 – Mini DHT | Vòng Chord 10 node trên TCP socket, finger table O(log N), đăng ký tên → địa chỉ, nhắn tin cho dịch vụ kể cả sau khi nó đổi port | `python lab2/mini_dht.py` |
| lab3 | Lect03 – Logical Clock Simulator | 3 thread giao tiếp qua queue, Lamport + Vector clock, phát hiện sự kiện song song (`\|\|`) | `python lab3/logical_clocks.py` |
| lab4 | Lect04 – Leader Election | Thuật toán Bully, 5 tiến trình dùng UDP socket, heartbeat, tắt leader P5 → bầu được P4 | `python lab4/bully_election.py` |
| lab5 | Lect05 – 2PC Simulator | 1 Coordinator + 3 Participant trên TCP, ghi WAL ra `lab5/logs/`; Tx 101 bị abort vì P3 xung đột khóa; Tx 102 có P2 crash rồi khôi phục từ WAL | `python lab5/two_phase_commit.py` |
| lab6 | Lect06 – Quorum (*) | N=5 bản sao, kiểm tra luật NR+NW>N và NW>N/2, so sánh cấu hình hợp lệ và không hợp lệ (đọc ra dữ liệu cũ) | `python lab6/quorum.py` |
| lab7 | Lect07 – Session Proxy | Proxy giữ V_read / V_write, bảo đảm Monotonic Reads và Read-Your-Writes trên 3 server S1–S3 bị lệch nhau | `python lab7/session_proxy.py` |
| lab8 | Lect08 – Gossip & Quorum | 5 replica TCP, quorum Gifford (NR, NW), gossip Push-Pull mỗi 2s, xóa bằng Tombstone | `python lab8/gossip_quorum.py` (~10 giây) |
| lab9 | Lect09 – Secure RPC & KDC | KDC + Alice + Bob qua TCP: Needham-Schroeder, AES-CBC, HMAC-SHA256, chống replay bằng nonce | `pip install cryptography` rồi `python lab9/secure_rpc.py` |

(*) Lect06 không có đề lab riêng (slide 39–40 là Cache Coherence và case study), nên lab6 lấy theo phần Quorum Systems.

---

## Phần 1 – Review lab 1 → 6

Đã chạy lại cả 6 lab, đều chạy đúng và ra kết quả như mô tả. Dưới đây là phân tích từng bài: ý chính, cách làm, và những điểm cần biết khi đi bảo vệ.

### Lab 1 – Latency Hiding
- **Ý chính:** mạng WAN chậm, nên việc gì làm được ở client thì làm ở client để người dùng khỏi phải chờ.
- **Cách làm:** một file luật `public/rules.js` dùng chung cho trình duyệt, server và `measure.js`, nên client và server luôn kiểm tra giống nhau. Server giả lập độ trễ 300ms.
- **Kết quả:** kiểm tra ở server mất khoảng 330ms, kiểm tra ở client chưa tới 0.1ms.
- **Điểm tốt:** server **vẫn** kiểm tra lại (không tin client). HTML được escape để chống XSS.
- **Lưu ý:** `measure.js` đo thời gian kiểm tra ở client bằng Node, không đo trong trình duyệt thật. Thời gian kiểm tra trong trình duyệt được in ra console.

### Lab 2 – Mini DHT (Chord)
- **Ý chính:** đặt tên phẳng (flat naming): tìm dịch vụ theo **tên** chứ không theo IP, nên dịch vụ đổi địa chỉ thì vẫn tìm được.
- **Cách làm:** 10 node có ID trên vòng 0..63 (m=6), `finger[i] = successor(n + 2^i)`, tra cứu đệ quy qua TCP. Tên `alice` được hash ra 40 và lưu ở Node 42.
- **Kết quả:** tra cứu mất 2 bước nhảy (≤ log₂10 ≈ 3,3). Alice đổi port 9200 → 9201, đăng ký lại, và tin nhắn vẫn tới được.
- **Hạn chế:** finger table tính sẵn từ danh sách node, không có `join` / `stabilize`, nên chưa xử lý được node vào hoặc ra khỏi vòng.

### Lab 3 – Lamport & Vector Clock
- **Ý chính:** Lamport clock chỉ cho thứ tự toàn phần, còn Vector clock phát hiện được hai sự kiện **song song**.
- **Cách làm:** 3 thread chỉ nói chuyện với nhau qua `queue`. Khi nhận tin: `L = max(L, L_msg) + 1` và `V = max từng phần tử` rồi tăng phần tử của mình.
- **Phát hiện song song:** nếu vector của tin nhận được và vector cục bộ không cái nào ≤ cái nào thì in `CONFLICT`. Ví dụ `[2,0,0] || [0,2,0]`.
- **Lưu ý:** đã đặt `seed` nhưng thứ tự chạy của các thread vẫn do hệ điều hành quyết định, nên mỗi lần chạy kết quả hơi khác nhau. Điều này là bình thường.

### Lab 4 – Bully Election
- **Ý chính:** tiến trình có ID lớn nhất còn sống sẽ làm leader.
- **Cách làm:** mỗi tiến trình có một UDP socket riêng. Leader gửi `HEARTBEAT`; quá 1s không nghe thấy thì gửi `ELECTION` cho các ID lớn hơn. Nếu có `OK` thì chờ, hết giờ chờ thì tự làm leader và gửi `COORDINATOR`.
- **Kết quả:** tắt P5, P2 phát hiện lỗi, P3 và P4 trả lời OK, P4 thắng và mọi tiến trình nhận P4 làm leader.
- **Lưu ý khi bảo vệ:**
  - Hàm `main` cố tình **làm chậm** P1, P3, P4 để P2 phát hiện lỗi trước, cho giống trace mẫu.
  - Cờ `in_election` không có khóa, nên đôi khi có thể có 2 cuộc bầu chạy cùng lúc. Kết quả cuối vẫn đúng vì Bully chịu được chuyện này.
  - Trên Windows, gửi UDP tới socket đã chết sẽ gây `ConnectionResetError`; code đã bỏ qua lỗi này.

### Lab 5 – Two-Phase Commit
- **Ý chính:** tất cả cùng commit hoặc tất cả cùng abort. WAL giúp khôi phục sau khi crash.
- **Cách làm:** mỗi bên ghi log, `flush` và `fsync` **trước** khi trả lời. Coordinator ghi quyết định vào log trước khi multicast.
- **Kịch bản:**
  - Tx 101: P3 bị khóa nên `VOTE_ABORT`, kết quả `GLOBAL_ABORT`.
  - Tx 102: P2 crash ở trạng thái READY. Khi khởi động lại, P2 đọc WAL, thấy `VOTE_COMMIT` mà chưa có quyết định, nên hỏi coordinator và nhận `GLOBAL_COMMIT`.
- **Hạn chế:**
  - Chưa mô phỏng trường hợp **coordinator crash**. Đây là điểm yếu lớn nhất của 2PC: participant ở trạng thái READY sẽ bị kẹt (blocking), và 3PC hoặc Paxos Commit sinh ra để giải quyết việc này.
  - Danh sách khóa không được lưu vào WAL.
  - Coordinator mặc định trả `GLOBAL_ABORT` khi không tìm thấy quyết định (presumed abort).

### Lab 6 – Quorum (N=5)
- **Ý chính:** hai luật của Gifford.
  - `NR + NW > N`: mọi quorum đọc đều giao với quorum ghi, nên đọc luôn thấy bản mới.
  - `NW > N/2`: hai quorum ghi luôn giao nhau, nên không có hai lần ghi xung đột cùng version.
- **Kết quả:**
  - (1, 5) và (3, 3) có 0 lần đọc cũ, kể cả khi 2 bản sao crash ở cấu hình (3, 3).
  - (2, 2) không hợp lệ: 3/10 lần đọc ra dữ liệu cũ.
- **Lưu ý:**
  - Version mới bằng max version trong quorum ghi cộng 1. Cách này chỉ đúng khi `NW > N/2`. Với (2, 2), hai lần ghi có thể ra cùng version mà khác giá trị, nhưng demo chưa in ra trường hợp này.
  - Lab 6 chạy trong bộ nhớ (không dùng socket) và trùng ý tưởng với lab 8. Lab 8 là bản đầy đủ hơn, có socket và gossip.

### Tóm tắt review
| Lab | Đúng yêu cầu chính | Điểm còn thiếu (có thể bổ sung nếu cần) |
|---|---|---|
| 1 | ✔ | — |
| 2 | ✔ | join/stabilize khi node vào/ra |
| 3 | ✔ | — |
| 4 | ✔ | khóa cho `in_election`; trace phụ thuộc thời gian |
| 5 | ✔ | kịch bản coordinator crash (blocking) |
| 6 | ✔ (tự chọn đề) | demo xung đột version khi NW ≤ N/2 |

---

## Phần 2 – Lab 7 → 9 (làm mới)

### Lab 7 – Client-Centric Session Proxy (`lab7/session_proxy.py`)

**Đề (slide 37–38):** viết một proxy nằm giữa client và 3 server S1, S2, S3. Proxy giữ `V_read` và `V_write`, bảo đảm **Monotonic Reads** và **Read-Your-Writes**, và khi client bị đẩy sang server cũ thì proxy phải lấy các write còn thiếu về.

**Hiểu nhanh:**
- Mỗi server có vector clock `(c1, c2, c3)`. `ci` là số write gốc từ Si mà server này đã có.
- `V_write`: những gì client **đã ghi**. Đọc ở server nào thì server đó phải có clock ≥ `V_write`. Đây là **Read-Your-Writes**: tôi phải thấy cái tôi vừa ghi.
- `V_read`: những gì client **đã đọc thấy**. Server phải có clock ≥ `V_read`. Đây là **Monotonic Reads**: dữ liệu không được "lùi về quá khứ".
- Nếu server chưa đủ thì proxy báo `Validation Failed`, lấy các write còn thiếu từ server khác (`missing_writes`) và áp vào server đó, rồi mới cho đọc.

**Cách làm (đơn giản):** 3 server là 3 object trong cùng chương trình. Sự lệch nhau giữa các server được giả lập bằng cách write chỉ nằm ở server nhận nó và không tự lan đi (giống mạng chậm hoặc chưa đồng bộ).

**Kịch bản:**
1. *Read-Your-Writes:* ghi `profile_name='Alice'` vào S1, rồi đọc ở S2 có clock (0,0,0). Proxy lấy W1 từ S1 nên đọc ra `'Alice'`.
2. *Monotonic Reads:* hộp thư ở S1 và S2 có 3 email, S3 có 5 email. Đọc S3 được 5 email; refresh thì bị đẩy sang S2. Proxy lấy write từ S3 về, nên vẫn thấy 5 email chứ không "mất" 2 email.
3. Chạy lại 2 kịch bản trên với proxy **tắt kiểm tra** (`enforce=False`) để thấy lỗi xảy ra: đọc ra `None`, và email bị biến mất.

**Kết quả (rút gọn, giống trace mẫu slide 38):**
```
[CLIENT] Write profile_name = 'Alice' -> Sent to Server S1
[S1] Write ACK | Client V_write updated to (1, 0, 0)
[SYSTEM] Routing CLIENT Read(profile_name) to Server S2... S2 Clock = (0, 0, 0)
[PROXY] Validation Failed! S2 Clock (0, 0, 0) < V_write (1, 0, 0) (Read-Your-Writes)
[PROXY] Fetching missing write profile_name='Alice' (S1#1) from S1 -> Applying to S2...
[S2] State Updated to (1, 0, 0)
[S2] Read executed -> Returns 'Alice' | V_read = (1, 0, 0)
[CLIENT] Read-Your-Writes Guarantee Preserved!
```

**Bài tập số (slide 35):**
- (2,0,1) < (3,1,1), nên hai sự kiện có quan hệ nhân quả.
- (2,0,1) và (2,2,0) không cái nào ≤ cái nào, nên chúng song song.
- `V_read = (4,2)`: chỉ replica có clock (5,3) phục vụ được. Replica có clock (4,1) phải chờ.

### Lab 8 – Gossip & Quorum Key-Value Store (`lab8/gossip_quorum.py`)

**Đề (slide 36–38):** 5 replica S1..S5 nói chuyện qua socket.
1. Quorum Gifford với NR, NW cấu hình được.
2. Gossip Push-Pull Anti-Entropy mỗi 2 giây.
3. Tombstone cho việc xóa.

Dữ liệu lưu dạng `key -> {value, version, tombstone}`.

**Cách làm:**
- Mỗi replica là một TCP server (thread) ở port 9501–9505, cộng thêm một thread gossip.
- **Ghi (NW=3):**
  1. Client hỏi version hiện tại trên NW replica.
  2. Version mới = lớn nhất + 1.
  3. Ghi vào NW replica đó.
  - Vì NW > N/2 nên luôn thấy version mới nhất.
- **Đọc (NR=3):** hỏi NR replica và lấy bản có version cao nhất. Nếu bản đó là tombstone thì coi như "không có".
- **Gossip Push-Pull:**
  1. Mỗi khoảng 2s, replica chọn ngẫu nhiên một peer.
  2. Replica gửi **toàn bộ** dữ liệu của mình (push) và nhận lại dữ liệu của peer (pull).
  3. Với từng key, bên nào có version lớn hơn thì thắng.
- **Tombstone:** xóa = ghi `{value: None, version: v+1, tombstone: True}`. Bản xóa này có version cao hơn nên lan đi được bằng gossip giống một write bình thường.

**Kịch bản và kết quả:**
1. Ghi `user1='Bob'` vào S1–S3 (lúc này gossip đang tắt), nên S4 và S5 còn cũ. Đọc từ **S3, S4, S5** vẫn ra `'Bob'`, vì quorum đọc chắc chắn chạm ít nhất một replica mới (ở đây là S3), đúng như luật `NR + NW > N`.
2. Bật gossip: sau khoảng 2s cả 5 replica có `'Bob' (Ver 1)`.
3. Xóa `user1` thì thành tombstone Ver 2. Gossip lan đi, và cả 5 node đều có `TOMBSTONE (Ver 2)`.
4. **So sánh:** xóa *thật* `user2` trên S1–S3 (không dùng tombstone). Khi gossip, S4 và S5 tưởng S1–S3 "chưa nhận" `user2` nên gửi lại, và `'Carol'` **sống lại** trên cả 5 node. Đây chính là lý do phải có Death Certificate.

**Bài tập số (slide 33–34):**
- N=7, NR=3, NW=5: 3+5=8 > 7 (PASS) và 5 > 3,5 (PASS).
- Ghi chịu được 7−5 = 2 node chết; đọc chịu được 7−3 = 4 node chết.
- Gossip 1024 node cần khoảng log₂1024 = 10 vòng.
- Push-Pull nhanh hơn Push ở các vòng cuối: lúc đó hầu hết node đã nhiễm, nên node chưa nhiễm tự đi **kéo** (pull) sẽ gần như chắc chắn gặp node có dữ liệu. Còn nếu chỉ push, phải chờ ai đó tình cờ chọn trúng đúng node chưa nhiễm.

### Lab 9 – Secure RPC & KDC (`lab9/secure_rpc.py`)

**Đề (slide 39–40):** 3 tiến trình socket: KDC, Client (Alice) và Server (Bob).
1. Xác thực bằng Needham-Schroeder.
2. Mã hóa RPC bằng AES-CBC với khóa phiên K_AB.
3. Gắn HMAC-SHA256 vào mọi message.
4. Dùng nonce để chống gửi lại gói tin (replay).

**Needham-Schroeder (bản khóa đối xứng):**
```
(1) A  -> KDC : A, B, R_A1
(2) KDC -> A  : E_KA( R_A1, B, K_AB, Ticket )      Ticket = E_KB( A, K_AB )
(3) A  -> B   : Ticket, E_KAB( R_A2 )
(4) B  -> A   : E_KAB( R_A2 - 1, R_B )
(5) A  -> B   : E_KAB( R_B - 1 )
```
- Bước 2: Alice kiểm tra `R_A1` khớp, nên biết đây là câu trả lời mới chứ không phải bị phát lại.
- Bước 4: Bob trả `R_A2 − 1`, chứng tỏ Bob giải mã được Ticket, tức Bob là thật.
- Bước 5: Alice trả `R_B − 1`, chứng tỏ Alice có K_AB, tức Alice là thật.

**Cách làm:**
- KDC (port 9601) và Bob (port 9602) là 2 TCP server chạy trên thread; Alice là client.
- `seal(key, obj)` mã hóa và gói tin theo kiểu **Encrypt-then-MAC**:
  1. Tạo IV ngẫu nhiên.
  2. Mã hóa bằng AES-256-CBC (padding PKCS7).
  3. Tính HMAC-SHA256 trên `IV + ciphertext`.
  - Từ mỗi khóa tách ra khóa AES và khóa HMAC riêng.
- `unseal` **kiểm tra HMAC trước**, đúng thì mới giải mã. Gói bị sửa sẽ bị từ chối ngay.
- **Chống replay:** mỗi RPC có một nonce ngẫu nhiên. Bob nhớ các nonce đã dùng trong phiên, nên gói trùng nonce sẽ bị từ chối.

**Kịch bản và kết quả:**
1. Bắt tay qua KDC, kết thúc với `Secure Channel Established with Server_Bob!`
2. `Write('Balance', 500)` và `Read('Balance')` cho `HMAC Verified OK`, trả về 500.
3. **Replay:** kẻ tấn công gửi lại y nguyên gói `Write('Balance', 600)`, và server báo `REPLAY DETECTED!`
4. **Sửa gói:** kẻ tấn công lật 1 bit trong gói `Write('Balance', 999)`, và server báo `HMAC Verification FAILED`. Đọc lại, Balance vẫn là 600.

**Lưu ý:**
- Needham-Schroeder gốc có lỗ hổng: nếu K_AB cũ bị lộ, kẻ tấn công có thể phát lại Ticket cũ (slide 28). Cách sửa của Denning-Sacco là thêm timestamp vào Ticket. Bản lab này chưa làm phần đó.
- Khóa dài hạn K_A, K_B được sinh sẵn khi chương trình khởi động (coi như đã đăng ký với KDC từ trước).

**Bài tập số (slide 37–38):**
- RSA với p=3, q=11: n=33, φ=20, e=3, d=7. Mã hóa 4 được 31, giải mã 31 được lại 4.
- 100 máy dùng khóa đôi một cần 4950 khóa; dùng KDC chỉ cần 100 khóa.
- Threshold signature với c=2 server bị chiếm: cần m = c+1 = 3 phần chữ ký.
- Diffie-Hellman với p=23, g=5, a=6, b=15: A=8, B=19, khóa chung K=2.

---

## Những phần đã lược bớt so với đề gốc
- Không viết báo cáo thiết kế riêng (lab 4, 5, 7). Phần giải thích nằm trong README này và trong docstring đầu mỗi file.
- Lab 2: dựng finger table trực tiếp từ danh sách node, không có giao thức join/stabilize; dùng socket, không dùng MPI.
- Lab 4, 8, 9: các "tiến trình" chạy trong 1 chương trình (mỗi thread có một socket riêng), cho dễ chạy và dễ xem log.
- Lab 7: 3 server là object trong cùng chương trình (đề không bắt buộc socket). Độ trễ mạng được giả lập bằng việc write chưa lan sang server khác.
- Lab 8: gossip gửi toàn bộ dữ liệu mỗi lần (không dùng digest hay Merkle tree), đủ dùng cho dữ liệu nhỏ.
- Lab 9: chưa có Denning-Sacco (timestamp trong Ticket) và chưa có thời hạn cho Ticket.
