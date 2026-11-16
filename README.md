# Bài lab Hệ thống phân tán (bản thu gọn)

Mỗi bài lab làm theo phần cuối slide trong thư mục tương ứng, chỉ giữ phần cốt lõi.
Lab 1 dùng Node.js, lab 2–12 dùng Python 3.

**Thư viện cần cài:**
- Lab 2–8, 12: không cần thư viện ngoài.
- Lab 9, 10: `pip install cryptography` (AES).
- Lab 11: `pip install flask`.

Trên Windows, nếu tiếng Việt bị lỗi font, chạy `set PYTHONIOENCODING=utf-8` trước.

| Lab | Slide | Nội dung | Chạy |
|---|---|---|---|
| lab1 | Lect01 – Latency Hiding | Form đăng ký: kiểm tra ở server và ở client, đo chênh lệch | `cd lab1 && npm install && node server.js` rồi `node measure.js` (xem `lab1/README.md`) |
| lab2 | Lect02 – Mini DHT | Vòng Chord 10 node trên TCP socket, finger table O(log N), đăng ký tên → địa chỉ, nhắn tin cho dịch vụ kể cả sau khi nó đổi port | `python lab2/mini_dht.py` |
| lab3 | Lect03 – Logical Clock Simulator | 3 thread giao tiếp qua queue, Lamport + Vector clock, phát hiện sự kiện song song (`\|\|`) | `python lab3/logical_clocks.py` |
| lab4 | Lect04 – Leader Election | Thuật toán Bully, 5 tiến trình dùng UDP socket, heartbeat, tắt leader P5 → bầu được P4 | `python lab4/bully_election.py` |
| lab5 | Lect05 – 2PC Simulator | 1 Coordinator + 3 Participant trên TCP, ghi WAL ra `lab5/logs/`; Tx 101 bị abort vì P3 xung đột khóa; Tx 102 có P2 crash rồi khôi phục từ WAL | `python lab5/two_phase_commit.py` |
| lab6 | Lect06 – Quorum (*) | N=5 bản sao, kiểm tra luật NR+NW>N và NW>N/2, so sánh cấu hình hợp lệ và không hợp lệ (đọc ra dữ liệu cũ) | `python lab6/quorum.py` |
| lab7 | Lect07 – Session Proxy | Proxy giữ V_read / V_write, bảo đảm Monotonic Reads và Read-Your-Writes trên 3 server S1–S3 bị lệch nhau; xung đột ghi giải quyết bằng nhãn Lamport | `python lab7/session_proxy.py` |
| lab8 | Lect08 – Gossip & Quorum | 5 replica TCP, quorum Gifford (NR, NW), gossip Push-Pull mỗi 2s, xóa bằng Tombstone, ghi trùng version phân thắng thua bằng ID client | `python lab8/gossip_quorum.py` (~10 giây) |
| lab9 | Lect09 – Secure RPC & KDC | KDC + Alice + Bob qua TCP: Needham-Schroeder, AES-CBC, HMAC-SHA256, chống replay bằng nonce ở cả request và response | `python lab9/secure_rpc.py` |
| lab10 | Lect10 – Secure Group Multicast & ABAC | Key Server giữ cây khóa LKH (N=8), đổi khóa khi Join / Leave, multicast mã hóa AES-256-GCM, ABAC kiểm tra Role + Time | `python lab10/secure_group.py` |
| lab11 | Lect11 – RESTful Order Service & OpenAPI | Flask REST API `/api/v1/orders`, status code chuẩn, JWT Bearer, HATEOAS `_links`, file `openapi.yaml` | `python lab11/client_demo.py` (tự bật server và gọi thử) |
| lab12 | Lect12 – DFS (NFS / HDFS) Simulator | 1 server + 3 client qua TCP: File Handle + VFS, cache Close-to-Open với TTL và mtime, chunk nhân bản 2x trên 3 thư mục DataNode | `python lab12/dfs_simulator.py` (~6 giây) |

(*) Lect06 không có đề lab riêng (slide 39–40 là Cache Coherence và case study), nên lab6 lấy theo phần Quorum Systems.

**Mục lục:**
- [Phần 1 – Review lab 1 → 9](#phần-1--review-lab-1--9)
- [Phần 2 – Lab 10 → 12 (làm mới)](#phần-2--lab-10--12-làm-mới)
- [Những phần đã lược bớt so với đề gốc](#những-phần-đã-lược-bớt-so-với-đề-gốc)

---

## Phần 1 – Review lab 1 → 9

Đã chạy lại cả 9 lab và đọc lại toàn bộ code. Cả 9 đều chạy đúng, ra kết quả như mô tả.
Mỗi bài dưới đây gồm: ý chính, cách làm, kết quả, và những điểm cần biết khi đi bảo vệ.
Ba lỗi tìm thấy khi review lab 7, 8, 9 **đã được sửa trong code** (xem mục "Đã sửa sau review" của từng lab). Các "điểm còn thiếu" khác chỉ được ghi lại, chưa sửa.

### Lab 1 – Latency Hiding
- **Ý chính:** mạng WAN chậm, nên việc gì làm được ở client thì làm ở client để người dùng khỏi phải chờ.
- **Cách làm:** một file luật `public/rules.js` dùng chung cho trình duyệt, server và `measure.js`, nên client và server luôn kiểm tra giống nhau. Server giả lập độ trễ 300ms.
- **Kết quả (đo lại):** kiểm tra ở server mất khoảng 355ms, kiểm tra ở client khoảng 0,05ms.
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
- **Lưu ý:** đã đặt `seed` nhưng thứ tự chạy của các thread vẫn do hệ điều hành quyết định, nên mỗi lần chạy kết quả hơi khác nhau (lần chạy lại này có 4 dòng `CONFLICT`). Điều này là bình thường.

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
3. *Xung đột ghi:* S1 ghi `theme='dark'` và S2 ghi `theme='light'` song song. Ba server nhận hai write theo ba thứ tự khác nhau nhưng cùng ra `'light'`.
4. Chạy lại kịch bản 1 và 2 với proxy **tắt kiểm tra** (`enforce=False`) để thấy lỗi xảy ra: đọc ra `None`, và email bị biến mất.

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

**Đã sửa sau review:**
- **Lỗi cũ:** khi áp một write lấy từ server khác, code gán thẳng `data[key] = value`. Nếu hai server cùng ghi một key, giá trị cuối phụ thuộc vào **thứ tự áp**, nên các server có thể lệch nhau mãi.
- **Cách sửa:** mỗi write mang thêm nhãn `(Lamport timestamp, server gốc)`. Giá trị của key là write có nhãn **lớn nhất** (last-writer-wins).
  - Write tạo ra sau khi đã thấy write khác thì có nhãn lớn hơn, nên thứ tự nhân quả được giữ.
  - Hai write song song có nhãn bằng nhau thì server ID lớn hơn thắng. Luật này giống nhau ở mọi server nên tất cả hội tụ.
- **Sửa kèm:** write đến sai thứ tự (ví dụ S3#2 tới trước S3#1) trước đây bị bỏ qua. Giờ nó được giữ trong `pending` và áp khi write đứng trước đã tới.

```
[SYSTEM] S1 ghi theme='dark' (nhãn 1, S1) || S2 ghi theme='light' (nhãn 1, S2)
[S1] theme = 'light' | Clock = (1, 1, 0)
[S2] theme = 'light' | Clock = (1, 1, 0)
[S3] theme = 'light' | Clock = (1, 1, 0)
[SYSTEM] S1 ghi tiếp theme='blue' (nhãn 2) -> S2 theme = 'blue'
[SYSTEM] S1 nhận write S3#2 trước S3#1: note = None, đang chờ 1 write -> nhận nốt S3#1: note = 'b'
```

**Review (điểm cần biết):**
- Chỉ làm 2 trong 4 bảo đảm client-centric (đúng theo đề). Chưa có Monotonic Writes và Writes-Follow-Reads.
- Last-writer-wins **bỏ đi** một trong hai write song song (ở trên là `'dark'`) mà không báo cho ai. Hệ cần giữ cả hai thì phải trả cả hai bản cho ứng dụng tự gộp.
- Proxy hỏi **mọi** server để tìm write thiếu, và `V_read` gộp cả clock của server chứ không chỉ các write liên quan tới key vừa đọc. Cách này an toàn nhưng chặt hơn mức cần thiết.

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
5. **Hai client ghi cùng lúc:** client 1 ghi `'Dave'` vào S1–S3, client 2 ghi `'Erin'` vào S3–S5, cả hai đều tính ra Ver 1. Sau gossip, cả 5 replica đều là `'Erin'`.

**Đã sửa sau review:**
- **Lỗi cũ:** client đọc version rồi mới ghi, giữa hai bước không có khóa, nên hai client ghi cùng lúc có thể ra **cùng version với hai giá trị khác nhau**. `merge` chỉ đổi khi version lớn hơn hẳn, nên hai giá trị đó tồn tại mãi và gossip không làm chúng hội tụ.
- **Cách sửa:** mỗi bản ghi mang thêm `writer` (ID của client). Bản mới hơn là bản có `(version, writer)` lớn hơn (hàm `rank`). Luật này dùng ở cả ba chỗ: gossip `merge`, đọc theo quorum, và xử lý `WRITE` ở replica.
- **Sửa kèm:** replica trước đây nhận `WRITE` là ghi đè luôn. Giờ nó chỉ nhận nếu bản mới có `rank` lớn hơn, nên bản thua tới sau không đè được bản thắng.
- Việc ghi được tách thành `prepare` (đọc version) và `commit` (gửi bản ghi) để demo dựng lại được đúng tình huống hai client xen kẽ nhau.

```
[CLIENT 1] chuẩn bị ghi 'Dave' Ver 1 -> S1,S2,S3 | [CLIENT 2] chuẩn bị ghi 'Erin' Ver 1 -> S3,S4,S5
[SYSTEM] Trước gossip (cùng Ver, khác giá trị):
    S1: user3='Dave' (Ver 1)   S2: 'Dave'   S3: 'Erin'   S4: 'Erin'   S5: 'Erin'
[SYSTEM] Sau gossip (hội tụ sau 0.5s): client ID 2 > 1 nên 'Erin' thắng trên mọi replica
[CLIENT] Read key='user3' (NR=3) versions [S1:1, S2:1, S3:1] -> 'Erin'
```
(Đoạn trên đã gộp 5 dòng trạng thái thành 1 dòng cho gọn.)

**Review (điểm cần biết):**
- Phân thắng thua bằng ID client là last-writer-wins: bản `'Dave'` bị bỏ mà client 1 không được báo. Cả hai client đều nhận ACK.
- Ghi không có rollback: nếu một replica trong quorum ghi chết giữa chừng, `rpc` ném lỗi và các replica đã ghi vẫn giữ bản mới. Demo không tắt replica nào.
- Tombstone không bao giờ được dọn, nên bộ nhớ lớn dần theo số lần xóa. Hệ thật (ví dụ Cassandra) dọn sau một khoảng thời gian đủ dài để mọi node đã nhận.
- Thời gian hội tụ thay đổi theo mỗi lần chạy, vì peer được chọn ngẫu nhiên và các thread chạy không cố định.

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
5. **Replay response:** Balance đã đổi thành 50. Kẻ tấn công chặn response thật của `Read('Balance')` và phát lại response cũ (Balance = 600). Client báo `RESPONSE REPLAY DETECTED!` và bỏ qua; đọc lại ra 50.

**Đã sửa sau review:**
- **Lỗi cũ:** chống replay mới làm một chiều. Bob kiểm tra nonce của request, nhưng Alice không kiểm tra nonce trong response (hàm `send` chỉ lấy `result`). Một response cũ vẫn có HMAC đúng, nên kẻ tấn công có thể phát lại nó cho một request mới và Alice sẽ tin.
- **Cách sửa:** Alice nhớ nonce của từng gói đã gửi và so với nonce trong response. Không khớp thì bỏ qua.
- **Sửa kèm:** mỗi gói ghi thêm chiều đi (`dir` = `req` hoặc `resp`) bên trong phần được mã hóa. Hai chiều dùng chung khóa K_AB, nên nếu không có trường này, kẻ tấn công có thể gửi ngược một request về cho Alice làm response (reflection).
- Alice cũng kiểm tra HMAC của response trong `try`, thay vì để chương trình dừng khi response bị sửa.

```
[ATTACKER] Chặn response thật, phát lại response cũ (Balance = 600) cho client...
[CLIENT] RESPONSE REPLAY DETECTED! Response mang nonce 332412424, request vừa gửi là 174335966 -> bỏ qua.
[CLIENT] Response nonce khớp | RPC result = 50
```

**Review (điểm cần biết):**
- Needham-Schroeder gốc có lỗ hổng: nếu K_AB cũ bị lộ, kẻ tấn công có thể phát lại Ticket cũ (slide 28). Cách sửa của Denning-Sacco là thêm timestamp vào Ticket. Bản lab này chưa làm phần đó, và Ticket cũng chưa có thời hạn.
- Tập nonce đã dùng (`seen`) lớn dần mãi trong suốt phiên. Hệ thật thường kèm timestamp để chỉ cần nhớ nonce trong một khoảng thời gian.
- Khóa dài hạn K_A, K_B được sinh sẵn khi chương trình khởi động (coi như đã đăng ký với KDC từ trước).

**Bài tập số (slide 37–38):**
- RSA với p=3, q=11: n=33, φ=20, e=3, d=7. Mã hóa 4 được 31, giải mã 31 được lại 4.
- 100 máy dùng khóa đôi một cần 4950 khóa; dùng KDC chỉ cần 100 khóa.
- Threshold signature với c=2 server bị chiếm: cần m = c+1 = 3 phần chữ ký.
- Diffie-Hellman với p=23, g=5, a=6, b=15: A=8, B=19, khóa chung K=2.

### Tóm tắt review
| Lab | Đúng yêu cầu chính | Điểm còn thiếu (có thể bổ sung nếu cần) |
|---|---|---|
| 1 | ✔ | — |
| 2 | ✔ | join/stabilize khi node vào/ra |
| 3 | ✔ | — |
| 4 | ✔ | khóa cho `in_election`; trace phụ thuộc thời gian |
| 5 | ✔ | kịch bản coordinator crash (blocking) |
| 6 | ✔ (tự chọn đề) | demo xung đột version khi NW ≤ N/2 |
| 7 | ✔ | Monotonic Writes, Writes-Follow-Reads (đề không yêu cầu). *Đã sửa:* xung đột khi 2 server ghi cùng key; write đến sai thứ tự |
| 8 | ✔ | dọn tombstone; rollback khi ghi dở. *Đã sửa:* 2 lần ghi trùng version không hội tụ |
| 9 | ✔ | timestamp trong Ticket (Denning-Sacco). *Đã sửa:* replay response; phản chiếu gói tin |

---

## Phần 2 – Lab 10 → 12 (làm mới)

### Lab 10 – Secure Group Multicast & ABAC (`lab10/secure_group.py`)

**Đề (slide 36–40):**
1. Cây khóa nhị phân LKH để đổi khóa nhóm khi có thành viên vào (Join) hoặc ra (Leave).
2. Mã hóa payload multicast bằng AES-256-GCM với khóa gốc của nhóm.
3. ABAC Policy Engine kiểm tra Subject, Action và Time.
4. In trace cho thấy số rekey block là O(log N).

**Vấn đề cần giải quyết:** cả nhóm dùng chung một khóa để đọc tin multicast. Mỗi khi có người vào hoặc ra, khóa đó phải đổi.
- Nếu chỉ có một khóa chung (Flat Group Key), khi một người rời nhóm thì server phải gửi khóa mới **riêng cho từng người còn lại**: N−1 tin nhắn.
- LKH xếp thành viên vào lá của một cây khóa. Khi đổi khóa, chỉ cần đổi các khóa trên **một đường** từ lá lên gốc: khoảng log N tin nhắn.

**Cây khóa (N=8, cao h=3):**
```
                 K_0                 <- khóa gốc = khóa nhóm
           K_1         K_2           <- KEK (khóa dùng để mã hóa khóa khác)
         K_3  K_4    K_5  K_6
        7  8  9 10  11 12 13 14      <- lá: khóa riêng của từng thành viên
```
Mỗi thành viên chỉ giữ khóa lá của mình và các khóa trên đường lên gốc: h + 1 = 4 khóa.
Ví dụ thành viên ở lá 14 giữ `K_14, K_6, K_2, K_0`.

**Cách làm:**
- **Key Server** là một TCP server (port 9701), giữ cây trong bộ nhớ, biết thành viên nào ở lá nào.
- **Client** mở một kết nối TCP và một thread nghe. Mỗi client có một khóa riêng đã đăng ký trước với server (chính là khóa lá).
- **"Multicast"** được giả lập bằng cách server gửi cùng một frame cho **mọi** socket đang nối, kể cả client chưa vào nhóm hoặc đã rời nhóm. Giống multicast thật: ai cũng nghe được, chỉ người có khóa mới đọc được.
- **Join:** mỗi khóa trên đường đi được đổi mới.
  - Người cũ nhận khóa mới qua multicast, mã hóa bằng **khóa cũ của chính nút đó**: h = 3 block.
  - Người mới nhận khóa qua unicast, mã hóa bằng khóa lá của họ.
- **Leave:** mỗi khóa trên đường đi được đổi mới, khóa mới mã hóa bằng khóa của **từng nút con**. Không tạo block nào cho lá của người rời. Các block xếp từ dưới lên, nên client giải mã được khóa tầng dưới rồi dùng nó mở block tầng trên.
- **Gửi tin:** client gửi yêu cầu publish cho server (mã hóa bằng khóa riêng). Server chạy ABAC, đạt thì mã hóa bằng `K_0` và multicast.
- **AES-256-GCM** vừa mã hóa vừa xác thực. Số version của khóa được đưa vào AAD, nên một block của version cũ không dùng lại được cho version mới.
- **ABAC:** `ALLOW IF Role == 'Publisher' AND Action == 'publish' AND 08:00 <= Time <= 18:00`. Thời gian là thuộc tính môi trường do demo truyền vào để thử được nhiều giờ khác nhau. Server còn kiểm tra thêm người gửi có còn trong nhóm không.

**Kịch bản và kết quả:**
1. Nhóm có 7 thành viên, `client_3` chưa vào nhưng đang nghe lén kênh. Gửi M1: thành viên đọc được, `client_3` thì không.
2. `client_3` vào nhóm: **3 block** rekey. `client_3` thử giải mã M1 đã ghi lại từ trước và **không được**. Tin M2 sau đó thì đọc được.
3. `client_7` rời nhóm nhưng vẫn nghe: **5 block** rekey (Flat Group Key cần 7 unicast). `client_7` không mở được block nào và không đọc được M3.
4. ABAC: Subscriber gửi tin bị từ chối; Publisher gửi lúc 23:30 bị từ chối; `client_7` đã rời bị từ chối; Publisher gửi lúc 17:59 được chấp nhận.

```
[CLIENT_3] Joining Group... LKH Rekey Sent: 3 Encrypted Blocks (h = log2 8 = 3).
[CLIENT_7] Received Rekey Msg (JOIN client_3) -> Updated Path Keys [K_2, K_0] to Root Key K_0 v9.
[CLIENT_7] Leaving Group... Executing Backward Secrecy Rekey.
[KEY_SERVER] Generated 5 Rekey Blocks (<= d*h = 2*3 = 6; Flat Group Key cần 7 unicast). Revoked client_7.
[CLIENT_7] Received Rekey Msg (LEAVE client_7) -> KHÔNG mở được block nào (vẫn giữ K_0 v9 cũ).
[ABAC_ENGINE] Policy Evaluation PASSED (Role = 'Publisher', Action = 'publish', Time = 11:00) -> Multicast Delivered.
[KEY_SERVER] Multicast Dispatch: AES-256-GCM Payload Encrypted under Root Key K_0 (v10).
[CLIENT_7] CANNOT decrypt message from client_1 (không có K_0 v10).
```

Cuối chương trình tự kiểm tra 2 mục trong Verification Checklist của slide 39 (người mới không đọc được tin cũ, người đã rời không đọc được tin mới) và đều `PASS`.

**Lưu ý khi bảo vệ:**
- **Leave ra 5 block chứ không phải 6 như trace mẫu.** Công thức `d × h = 6` trong slide là mức trần: mỗi tầng 2 block. Ở tầng thấp nhất, một trong hai nút con chính là lá của người vừa rời nên không cần block cho nó. Số thật là `d × h − 1 = 5`. Chương trình in con số thật và ghi rõ `<= d*h`.
- **Tên gọi Forward / Backward Secrecy.** Slide 12 gọi Join là "Forward Secrecy" và Leave là "Backward Secrecy", và trace trong code đi theo slide. Nhiều tài liệu khác gọi ngược lại (backward secrecy: người mới không đọc được tin cũ; forward secrecy: người đã rời không đọc được tin mới). Nội dung bảo đảm thì giống nhau, chỉ khác tên.
- Key Server là điểm tin cậy duy nhất và cũng là điểm chết duy nhất. Nó biết mọi khóa và đọc được mọi tin.

**Bài tập số (slide 33–34):**
- RSA với p=5, q=11: n=55, φ=40, e=3, d=27 (vì 3×27 = 81 = 2×40 + 1). Mã hóa 9 được 9³ mod 55 = 14; giải mã 14²⁷ mod 55 = 9.
- Diffie-Hellman với p=23, g=5, a=4, b=3: A = 5⁴ mod 23 = 4, B = 5³ mod 23 = 10, khóa chung K = 10⁴ mod 23 = 4³ mod 23 = 18.
- LKH với N=1024, d=2: cao h = 10; mỗi thành viên giữ 11 khóa; Leave cần 2×10 = 20 block, so với 1023 tin nhắn của Flat Group Key, giảm khoảng 98%.

### Lab 11 – RESTful Order Management Service & OpenAPI (`lab11/`)

**Đề (slide 38–39):** dịch vụ REST mức Richardson Level 2 trở lên, có tài liệu OpenAPI 3.0.
1. Resource URI `/api/v1/orders` với GET, POST, PUT, DELETE.
2. Status code: 200, 201, 400, 404, 409.
3. Bộ lọc xác thực JWT Bearer Token.
4. HATEOAS `_links` cho các bước chuyển trạng thái (Pay, Cancel, Ship).
5. File OpenAPI 3.0 YAML hợp lệ.

**File:**
| File | Vai trò |
|---|---|
| `order_service.py` | Server Flask. Chạy riêng: `python lab11/order_service.py` (port 5000) |
| `client_demo.py` | Tự bật server trên port 5011 rồi gọi thử toàn bộ kịch bản qua HTTP thật |
| `openapi.yaml` | Hợp đồng OpenAPI 3.0.3. Server cũng trả file này ở `GET /api/v1/openapi.yaml` |

**Vòng đời đơn hàng:**
```
CREATED --pay--> PAID --ship--> SHIPPED
   \--cancel--> CANCELLED
```

**Bảng API:**
| Verb + URI | Việc làm | Status code |
|---|---|---|
| `POST /auth/login` | Đăng nhập, nhận JWT | 200, 400, 401 |
| `GET /orders` (`?status=`) | Danh sách đơn | 200 |
| `POST /orders` | Tạo đơn, trả header `Location` | 201, 400 |
| `GET /orders/{id}` | Xem một đơn | 200, 404 |
| `PUT /orders/{id}` | Thay toàn bộ `item`, `quantity` | 200, 400, 404, 409 |
| `DELETE /orders/{id}` | Xóa đơn | 204, 404, 409 |
| `POST /orders/{id}/pay` \| `cancel` \| `ship` | Chuyển trạng thái | 200, 403 (ship), 404, 409 |

Mọi URI dưới `/orders` đều cần `Authorization: Bearer <token>`, thiếu hoặc sai thì 401.

**Cách làm:**
- **Mức Richardson:** URI là danh từ (Level 1), dùng đúng verb và status code (Level 2), có `_links` (Level 3).
- **409 Conflict** dùng khi request đúng định dạng nhưng **trái với trạng thái hiện tại**: xóa đơn đã thanh toán, thanh toán hai lần, sửa đơn đã giao.
- **JWT (HS256)** tự viết bằng `hmac` và `base64` của thư viện chuẩn, để thấy rõ cấu trúc `header.payload.signature`.
  - Payload chứa `sub` (tên), `role`, `exp` (hạn dùng).
  - Server kiểm tra chữ ký **trước** rồi mới đọc payload, và luôn tính bằng HS256 chứ không tin trường `alg` do client gửi.
  - Server **không giữ session**: mọi thông tin người dùng nằm trong token. Đây là ràng buộc Stateless của REST, nên request nào cũng có thể vào bất kỳ server nào sau load balancer.
- **Bộ lọc** là `before_request` của Flask, chạy trước mọi handler. `after_request` in trace theo mẫu của slide.
- **HATEOAS:** hàm `links_for` chỉ đưa ra những bước **hợp lệ** với trạng thái hiện tại.

  | Trạng thái | `_links` (ngoài `self`, `collection`) |
  |---|---|
  | CREATED | `update`, `pay`, `cancel`, `delete` |
  | PAID | `ship` |
  | SHIPPED | — |
  | CANCELLED | `delete` |

  Client demo không tự ghép URL `/pay`, `/ship`: nó đọc `href` và `method` trong `_links` của response trước rồi gọi theo.
- **Idempotent:** PUT và DELETE gửi lại nhiều lần thì trạng thái server vẫn như gửi một lần (DELETE lần hai trả 404 nhưng server không đổi gì thêm). POST tạo đơn thì không idempotent: gửi hai lần ra hai đơn.
- **Phân quyền:** `ship` chỉ dành cho role `staff`. Role lấy từ JWT, sai role thì 403.

**Kết quả (rút gọn, giống trace mẫu slide 39):**
```
[HTTP GET /api/v1/orders] -> 401 UNAUTHORIZED | Thiếu header Authorization: Bearer <token>
[HTTP POST /api/v1/orders] -> 201 CREATED | JWT Validated (alice/customer) | Order 102 created (state CREATED).
[HTTP GET /api/v1/orders/102] -> 200 OK | JWT Validated (alice/customer) | Payload + HATEOAS _links returned.
[HTTP POST /api/v1/orders/102/pay] -> 200 OK | JWT Validated (alice/customer) | State Updated to PAID.
[HTTP DELETE /api/v1/orders/102] -> 409 CONFLICT | JWT Validated (alice/customer) | Cannot delete paid order.
[HTTP POST /api/v1/orders/102/ship] -> 403 FORBIDDEN | JWT Validated (alice/customer) | Chỉ role 'staff' được ship đơn hàng
[HTTP POST /api/v1/orders/102/ship] -> 200 OK | JWT Validated (staff/staff) | State Updated to SHIPPED.
```
Demo kiểm tra 18 tình huống và cả 18 đều ra đúng status code mong đợi. Trong đó có 4 tình huống về JWT: không có token, sai mật khẩu, token bị sửa payload (tự đổi role thành `staff`), token hết hạn.

**Kiểm tra `openapi.yaml`:** đã chạy qua `openapi-spec-validator` và hợp lệ theo OpenAPI 3.0.3. Đã so với các route trong code: 9 operation khớp cả hai phía. Hai bước kiểm tra này làm bằng tay một lần, không nằm trong `client_demo.py`.

**Lưu ý khi bảo vệ:**
- File YAML được **viết tay** (design-first), không sinh tự động từ code. Sửa route thì phải sửa cả file này.
- Dữ liệu lưu trong bộ nhớ, tắt server là mất. Tài khoản mẫu (`alice` / `staff`) và mật khẩu viết thẳng trong code, chỉ để làm lab.
- Khóa ký JWT sinh ngẫu nhiên mỗi lần bật server, nên token cũ hết dùng được sau khi khởi động lại. Muốn cố định thì đặt biến môi trường `JWT_SECRET`.
- JWT không thu hồi được trước hạn (đây là cái giá của stateless). Đơn hàng có trường `owner` nhưng chưa giới hạn "chỉ chủ đơn mới được sửa".
- Chạy bằng server phát triển của Flask qua HTTP thường. Dùng thật thì cần HTTPS, vì token đi trong header ở dạng đọc được.

**Bài tập số (slide 36):**
- Cùng 200 byte dữ liệu: SOAP 1400 byte, REST/JSON 350 byte, gRPC 230 byte. gRPC nhỏ hơn SOAP 1 − 230/1400 ≈ 83,6% (slide ghi 83,5%); REST nhỏ hơn SOAP 75%.
- 1.000.000 GET/ngày × 10 KB = 10 GB. Cache trúng 85% thì chỉ 15% tới server gốc: 1,5 GB, tiết kiệm 8,5 GB.

### Lab 12 – Distributed File System: NFS / HDFS (`lab12/dfs_simulator.py`)

**Đề (slide 38–39):** 1 server (VFS / Metadata Manager) dùng socket và 3 client.
1. Sinh File Handle và bảng tra VFS.
2. Cache theo Close-to-Open consistency, kiểm tra lại bằng `mtime` khi hết TTL.
3. HDFS: nhân bản chunk 2x trên các thư mục DataNode giả lập.
4. In trace RPC.

**Kiến trúc:**
- **Server** (TCP port 9801) vừa là NFS server vừa là HDFS NameNode. Nó chỉ giữ **metadata** trong RAM:
  - bảng VFS: `path → inode`
  - inode: generation, mtime, size, danh sách chunk
  - chunk: nằm ở DataNode nào, CRC-32
- **DataNode** là một thư mục thật `lab12/datanodes/dn1..dn3`, mỗi chunk là một file. Mỗi DataNode có một thread gửi heartbeat.
- **Client** có kết nối TCP riêng và cache trong RAM.

**Phần NFS:**
- **File Handle** = băm của (Volume ID, Inode, Generation), ví dụ `0x2860A0`. Client coi nó là chuỗi mờ, không hiểu bên trong.
- **Stateless:** server không nhớ client nào đang mở file gì. RPC nào (`GETATTR`, `READ`, `WRITE`) cũng tự mang File Handle. Server crash rồi bật lại thì không có bảng "file đang mở" nào phải dựng lại.
- **Generation:** xóa file rồi tạo file mới, inode cũ được dùng lại nhưng generation tăng. Handle cũ vì thế không còn khớp, và server trả `ESTALE`. Nếu không có generation, client cầm handle cũ sẽ đọc nhầm sang file mới.
- **Cache phía client:**

  | Thao tác | Client làm gì |
  |---|---|
  | `OPEN` | **Luôn** gửi `GETATTR`. `mtime` khác bản cache thì bỏ cache, tải lại |
  | `READ` | Còn TTL: đọc cache, **không gửi RPC**. Hết TTL: `GETATTR` rồi so `mtime` |
  | `WRITE` | Chỉ ghi vào bộ đệm cục bộ |
  | `CLOSE` | Đẩy bộ đệm lên server |

- **Close-to-Open** nghĩa là: bên ghi `CLOSE` xong thì bên nào `OPEN` sau đó chắc chắn thấy bản mới. Ở giữa thì không bảo đảm.

**Phần HDFS:**
- File được cắt thành chunk 16 byte (HDFS thật là 128 MB; để nhỏ cho một câu văn cũng thành nhiều chunk).
- Mỗi chunk ghi vào 2 DataNode đang giữ ít chunk nhất.
- **Heartbeat:** DataNode nào im lặng quá 0,7 giây thì NameNode coi là chết, rồi chép các chunk bị thiếu từ bản còn sống sang DataNode khác cho đủ 2 bản.
- **CRC-32:** khi đọc, chunk nào sai checksum thì đọc bản còn lại và chép đè lên bản hỏng.

**Kịch bản và kết quả:**
1. `CLIENT_1` tạo file, ghi `v1`, close: 35 byte thành 3 chunk, mỗi chunk ở 2 DataNode. `CLIENT_2` lookup cùng path nhận **cùng handle**.
2. `CLIENT_2` ghi `v2` và close. `CLIENT_1` đọc ngay thì **vẫn ra `v1`** (TTL còn hạn, không hỏi server). Chờ hết TTL rồi đọc lại: `mtime` khác, bỏ cache, ra `v2`. Đây là điểm yếu NFS chấp nhận để đổi lấy tốc độ.
3. `CLIENT_3` ghi `v3` nhưng chưa close: `CLIENT_1` open vẫn thấy `v2`. `CLIENT_3` close, `CLIENT_1` open lại thì thấy `v3` ngay, không cần chờ TTL.
4. `CLIENT_2` xóa file rồi tạo lại cùng tên. `CLIENT_1` dùng handle cũ, nhận `ESTALE`, lookup lại và nhận handle mới.
5. `DataNode_2` chết: NameNode phát hiện mất heartbeat, chép Chunk 109 từ DataNode_1 sang DataNode_3.
6. Làm hỏng 1 byte của một chunk trên đĩa: CRC phát hiện, client vẫn đọc ra đúng nội dung.

```
[CLIENT_2] LOOKUP path='/docs/file.txt' -> Obtained FileHandle 0x2860A0.
[CLIENT_2] OPEN -> Fetched Attributes (mtime=17000011). Cached locally.
[SERVER] WRITE FileHandle 0x2860A0 by CLIENT_2 -> 24 bytes, 2 chunks x2 (mtime=17000026).
[CLIENT_1] READ -> 'v1: Hello distributed file systems!' (cache hit, TTL chưa hết, không gửi RPC nào).
[CLIENT_1] READ -> TTL expired -> Re-validated mtime (17000026 != 17000011). Local cache invalidated!
[SERVER] GETATTR FileHandle 0x2860A0 from CLIENT_1 -> ESTALE (stale file handle).
[HDFS_MASTER] DataNode_2 failed (no heartbeat for 0.7s)! 1 chunks under-replicated.
[HDFS_MASTER] Re-replicating Chunk 109: DataNode_1 -> DataNode_3 (2x restored).
[HDFS_MASTER] Checksum mismatch: Chunk 109 on DataNode_1 corrupted -> read from another replica and repaired.
```
Cuối chương trình tự kiểm tra 8 mục và cả 8 đều `PASS`. Số `mtime` và số chunk thay đổi nhẹ giữa các lần chạy.

**Lưu ý khi bảo vệ:**
- **Bài này ghép hai mô hình vào một server** vì đề yêu cầu cả hai. NFS thật cho ghi đè ngẫu nhiên; HDFS thật chỉ ghi một lần rồi đọc nhiều lần (WORM) và client đọc dữ liệu **thẳng** từ DataNode. Ở đây server đứng giữa đọc/ghi chunk giúp client, và mỗi lần `WRITE` thay toàn bộ file.
- Các mốc thời gian được rút ngắn cho demo chạy nhanh:

  | Tham số | Trong lab | Hệ thật (theo slide) |
  |---|---|---|
  | TTL của attribute cache | 1 s | 3–60 s |
  | Chu kỳ heartbeat | 0,2 s | 3 s |
  | Coi DataNode là chết sau | 0,7 s | 10 phút |
  | Kích thước chunk | 16 byte | 128 MB |

- `mtime` là đồng hồ logic của server (luôn tăng), nên không phụ thuộc đồng hồ của client.
- Hai client cùng ghi một file thì ai close sau sẽ thắng (last-close-wins). Slide 8 cũng nói kết quả ghi đồng thời trong NFS là không xác định.
- Metadata chỉ nằm trong RAM. HDFS thật có edit log và FSImage để NameNode khởi động lại không mất metadata.
- Với 3 DataNode và nhân bản 2x, hệ chịu được **một** DataNode chết. Chết thêm một cái nữa thì không còn chỗ để nhân bản.

**Bài tập số (slide 36):**
- 1000 lần đọc 1 KB qua WAN có RTT 10 ms: NFS gửi 1000 RPC `READ`, mất 1000 × 10 ms = 10 giây. AFS tải cả file bằng 1 RPC `FETCH`, mất 10 ms. Nhanh hơn 1000 lần.
- File 1 TB (1.000.000 MB), block 128 MB, nhân bản 3x: ceil(1.000.000 / 128) = 7813 block. Dung lượng chiếm khoảng 3 TB.
  - Slide ghi `7.813 × 128 × 3 = 2.999.999 MB`, nhưng phép nhân đó thật ra bằng 3.000.192 MB.
  - Con số đúng hơn là 1.000.000 × 3 = 3.000.000 MB, vì block cuối chỉ chứa 64 MB và HDFS không chiếm đủ 128 MB cho block chưa đầy.

---

## Những phần đã lược bớt so với đề gốc
- Không viết báo cáo thiết kế riêng (lab 4, 5, 7, 10, 12). Phần giải thích nằm trong README này và trong docstring đầu mỗi file.
- Lab 2: dựng finger table trực tiếp từ danh sách node, không có giao thức join/stabilize; dùng socket, không dùng MPI.
- Lab 4, 8, 9, 10, 12: các "tiến trình" chạy trong 1 chương trình (mỗi thread có một socket riêng), cho dễ chạy và dễ xem log.
- Lab 7: 3 server là object trong cùng chương trình (đề không bắt buộc socket). Độ trễ mạng được giả lập bằng việc write chưa lan sang server khác.
- Lab 8: gossip gửi toàn bộ dữ liệu mỗi lần (không dùng digest hay Merkle tree), đủ dùng cho dữ liệu nhỏ.
- Lab 9: chưa có Denning-Sacco (timestamp trong Ticket) và chưa có thời hạn cho Ticket.
- Lab 10: cây có sức chứa cố định 8 lá, không tự lớn thêm. Multicast giả lập bằng TCP gửi cho mọi kết nối, không dùng IP multicast thật. Khóa riêng của client coi như đã đăng ký sẵn với Key Server.
- Lab 11: lưu trong bộ nhớ, không có CSDL. Không có Swagger UI; hợp đồng là file `openapi.yaml` viết tay.
- Lab 12: `WRITE` thay cả file, không ghi theo offset. Không có khóa file (NFSv4), không có Rack Awareness, NameNode không ghi edit log.
