# Final-AI

# Final Project: Introduction to Artificial Intelligence (503043)

| Phần | Bài toán | Thư mục code |
|---|---|---|
| [Task 1](#task-1-n-queens-propositional-logic-và-local-search) | N-Queens: Glucose3 và Min-Conflicts | [Task 1/](Task%201/) |
| [Task 2](#task-2-tank-battle-adversarial-search) | Tank Battle: tìm kiếm đối kháng | [Task 2/](Task%202/) |
| [Task 3](#task-3-kakuro-constraint-satisfaction-problem) | Kakuro: CSP | [Task 3/](Task%203/) |

Các mục chung (tối ưu hiệu năng, kiểm thử, lưu ý về số liệu, việc còn lại) nằm ở cuối tệp.

## Cài đặt

Code đã chạy thử trên Python 3.14.7. Cú pháp đã được kiểm tra tương thích với Python 3.9, nhưng code chưa được chạy trên bản đó.

```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

```powershell
# Windows
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Mỗi task chạy độc lập từ thư mục của nó. Lệnh cụ thể nằm ở mục "Cách chạy" của từng task bên dưới.

```bash
cd "Task 2"
python main.py
```

---

## Task 1: N-Queens (Propositional Logic và Local Search)

### Cách chạy

Chạy trong thư mục `Task 1`:

```bash
python main.py sat --n 8                                  # giải bằng Glucose3, mã hoá theo cặp
python main.py sat --n 200 --encoding sequential          # mã hoá sequential counter
python main.py minconflicts --n 8 --selector tabu         # giải bằng Min-Conflicts
python main.py experiment-sat                             # thí nghiệm yêu cầu 2
python main.py experiment-encoding                        # so sánh hai cách mã hoá
python main.py experiment-minconflicts                    # thí nghiệm yêu cầu 3
python -m unittest discover -s tests                      # kiểm thử
```

Kết quả thí nghiệm được ghi vào `results/*.csv`.

| Tệp | Vai trò |
|---|---|
| [nqueens/board.py](Task%201/nqueens/board.py) | `Placement`: biểu diễn lời giải, kiểm tra độc lập theo luật cờ |
| [nqueens/encoding.py](Task%201/nqueens/encoding.py) | `SquareVariables`, `ConstraintDiscovery`, `CnfEncoder`, `PairwiseEncoding`, `SequentialCounterEncoding` |
| [nqueens/sat_solver.py](Task%201/nqueens/sat_solver.py) | `Glucose3QueensSolver` |
| [nqueens/min_conflicts.py](Task%201/nqueens/min_conflicts.py) | `ConflictTracker`, các `VariableSelector`, `MinConflictsSolver` |
| [nqueens/experiments.py](Task%201/nqueens/experiments.py) | `SatExperiment`, `EncodingExperiment`, `MinConflictsExperiment` |

### Yêu cầu 1: Mô hình hoá bằng logic mệnh đề

**Biến.** Mỗi ô (r, c) ứng với một biến Q(r,c), đúng khi ô có quân hậu. Bàn N×N có N² biến, được đánh số `r·N + c + 1` theo chuẩn DIMACS.

**Ràng buộc.**

- Mỗi hàng có đúng một quân hậu.
- Mỗi cột có đúng một quân hậu.
- Mỗi đường chéo (cả hai hướng) có nhiều nhất một quân hậu.

Hai ràng buộc đầu đã đảm bảo có đúng N quân hậu trên bàn.

**Thuật toán phát hiện ràng buộc.** Hai ô tấn công nhau khi và chỉ khi chúng có chung một trong bốn khoá: `r` (hàng), `c` (cột), `r − c` (đường chéo), `r + c` (đường chéo phụ). Vì vậy chỉ cần quét bàn cờ một lần trong O(N²) và gom ô theo khoá là có toàn bộ các "đường tấn công". Mỗi cặp ô tấn công nhau chỉ nằm trên đúng một đường, nên không sinh mệnh đề trùng lặp. Test `test_attack_lines_contain_exactly_the_attacking_pairs` so khớp kết quả này với định nghĩa theo luật cờ.

**Chuyển sang CNF.** Với một đường có các biến x₁, …, xₖ:

| Ràng buộc | Công thức | Dạng CNF |
|---|---|---|
| Ít nhất một | x₁ ∨ … ∨ xₖ | 1 mệnh đề, giữ nguyên |
| Nhiều nhất một | với mọi i < j: ¬(xᵢ ∧ xⱼ) | theo De Morgan: (¬xᵢ ∨ ¬xⱼ), tổng C(k,2) mệnh đề |
| Đúng một | Ít nhất một ∧ Nhiều nhất một | ghép hai loại trên |

**Số mệnh đề** là đại lượng Θ(N³):

```
2N             ít nhất một, trên hàng và cột
2N·C(N,2)      nhiều nhất một, trên hàng và cột
2·C(N,2) + 4·C(N,3)   nhiều nhất một, trên hai hướng chéo
```

Với N = 8, công thức cho 744 mệnh đề, khớp chính xác với số đo trong chương trình.

**Mã hoá gọn hơn: sequential counter (Sinz).** Mã hoá theo cặp tốn C(k,2) mệnh đề trên mỗi đường. Sequential counter thêm k − 1 biến phụ sᵢ, nghĩa là "có quân hậu trong x₁…xᵢ", chỉ cần 3k − 4 mệnh đề, với ý nghĩa: quân hậu làm bật bộ đếm, bộ đếm đã bật thì giữ nguyên, và không quân hậu nào được đứng sau bộ đếm đã bật. Tổng số mệnh đề giảm xuống Θ(N²). Biến 1…N² vẫn là các ô như đề yêu cầu, biến phụ được đánh số sau đó, và đường ngắn từ 5 ô trở xuống vẫn dùng dạng theo cặp vì khi đó nó nhỏ hơn. Test kiểm tra cách mã hoá này cho đúng số lời giải đã biết (ví dụ 92 lời giải ở N = 8).

### Yêu cầu 2: Thí nghiệm với Glucose3

Mã hoá theo cặp. Mỗi N chạy 3 lần, lấy trung vị thời gian. Mọi lời giải đều qua `Placement.is_solution`, bộ kiểm tra không dùng CNF.

| N | Biến | Mệnh đề | Mã hoá (ms) | Nạp (ms) | Giải (ms) | Tổng (ms) | Conflicts |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 4 | 16 | 84 | 0,04 | 0,04 | 0,01 | 0,09 | 2 |
| 8 | 64 | 744 | 0,12 | 0,21 | 0,05 | 0,38 | 20 |
| 12 | 144 | 2.620 | 0,33 | 0,65 | 0,15 | 1,13 | 42 |
| 20 | 400 | 12.580 | 1,36 | 2,97 | 13,06 | 17,64 | 1.393 |
| 25 | 625 | 24.850 | 2,76 | 5,87 | 1,33 | 10,31 | 186 |
| 50 | 2.500 | 203.450 | 26,92 | 53,45 | 10,48 | 90,85 | 600 |
| 100 | 10.000 | 1.646.900 | 521,04 | 481,39 | 15,36 | 1.016,31 | 320 |
| 120 | 14.400 | 2.851.480 | 1.020,43 | 899,35 | 25,62 | 1.929,39 | 345 |

Bảng đầy đủ 18 giá trị N nằm ở [Task 1/results/sat_experiment.csv](Task%201/results/sat_experiment.csv).

**Nhận xét.**

- Số mệnh đề thực đo khớp công thức ở mọi N.
- Khi N lớn, thời gian chủ yếu nằm ở bước mã hoá và nạp mệnh đề, còn bước giải chỉ chiếm phần nhỏ: ở N = 120, giải chỉ mất 26 ms trên tổng 1.929 ms.
- Thời gian giải không tăng đều theo N: N = 20 (13,06 ms) giải chậm hơn N = 25, 30, 40, 50 và 60. Lý do có thể là độ khó phụ thuộc vào đường đi của bộ giải CDCL chứ không chỉ vào kích thước, thể hiện qua số conflicts cao hơn hẳn ở N = 20.

#### So sánh hai cách mã hoá

| N | Mệnh đề (theo cặp) | Mệnh đề (sequential) | Giảm | Tổng ms (theo cặp) | Tổng ms (sequential) |
|---:|---:|---:|---:|---:|---:|
| 8 | 744 | 580 | 1,3 lần | 0,41 | 0,44 |
| 16 | 6.352 | 2.708 | 2,3 lần | 4,53 | 1,68 |
| 32 | 52.640 | 11.572 | 4,5 lần | **22,60** | **141,91** |
| 64 | 428.864 | 47.732 | 9,0 lần | 185,99 | 35,07 |
| 100 | 1.646.900 | 117.788 | 14,0 lần | 927,74 | 134,73 |
| 120 | 2.851.480 | 170.148 | 16,8 lần | 1.849,41 | 169,17 |
| 200 | 13.253.800 (không chạy) | 475.588 | 27,9 lần | – | 620,72 |
| 300 | 44.820.700 (không chạy) | 1.073.388 | 41,8 lần | – | 1.463,34 |

**Nhận xét.** Sequential counter giúp chạy được bàn lớn mà mã hoá theo cặp không kham nổi về bộ nhớ, và nhanh hơn khoảng 11 lần ở N = 120. Tuy nhiên **nó không phải lúc nào cũng nhanh hơn**: ở N = 32 nó chậm hơn hẳn (142 ms so với 23 ms) vì bộ giải gặp 1.733 conflicts so với 292. Với N nhỏ, mã hoá theo cặp đơn giản và đủ tốt, nên đó vẫn là mặc định. Dữ liệu ở [Task 1/results/encoding_experiment.csv](Task%201/results/encoding_experiment.csv).

### Yêu cầu 3: Min-Conflicts và heuristic chọn biến

**Mô hình CSP.** Mỗi hàng là một biến, giá trị là cột đặt quân hậu của hàng đó. Mỗi hàng luôn có đúng một quân hậu, nên chỉ còn phải sửa xung đột cột và chéo.

**Tối ưu cài đặt.** Thuật toán không đổi, chỉ cách tính nhanh hơn:

1. **Cập nhật tăng dần.** Một nước đi chỉ thay đổi xung đột của các quân trên 6 đường, nên `ConflictTracker` cập nhật tăng dần thay vì đếm lại cả bàn. So với bản đầu tiên, mỗi bước nhanh hơn khoảng 3 lần ở N lớn.
2. **Chọn giá trị bằng hàm C thay vì vòng lặp Python.**
   - Ba bộ đếm cột và chéo được cộng bằng `map`.
   - Các giá trị hoà được tìm bằng `list.count` và `list.index`.
   - Khi phá hoà, không cần dựng danh sách các phần tử hoà. `rng.choice(ds)` thực chất là `ds[rng.randrange(len(ds))]`, nên chỉ cần đếm số phần tử hoà, bốc một chỉ số rồi nhảy tới đúng phần tử đó.

   Test so với cài đặt dùng vòng lặp đơn giản cho thấy bản chuẩn chạy giống hệt từng bước (cùng lựa chọn, cùng số ngẫu nhiên đã dùng).
3. **Nhóm các hàng theo số xung đột.** `ConflictTracker` giữ `buckets[c]` là các hàng có đúng c xung đột, cập nhật cùng lúc với số xung đột. Mỗi lần cập nhật chỉ tốn O(1): thêm vào cuối nhóm mới, và rời nhóm cũ bằng cách đổi chỗ với phần tử cuối. Heuristic lấy nhóm cao nhất còn hàng không bị cấm rồi bốc đều ngẫu nhiên trong nhóm, thay vì duyệt mọi hàng đang xung đột.

   Tập hàng có thể được chọn vẫn đúng như trước (test so với vòng lặp cũ trên nhiều thế cờ ngẫu nhiên), nhưng thứ tự bốc khác nên từng lần chạy cụ thể của heuristic khác lần đo trước.

Đo trong cùng điều kiện ở N = 4096, mỗi bước của bản chuẩn giảm từ 268 xuống khoảng 196 µs, của bản đề xuất từ 345 xuống khoảng 196 µs: giờ hai bản tốn như nhau cho mỗi bước.

**Heuristic đề xuất: `most-conflicted + tabu`.**

1. Chọn biến có **nhiều xung đột nhất**: một lần sửa gỡ được nhiều cặp tấn công nhất khi bàn còn nhiều xung đột.
2. **Cấm chọn lại** biến vừa sửa trong `tenure = 8` bước. Gần lời giải, phần lớn biến chỉ còn đúng một xung đột nên bằng điểm nhau, và chọn tham lam thuần tuý dễ quay lại vài hàng cũ. Danh sách cấm buộc tìm kiếm chuyển sang hàng khác.
3. Nếu mọi biến xung đột đều đang bị cấm thì bỏ qua lệnh cấm ở lần đó.

Giá trị `tenure` được chọn trên seed 1000 trở đi, tách khỏi seed 0–99 dùng để đánh giá, để tránh chọn tham số theo chính dữ liệu đánh giá.

**Thiết kế thí nghiệm.** Thí nghiệm so sánh theo cặp: với mỗi N và seed, mọi chiến lược xuất phát từ **cùng một phép gán ban đầu**, nên khác biệt đến từ chiến lược chứ không từ điểm xuất phát may mắn. Chỉ bước chọn biến khác nhau, bước chọn giá trị giữ nguyên. Mỗi N chạy 100 seed, giới hạn `max(2000, 100·N)` bước, không restart.

| N | Chiến lược | Thành công | Bước (TB) | Bước (trung vị) | Độ lệch chuẩn | ms (TB) | Ít bước hơn chuẩn |
|---:|---|---:|---:|---:|---:|---:|---:|
| 8 | standard | 95% | 157,8 | 43,0 | 427,5 | 0,34 | – |
| 8 | **đề xuất** | 99% | 45,2 | 18,0 | 197,9 | 0,17 | 71% |
| 16 | standard | 99% | 109,7 | 64,5 | 206,9 | 0,35 | – |
| 16 | **đề xuất** | 98% | 84,8 | 36,0 | 275,9 | 0,37 | 71% |
| 64 | standard | 100% | 114,6 | 108,5 | 36,5 | 0,73 | – |
| 64 | **đề xuất** | 100% | 71,0 | 67,5 | 19,3 | 0,58 | 87% |
| 256 | standard | 100% | 249,1 | 243,5 | 36,6 | 4,50 | – |
| 256 | **đề xuất** | 100% | 175,6 | 174,5 | 19,7 | 3,57 | 96% |
| 1024 | standard | 100% | 719,0 | 712,5 | 38,4 | 52,33 | – |
| 1024 | **đề xuất** | 100% | 551,2 | 549,5 | 19,6 | 41,53 | 100% |
| 4096 | standard | 100% | 2.602,6 | 2.598,0 | 47,7 | 702,77 | – |
| 4096 | **đề xuất** | 100% | 2.038,4 | 2.037,5 | 29,0 | 554,58 | 100% |

Bảng đầy đủ (10 giá trị N, thêm cả biến thể `most-conflicted` không tabu) nằm ở [Task 1/results/min_conflicts_experiment.csv](Task%201/results/min_conflicts_experiment.csv).

**Nhận xét.**

- Từ N = 32 trở lên, heuristic giảm khoảng 22–38% số bước trung bình so với bản chuẩn, độ lệch chuẩn cũng nhỏ hơn. Từ N = 512, heuristic thắng cả 100/100 cặp.
- **Ít bước hơn giờ cũng là ít thời gian hơn.** Trước khi nhóm các hàng theo số xung đột, heuristic phải duyệt mọi biến xung đột ở mỗi bước, nên ở N = 4096 giảm 22% số bước mà thời gian chỉ giảm khoảng 3%. Giờ mỗi bước tốn ngang bản chuẩn, nên từ N = 64 trở lên thời gian giảm khoảng 20% (khoảng 0,79 lần), tương ứng với số bước. Ở N = 16 chi phí cố định vẫn lớn hơn phần lợi.
- Ở N nhỏ, trung vị số bước luôn tốt hơn nhưng **tỉ lệ thành công chênh lệch trong mức nhiễu**. Với 100 lần chạy, N = 8 cho 99% so với 95% ở lần đo này. Hai lần đo trước, với luồng số ngẫu nhiên khác, cho 97% so với 95% và 93% so với 96%. Không nên kết luận heuristic làm tăng tỉ lệ thành công ở bàn nhỏ. Số bước trung bình ở N = 8 cũng vì thế mà dao động mạnh, do mỗi lần thất bại đóng góp trọn 2.000 bước.

**Vì sao bàn nhỏ thất bại.** Mình đã kiểm tra trực tiếp với 400 lần chạy ở mỗi N = 6, 8, 10, 12, 16: khoảng một nửa số lần thất bại kết thúc ở cực tiểu địa phương chặt, tức là mọi biến đang xung đột đều đã ở giá trị tốt nhất duy nhất của nó. Phần còn lại chưa thoát được sau 2.000 bước, nhiều khả năng do lặp trên vùng phẳng, nhưng mình chưa kiểm chứng điểm này. Tình trạng thất bại xảy ra với **cả bản chuẩn lẫn bản đề xuất**. Riêng cực tiểu chặt thì không cách chọn biến nào thoát được, vì biến nào được chọn cũng giữ nguyên giá trị. Vì thế lệnh `minconflicts` dùng thêm random restart để trả về lời giải, còn thí nghiệm không dùng restart để giữ nguyên hiện tượng này trong số liệu.

### Giả định và giới hạn của Task 1

- Đề nói Min-Conflicts được giới thiệu ở Lecture 08 nhưng mình không có slide. Mình cài theo phiên bản chuẩn trong giáo trình AIMA: chọn ngẫu nhiên một biến đang xung đột, chọn giá trị ít xung đột nhất và phá hoà ngẫu nhiên. Hãy đối chiếu với slide của lớp.
- Đề không yêu cầu giao diện cho task này nên không có.
- Về máy đo, xem mục "Lưu ý về số liệu" ở cuối tệp.

---

## Task 2: Tank Battle (Adversarial Search)

### Cách chạy

Chạy trong thư mục `Task 2`:

```bash
python main.py                                  # mở menu chọn người chơi, bản đồ, thời gian
python main.py --list                           # liệt kê tác nhân và bản đồ
python main.py --p1 "Heuristic Alpha-Beta" --p2 plugins/example_function_agent.py --map Bunkers
python main.py --headless --p1 "Heuristic A-B + optimizations" --p2 path/to/group_x.py --games 8
python run_experiments.py                       # toàn bộ thí nghiệm, khoảng 20 phút hoặc lâu hơn
python run_experiments.py --only strength       # hoặc: depth, time, tournament, ablation, depth_value
python run_tuning.py --iterations 60            # tinh chỉnh trọng số hàm đánh giá
python -m unittest discover -s tests            # kiểm thử
```

**Phím trong game:** `P` tạm dừng, `N` đi từng bước, `←`/`→` xem lại các chu kỳ đã qua (khi tạm dừng hoặc hết ván), `+`/`-` tốc độ, `L` đường đạn, `V` kế hoạch của AI, `H` bản đồ công sức, `R` chơi lại, `Enter` ván tiếp theo, `Esc` về menu. Người chơi dùng `WASD` hoặc mũi tên để di chuyển, `Space` hoặc `Enter` để bắn, `X` hoặc `RShift` để đứng yên.

| Tệp | Vai trò |
|---|---|
| [tank_battle/model.py](Task%202/tank_battle/model.py) | `Action`, `Tank`, `Base`, `Bullet`, `Wall`, `GameState` |
| [tank_battle/rules.py](Task%202/tank_battle/rules.py) | `GameRules`: hàm chuyển trạng thái, kiểm tra kết thúc, utility |
| [tank_battle/maps.py](Task%202/tank_battle/maps.py) | `GameMap`, 7 bản đồ tự thiết kế, `random_map` |
| [tank_battle/evaluation.py](Task%202/tank_battle/evaluation.py) | `RaceEvaluator`, `FiringEffortMap`, và `HeuristicEvaluator` của bản đầu để so sánh |
| [tank_battle/search.py](Task%202/tank_battle/search.py) | `AdversarialSearch`, `SearchConfig` |
| [tank_battle/agents.py](Task%202/tank_battle/agents.py) | `Agent` (giao diện chung), `SearchAgent`, `RandomAgent` |
| [tank_battle/plugins.py](Task%202/tank_battle/plugins.py) | `PluginLoader`, `AgentCatalog`: nạp thuật toán nhóm khác |
| [tank_battle/session.py](Task%202/tank_battle/session.py) | `SafeAgentRunner`, `GameSession`, `HeadlessMatch` |
| [tank_battle/experiments.py](Task%202/tank_battle/experiments.py) | Các thí nghiệm |
| [tank_battle/gui/](Task%202/tank_battle/gui/) | Giao diện PyGame |

Bản đồ là thiết kế riêng cho bài này. Đồ hoạ là pixel-art vẽ hoàn toàn bằng code trong [tank_battle/gui/retro.py](Task%202/tank_battle/gui/retro.py), theo phong cách của Battle City (khung xám quanh sân đen, tường gạch, đại bàng, tank hai bánh xích, vụ nổ nhiều khung hình, chữ pixel 5×7). Không dùng ảnh hay sprite của game gốc. Phong cách được dựng theo hiểu biết về game gốc, vì bài viết tham khảo trên Hardcore Gaming 101 đang bảo trì lúc làm nên chưa đọc được.

### Yêu cầu 1: Mô hình hoá thành trò chơi tổng bằng không

| Thành phần | Định nghĩa trong bài |
|---|---|
| **Trạng thái s** | Vị trí, hướng, HP của 2 tank; HP của 2 căn cứ; HP từng tường; vị trí và hướng từng viên đạn; số chu kỳ đã qua. Thông tin đầy đủ, tất định. |
| **Người chơi** | MAX là người đang ra quyết định, MIN là đối thủ. |
| **Hành động** | 6 hành động luôn hợp lệ: `MOVE_UP`, `MOVE_DOWN`, `MOVE_LEFT`, `MOVE_RIGHT`, `FIRE`, `STAY`. |
| **Chuyển trạng thái** | `RESULT(s, a₁, a₂)` theo 4 pha ở dưới. |
| **Trạng thái cuối** | Một tank hoặc một căn cứ hết HP, hoặc đạt giới hạn chu kỳ. |
| **Utility** | Thắng +1, thua −1, hoà 0, nên U(s, P₁) + U(s, P₂) = 0. Người thắng là bên còn nhiều tài sản hoạt động hơn trong số tank và căn cứ. |

**Một chu kỳ** ([rules.py](Task%202/tank_battle/rules.py)):

1. Hai tank cùng quay và di chuyển.
2. Tank đi vào ô có đạn đang bay thì bị trúng đạn.
3. `FIRE` đặt đạn lên ô của tank, cùng hướng với tank.
4. Lặp 3 lần: mọi viên đạn tiến một ô rồi **kiểm tra va chạm ngay**. Đạn dừng khi trúng vật thể. Game dừng ngay ở bước con mà một tank hoặc căn cứ bị phá.

**Đưa lượt đồng thời về cây trò chơi.** Hai bên chọn hành động trên cùng một trạng thái. Trong cây tìm kiếm, mỗi chu kỳ thành 2 tầng: MAX chọn a₁, MIN chọn a₂ khi đã biết a₁, rồi mới áp dụng `RESULT`. Giả định này thận trọng vì cho đối thủ biết trước nước đi, đổi lại trò chơi trở thành cây tổng bằng không thông thường. Độ sâu d chu kỳ tương ứng 2d tầng, và cây chỉ bị cắt ở chu kỳ hoàn chỉnh. Mình đã thử thay bằng ma trận đối đầu ở gốc để phản ánh đúng việc chọn đồng thời, nhưng nó không mạnh hơn (46–48% khi đấu với cách hiện tại) nên không dùng.

**Áp dụng các thuật toán.**

| Thuật toán | Giá trị tại điểm cắt | Ý nghĩa |
|---|---|---|
| Minimax | 0 | Duyệt toàn bộ đến độ sâu giới hạn, chỉ biết utility ở trạng thái cuối |
| Alpha-Beta | 0 | Như trên, cắt các nhánh không ảnh hưởng kết quả |
| Heuristic Minimax | `EVAL(s)` | Duyệt toàn bộ, ước lượng trạng thái chưa kết thúc |
| Heuristic Alpha-Beta | `EVAL(s)` | Ước lượng và cắt nhánh |

Hệ số nhánh là 36 mỗi chu kỳ, còn một ván giữa các tác nhân có heuristic kéo dài trung bình khoảng 20 chu kỳ (40 tầng) theo thí nghiệm 3, nên không thể duyệt đến trạng thái cuối thật. Cho giá trị 0 tại điểm cắt tương đương với việc tuyên bố hoà khi đạt giới hạn độ sâu, tức là chạy Minimax thuần trên trò chơi bị cắt ngắn. Đây là cách đo được bản không heuristic một cách trung thực.

**Hàm đánh giá `RaceEvaluator`.** Ván đấu được quyết định bởi bên nào phá được mục tiêu trước, nên hàm đánh giá ước lượng **thời gian hoàn thành** của mỗi bên: số chu kỳ để có đường bắn cộng số phát còn cần, lấy mục tiêu tốt hơn trong hai mục tiêu tank và căn cứ, tính cả đạn đang bay.

Vì đạn bay không giới hạn tầm, tank không cần đi đến sát mục tiêu mà chỉ cần thẳng hàng với nó. `FiringEffortMap` tính cho mỗi ô công sức để bắn được: xuất phát từ mọi ô thẳng hàng với mục tiêu (tốn số phát phá tường chắn), rồi Dijkstra cộng thêm đường đi.

**Hàm đánh giá được tính lười.** Đây là phần tốn nhất của tìm kiếm: trước khi tối ưu, nó chiếm 59% thời gian. Mục tiêu "tank địch" đổi vị trí liên tục nên bộ nhớ đệm ít khi trúng. Hai thay đổi, không làm đổi bất kỳ giá trị nào:

1. **Dijkstra dừng giữa chừng.** Mỗi lần đánh giá chỉ cần chi phí tại đúng ô tank đang đứng. Vì vậy Dijkstra dừng ngay khi ô đó được lấy ra khỏi hàng đợi (lúc đó chi phí đã chắc chắn), và lần hỏi sau với cùng mục tiêu và cùng tường sẽ chạy tiếp từ chỗ dừng. Dijkstra lấy các ô ra theo thứ tự chi phí tăng dần dù có dừng hay không, nên kết quả giống hệt một lần chạy trọn vẹn.
2. **Cận cho mục tiêu tank.** Hàm đánh giá lấy mục tiêu nào xong sớm hơn giữa căn cứ và tank. Chi phí không bao giờ âm, nên khi công sức tới tank chắc chắn vượt mốc `T_căn_cứ − HP_tank − 6,43`, tank không thể là lựa chọn tốt hơn và Dijkstra dừng ở đó. Nếu mốc này âm thì bỏ hẳn bước tìm đường.

Test so với cách tính cũ (Dijkstra trọn vẹn cho cả bản đồ) trên nhiều thế cờ ngẫu nhiên cho ra giá trị đánh giá bằng nhau tuyệt đối. Bài đo 3 ván thật ở độ sâu 4 cho cùng mọi nước đi và cùng 259.657 nút, thời gian giảm từ 5,73 xuống 2,53 giây.

| Thành phần | Trọng số | Lý do |
|---|---:|---|
| HP tank | 10 | Mất tank là thua |
| HP căn cứ | 8,75 | Mất căn cứ là thua |
| Đạn đang bay tới tank | 4,19 | Thiệt hại sắp xảy ra, nhưng tank có thể né |
| Đạn đang bay tới căn cứ | 18,76 | Căn cứ không né được |
| Dẫn trước về thời gian hoàn thành | 1,13/chu kỳ | Ai xong trước thì thắng |
| Sắp hoàn thành | 60 × 1/T | Bên sắp xong quan trọng hơn lợi thế còn xa |
| Phụ trội khi săn tank | +6,43 chu kỳ | Tank né được nên khó hơn con số thuần tuý |
| Đã ngắm đúng hướng | −0,45 chu kỳ | Bắn được ngay |
| Chủ động | 1,88/chu kỳ của bên đang tìm kiếm | Xem mục sửa lỗi kẹt ở dưới |

Thành phần "chủ động" là phần duy nhất không phản đối xứng, nên hàm đánh giá khi tìm kiếm không còn tổng bằng không tuyệt đối. Utility thật ở trạng thái cuối vẫn tổng bằng không, và trong mỗi lần tìm kiếm chỉ có một hàm giá trị duy nhất nên Minimax vẫn đúng. Test kiểm tra phần còn lại phản đối xứng khi đặt `aggression = 0`.

**Một nhận xét đáng đưa vào báo cáo.** Vì tank di chuyển trước đạn, một tank còn chỗ né thì không bao giờ bị "giết chắc chắn" trong cây tìm kiếm, còn căn cứ thì không né được. Do đó thuật toán có xu hướng tấn công căn cứ, và tinh chỉnh tự động cũng đưa trọng số đạn bay tới căn cứ lên cao hơn hẳn đạn bay tới tank.

### Yêu cầu 2: Điều khiển và thí nghiệm

**Bộ điều khiển dùng khi chơi thật** là `Heuristic A-B + optimizations`, với các tối ưu:

- **Iterative deepening theo thời gian:** tăng dần độ sâu đến khi hết giờ, bảo đảm chạy thời gian thực. Nếu bị ngắt giữa chừng thì vẫn dùng được kết quả dở dang, vì nước tốt nhất trước đó luôn được duyệt đầu tiên.
- **Move ordering:** nước nhớ được, nước phát bắn trúng, killer move, history heuristic.
- **Transposition table và nhớ nước trả lời của MIN.**
- **Bỏ hành động trùng:** nước di chuyển bị chặn khi đã quay đúng hướng thì giống hệt `STAY`.
- **Phạt lặp trạng thái:** xem mục dưới.
- **Hàm đánh giá tính lười** (xem phần hàm đánh giá ở trên), cùng vài chỗ nhỏ trong `step` và `_order`: giữ lại đối tượng tank không đổi, sắp xếp không cần lambda.

Đóng góp của từng tối ưu được đo riêng ở thí nghiệm 5. Cache giá trị đánh giá cũng đã được thử nhưng gần như không có tác dụng nên không giữ.

#### Lỗi đã phát hiện và sửa: tank đứng dao động

Bản đầu có một lỗi mà giải đấu trên bản đồ đối xứng không phát hiện được. Từ các khai cuộc ngẫu nhiên, **hai tank có thể đi lên đi xuống suốt ván mà không bắn phát nào** (66/200 ván chạm giới hạn chu kỳ trong một phép đo trên bản đầu của hàm đánh giá mới). Nguyên nhân:

1. Bức tường chắn cho cả hai bên: phá nó thì cả hai cùng có lợi, nên hiệu số không đổi và tìm kiếm thấy không có lý do để bắn. Sửa bằng thành phần **chủ động**.
2. Bắn tường ở xa thì đạn bay nhiều chu kỳ mới tới, vượt quá độ sâu tìm kiếm, nên trông như vô ích. Sửa bằng cách **tính trước công của viên đạn đang bay** tới bức tường chắn căn cứ địch.
3. Quay lại đúng vị trí cũ không bị phạt. Sửa bằng **phạt lặp theo tiến độ của chính mình**, không xét vị trí đối thủ, nên vẫn phát hiện được dao động khi đối thủ đang di chuyển.

#### Tinh chỉnh trọng số: một bài học về học thuộc

Lần tinh chỉnh đầu dùng 5 bản đồ cố định và đạt điểm cao trên chúng, nhưng khi kiểm tra trên 2 bản đồ chưa từng thấy thì **thua cả bản cũ ở độ sâu 2, 3 và ở 50 ms (30–40%)**, chỉ thắng ở độ sâu 4. Vì vậy [run_tuning.py](Task%202/run_tuning.py) hiện tinh chỉnh trên 60 bản đồ ngẫu nhiên đối xứng, và kết quả báo cáo dùng các bản đồ ngẫu nhiên khác hẳn (seed từ 1000). Trọng số cuối chỉ được nhận sau khi thắng trọng số trước đó trên dữ liệu kiểm tra này (55,2% đấu trực tiếp).

#### Điều kiện công bằng của thí nghiệm

Bốn cấu hình dùng chung một mã nguồn, cùng 10 tình huống (7 khai cuộc, 2 trung cuộc, 1 tàn cuộc), cùng thứ tự hành động, không dùng các tối ưu trên. Nếu kết quả của cặp có cắt nhánh và không cắt nhánh khác nhau về giá trị hoặc hành động, chương trình sẽ báo lỗi, và lỗi này đã không xảy ra ở lần chạy nào.

#### Thí nghiệm 1: Cùng độ sâu (trung bình trên 10 tình huống)

| Độ sâu (chu kỳ / tầng) | Cấu hình | Thời gian (ms) | Trạng thái đã duyệt | Hệ số nhánh hiệu dụng |
|---|---|---:|---:|---:|
| 2 / 4 | Minimax | 4,29 | 1.555 | 6,28 |
| 2 / 4 | Alpha-Beta | 0,23 | 130 | 3,38 |
| 2 / 4 | Heuristic Minimax | 15,60 | 1.555 | 6,28 |
| 2 / 4 | Heuristic Alpha-Beta | 3,54 | 225 | 3,84 |
| 3 / 6 | Minimax | 148,58 | 55.655 | 6,18 |
| 3 / 6 | Alpha-Beta | 1,35 | 812 | 3,05 |
| 3 / 6 | Heuristic Minimax | 356,40 | 55.655 | 6,18 |
| 3 / 6 | Heuristic Alpha-Beta | 16,56 | 2.095 | 3,55 |
| 4 / 8 | Minimax | 5.466,32 | 1.994.060 | 6,13 |
| 4 / 8 | Alpha-Beta | 9,54 | 5.017 | 2,90 |
| 4 / 8 | Heuristic Minimax | 12.067,57 | 1.994.060 | 6,13 |
| 4 / 8 | Heuristic Alpha-Beta | 103,65 | 18.068 | 3,39 |
| 5 / 10 | Minimax và Heuristic Minimax | bỏ qua | cây đầy đủ 72,6 triệu | – |
| 5 / 10 | Alpha-Beta | 62,35 | 32.856 | 2,82 |
| 5 / 10 | Heuristic Alpha-Beta | 769,39 | 155.357 | 3,28 |
| 6 / 12 | Alpha-Beta | 428,86 | 219.595 | 2,77 |
| 6 / 12 | Heuristic Alpha-Beta | 6.683,11 | 1.377.800 | 3,21 |

Số trạng thái giống hệt lần đo trước khi tối ưu hàm đánh giá. Chỉ thời gian của các cấu hình có heuristic giảm xuống. Dữ liệu từng tình huống nằm ở [Task 2/results/fixed_depth.csv](Task%202/results/fixed_depth.csv).

#### Thí nghiệm 2: Cùng thời gian mỗi quyết định

| Thời gian | Cấu hình | Độ sâu trung vị (chu kỳ) | Độ sâu TB | Độ sâu tối đa | Trạng thái/ms |
|---:|---|---:|---:|---:|---:|
| 200 ms | Minimax | 3 | 3,00 | 3 | 365 |
| 200 ms | Alpha-Beta | 5 | 5,00 | 5 | 485 |
| 200 ms | Heuristic Minimax | 2 | 2,00 | 2 | 148 |
| 200 ms | Heuristic Alpha-Beta | 4 | 4,00 | 4 | 191 |
| 200 ms | Heuristic A-B + tối ưu | 5 | 7,20 | 23 | 113 |
| 1000 ms | Minimax | 3 | 3,00 | 3 | 357 |
| 1000 ms | Alpha-Beta | 6 | 5,90 | 6 | 484 |
| 1000 ms | Heuristic Minimax | 3 | 3,00 | 3 | 158 |
| 1000 ms | Heuristic Alpha-Beta | 5 | 4,87 | 5 | 203 |
| 1000 ms | Heuristic A-B + tối ưu | 7 | 10,20 | 40 | 113 |

Độ sâu ở đây là độ sâu đã duyệt xong hoàn toàn. Trung bình của bản tối ưu bị kéo lên bởi các thế tàn cuộc rất ít lựa chọn (chạm giới hạn 40), nên **nên đọc theo trung vị**. Dữ liệu đầy đủ (5 mức thời gian) nằm ở [Task 2/results/fixed_time.csv](Task%202/results/fixed_time.csv).

Nhờ hàm đánh giá tính lười, bản tối ưu duyệt 113 trạng thái/ms thay vì 61–68 như trước, và ở 1000 ms đạt độ sâu trung vị 7 thay vì 6. Số trạng thái/ms của nó vẫn thấp hơn Heuristic Alpha-Beta vì mỗi nút làm thêm việc (sắp thứ tự, tra bảng chuyển vị), nhưng nó cần ít nút hơn nhiều để đạt cùng độ sâu (thí nghiệm 5).

#### Thí nghiệm 3: Đấu vòng tròn từ thế xuất phát

Mỗi cặp đấu trên 4 bản đồ, đổi bên, 2 seed, tổng 16 ván, tối đa 120 chu kỳ mỗi ván.

| Cùng độ sâu 2 chu kỳ | Thắng | Hoà | Thua | Điểm |
|---|---:|---:|---:|---:|
| Heuristic Minimax | 56 | 0 | 8 | 87,5% |
| Heuristic Alpha-Beta | 56 | 0 | 8 | 87,5% |
| Minimax | 0 | 32 | 32 | 25,0% |
| Alpha-Beta | 0 | 32 | 32 | 25,0% |
| Random | 0 | 32 | 32 | 25,0% |

| Cùng thời gian 20 ms | Thắng | Hoà | Thua | Điểm |
|---|---:|---:|---:|---:|
| Heuristic Minimax | 41 | 21 | 2 | 80,5% |
| Heuristic A-B + tối ưu | 35 | 24 | 5 | 73,4% |
| Heuristic Alpha-Beta | 34 | 23 | 7 | 71,1% |
| Minimax | 0 | 16 | 48 | 12,5% |
| Alpha-Beta | 0 | 16 | 48 | 12,5% |

#### Thí nghiệm 4: Bản hiện tại so với bản đầu

Thí nghiệm này mới so bộ điều khiển hiện tại với bản đầu (hàm đánh giá cũ, không phạt lặp, dùng chung các tối ưu tìm kiếm mới), từ khai cuộc ngẫu nhiên, đấu cả hai bên, 240 ván mỗi cặp, trên **60 bản đồ ngẫu nhiên chưa từng dùng để tinh chỉnh**. Đối thủ gồm 4 kiểu trong [plugins/sparring_partners.py](Task%202/plugins/sparring_partners.py).

| Độ sâu 3 chu kỳ | Bản hiện tại | Bản đầu | Số ván kẹt (hiện tại / bản đầu) |
|---|---:|---:|---:|
| gặp Rusher (lao vào căn cứ) | 65,6% | 64,2% | 0 / 0 |
| gặp Dodger (tấn công và né đạn) | 66,3% | 64,8% | 0 / 0 |
| gặp Hunter (săn tank) | 88,8% | 86,7% | 0 / 1 |
| gặp Turret (đứng yên, bắn khi thẳng hàng) | 97,5% | 92,3% | 2 / 30 |

| Đấu trực tiếp với bản đầu | Thắng | Hoà | Thua | Điểm |
|---|---:|---:|---:|---:|
| Độ sâu 2 | 109 | 52 | 79 | 56,3% |
| Độ sâu 3 | 100 | 54 | 86 | 52,9% |
| Độ sâu 4 | 87 | 67 | 86 | 50,2% |
| 50 ms mỗi quyết định | 92 | 65 | 83 | 51,9% |
| Độ sâu 3, trên 7 bản đồ có sẵn | 69 | 31 | 40 | 60,4% |

Dữ liệu ở [Task 2/results/](Task%202/results/), các tệp `strength_*.csv`. Các dòng theo độ sâu không phụ thuộc tốc độ, nên vẫn đúng sau khi tối ưu. Dòng 50 ms được đo lại sau khi tối ưu.

#### Thí nghiệm 5: Đóng góp của từng tối ưu

Bắt đầu từ Heuristic Alpha-Beta, bật riêng từng tối ưu, rồi bật cả ba, trên cùng 10 tình huống và cùng độ sâu. Thời gian là tổng của 10 tình huống, mỗi tình huống lấy trung vị 3 lần chạy. Ở **mọi dòng, giá trị tìm được ở gốc đều giống hệt** Heuristic Alpha-Beta thường: các tối ưu này chỉ đổi khối lượng công việc, không đổi kết quả.

| Độ sâu | Cấu hình | Thời gian (ms) | Trạng thái | Trạng thái so với gốc | Thời gian so với gốc |
|---|---|---:|---:|---:|---:|
| 4 | Heuristic Alpha-Beta | 861 | 180.684 | 1,00 | 1,00 |
| 4 | + bỏ hành động trùng | 937 | 138.643 | 0,77 | 1,09 |
| 4 | + sắp thứ tự nước đi | 699 | 91.707 | 0,51 | 0,81 |
| 4 | + bảng chuyển vị | 610 | 74.145 | 0,41 | 0,71 |
| 4 | **cả ba** | **420** | **37.632** | **0,21** | **0,49** |
| 5 | Heuristic Alpha-Beta | 7.619 | 1.553.572 | 1,00 | 1,00 |
| 5 | + bỏ hành động trùng | 5.738 | 1.017.901 | 0,66 | 0,75 |
| 5 | + sắp thứ tự nước đi | 4.396 | 673.896 | 0,43 | 0,58 |
| 5 | + bảng chuyển vị | 2.271 | 310.749 | 0,20 | 0,30 |
| 5 | **cả ba** | **1.232** | **121.064** | **0,08** | **0,16** |

Dữ liệu ở [Task 2/results/ablation.csv](Task%202/results/ablation.csv), chạy lại bằng `python run_experiments.py --only ablation`.

#### Thí nghiệm 6: Tìm sâu hơn có thắng nhiều hơn không?

Các thí nghiệm 1, 2 và 5 cho thấy các tối ưu giúp tìm sâu hơn trong cùng thời gian. Thí nghiệm này kiểm tra xem độ sâu đó có đổi thành ván thắng không. Cùng 120 khai cuộc trên 60 bản đồ ngẫu nhiên chưa dùng để tinh chỉnh như thí nghiệm 4, mỗi khai cuộc đấu cả hai bên, nên mỗi dòng có 240 ván và sai số chuẩn của điểm khoảng 3 điểm phần trăm.

| Người chơi | Đối thủ | Thắng | Hoà | Thua | Điểm |
|---|---|---:|---:|---:|---:|
| Bản tối ưu, độ sâu 2 | Bản tối ưu, độ sâu 1 | 152 | 48 | 40 | **73,3%** |
| Bản tối ưu, độ sâu 3 | Bản tối ưu, độ sâu 2 | 107 | 53 | 80 | **55,6%** |
| Bản tối ưu, độ sâu 4 | Bản tối ưu, độ sâu 3 | 90 | 64 | 86 | 50,8% |
| Bản tối ưu, độ sâu 5 | Bản tối ưu, độ sâu 4 | 86 | 75 | 79 | 51,5% |
| Bản tối ưu, độ sâu 2 | Heuristic Alpha-Beta, độ sâu 2 | 125 | 54 | 61 | **63,3%** |
| Bản tối ưu, độ sâu 3 | Heuristic Alpha-Beta, độ sâu 3 | 111 | 55 | 74 | **57,7%** |
| Heuristic Alpha-Beta, 50 ms | Heuristic Alpha-Beta, độ sâu 3 | 100 | 71 | 69 | **56,5%** |
| Bản tối ưu, 50 ms | Heuristic Alpha-Beta, 50 ms | 88 | 69 | 83 | 51,0% |
| Bản tối ưu, 50 ms | Heuristic Minimax, 50 ms | 87 | 75 | 78 | 51,9% |
| Heuristic Alpha-Beta, 50 ms | Heuristic Minimax, 50 ms | 81 | 80 | 79 | 50,4% |

Ở 50 ms, độ sâu đã duyệt xong của bản tối ưu thường là 4–5 chu kỳ, của Heuristic Alpha-Beta thường là 3 (đo riêng trên 30 ván từ 15 khai cuộc đầu tiên).

Dữ liệu ở [Task 2/results/depth_value.csv](Task%202/results/depth_value.csv), chạy lại bằng `python run_experiments.py --only depth_value`.

#### Nhận xét

1. **Cắt nhánh rất hiệu quả và an toàn.** Ở độ sâu 4 chu kỳ, Alpha-Beta giảm số trạng thái khoảng 397 lần so với Minimax, Heuristic Alpha-Beta giảm khoảng 110 lần so với Heuristic Minimax, mà giá trị và hành động ở gốc không đổi.
2. **Heuristic làm mỗi nút đắt hơn nhiều.** Tốc độ duyệt giảm từ khoảng 360–480 xuống khoảng 150–200 trạng thái/ms, dù hàm đánh giá đã được tính lười. Vì vậy với cùng thời gian, bản có heuristic duyệt nông hơn.
3. **Alpha-Beta không heuristic cắt được nhiều hơn** Heuristic Alpha-Beta. Nguyên nhân là phần lớn lá đều có giá trị 0, nên rất nhiều nhánh bị cắt, nhưng độ sâu đó **không mang lại nước đi tốt hơn**.
4. **Heuristic mới là yếu tố quyết định sức mạnh.** Tác nhân có heuristic thắng toàn bộ 16/16 ván trước tác nhân không heuristic ở cả hai giải. Minimax và Alpha-Beta không hơn Random: mọi ván giữa chúng đều hoà.
5. **Lợi ích chắc chắn nhất của bản hiện tại là hết bị kẹt** (trước Turret: 2 ván so với 30 ván trên 240). **Về sức mạnh, nó chỉ nhỉnh hơn bản đầu một chút:** 50–56% khi đấu trực tiếp trên bản đồ mới, ngang nhau khi có thời gian hoặc độ sâu lớn hơn. Gặp Rusher và Dodger, mức chênh chỉ khoảng 1–2 điểm ở độ sâu 3, và ở độ sâu 4 thì không còn hơn. Khó có thể gọi đây là bước nhảy lớn về sức mạnh.
6. **Giải đấu từ thế xuất phát không đủ để xếp hạng các bản heuristic.** Ở cùng độ sâu, Heuristic Minimax và Heuristic Alpha-Beta đưa ra cùng quyết định nên kết quả 8–0–8 chỉ phản ánh bên chơi. Ở 20 ms, mỗi bản chỉ có 64 ván, nên sai số chuẩn của điểm khoảng 5 điểm phần trăm. Lần đo này cho 80,5%, 73,4% và 71,1%, còn lần đo trước (trước khi tối ưu) cho 75,8%, 74,2% và 75,0%, tức thứ tự đổi giữa hai lần chạy: đây là nhiễu. Thí nghiệm 6, với 240 ván mỗi cặp, xác nhận ba bản này ngang nhau ở cùng thời gian (50–52%).
7. **Bảng chuyển vị là tối ưu đáng giá nhất, và các tối ưu cộng hưởng với nhau.** Ở độ sâu 5, riêng bảng chuyển vị đã giảm còn 20% số trạng thái, cả ba tối ưu còn 8%, nhanh gấp khoảng 6 lần. Lợi ích tăng theo độ sâu: ở độ sâu 4, cả ba chỉ nhanh gấp khoảng 2 lần, và riêng việc bỏ hành động trùng còn chưa bù được chi phí của nó (qua ba lần đo, thời gian dao động từ 0,89 đến 1,30 lần so với gốc, tức nằm trong mức nhiễu).
8. **Quá 3 chu kỳ, tìm sâu hơn không thắng thêm, nên các tối ưu tìm kiếm không làm tác nhân mạnh hơn ở cùng thời gian.** Từ độ sâu 1 lên 2 thắng 73%, từ 2 lên 3 còn 56%, từ 3 lên 4 và từ 4 lên 5 chỉ 51%, tức ngang nhau. Vì vậy ở 50 ms, bản tối ưu tìm sâu hơn Heuristic Alpha-Beta 1–2 chu kỳ nhưng chỉ đạt 51%. Có hai nguyên nhân hợp lý, chưa được tách riêng để kiểm chứng:
   - Hàm đánh giá đã tính sẵn "cuộc đua" về đích bằng Dijkstra, nên phần lớn những gì độ sâu lớn hơn phát hiện ra đã nằm sẵn trong giá trị đánh giá.
   - Mô hình hai tầng giả định đối thủ biết trước nước của mình (xem phần mô hình). Ở độ sâu lớn, giả định bi quan này lặp lại ở mọi chu kỳ, nên đối thủ trong cây "né" được mọi phát bắn, điều đối thủ thật không làm được.
9. **Cái làm bản tối ưu mạnh hơn ở cùng độ sâu là phạt lặp, không phải các tối ưu tốc độ.** Ở cùng độ sâu, nó thắng Heuristic Alpha-Beta 63% (độ sâu 2) và 58% (độ sâu 3). Thí nghiệm 5 đã cho thấy ba tối ưu tìm kiếm không đổi giá trị ở gốc, nên phần hơn này đến từ phạt lặp và cách phá thế hoà. Ở 50 ms, lợi thế này mất đi vì chính iterative deepening cũng giúp Heuristic Alpha-Beta mạnh lên (56,5% so với chính nó ở độ sâu cố định 3): nước tốt nhất của vòng trước được duyệt đầu tiên nên được giữ khi hoà điểm, tức tác nhân ưu tiên nước vừa tốt ở tầm ngắn vừa tốt ở tầm xa.
10. **Vậy với trò chơi này, các tối ưu tìm kiếm chủ yếu giúp về thời gian, không giúp về sức mạnh.** Ở độ sâu 3, mức mà sau đó tìm sâu hơn không còn giúp, cả ba tối ưu chỉ tiết kiệm khoảng 1/3 thời gian (trung bình 9,6 ms so với 14,4 ms mỗi quyết định trên 10 tình huống của thí nghiệm 5). Lợi ích lớn (nhanh gấp 6 lần) chỉ xuất hiện ở độ sâu 5, nơi độ sâu thêm không còn đổi thành ván thắng. Đây là kết luận trung thực của thí nghiệm. Muốn mạnh hơn, hướng đúng là cải thiện hàm đánh giá hoặc mô hình nước đi đồng thời, không phải tìm nhanh hơn.

### Yêu cầu 3: Giao diện và tích hợp thuật toán nhóm khác

**Màu hai người chơi:** P1 vàng (như tank người chơi 1 của game gốc), P2 xanh dương. Cặp màu này đã chạy bộ kiểm tra bảng màu trên nền đen: khác nhau rõ khi mù màu (độ lệch tệ nhất 24 trên thang OKLab) và đủ tương phản. Riêng màu vàng sáng hơn dải mà công cụ đó dành cho biểu đồ, điều chấp nhận được với một sprite.

**Menu:** tiêu đề xếp bằng gạch như logo của game gốc; chọn hai người chơi, chọn bản đồ qua ảnh xem trước, thời gian mỗi quyết định, số ván trong trận (đổi bên sau mỗi ván). Mặc định là **người chơi (bàn phím) đấu với bộ điều khiển tối ưu**, nên mở game lên chỉ cần bấm `Enter`. Mỗi lựa chọn có nhãn nhỏ giúp chọn đối thủ: `strong` cho ba bản có heuristic (ở cùng thời gian chúng mạnh ngang nhau, xem thí nghiệm 6), `weak: no heuristic`, `easiest` cho Random, `plugin` cho thuật toán nạp thêm. Dòng cuối menu nhắc phím điều khiển của người chơi đã chọn.

**Khi người tự lái tank:**

- Mỗi chu kỳ là một lượt: game **chờ** người bấm phím rồi mới chạy, còn AI vẫn bị giới hạn thời gian như thường. Người 1 dùng `W A S D`, `Space` bắn, `X` đứng yên; người 2 dùng mũi tên, `Enter`, `Right Shift`. Chơi một mình thì dùng bộ nào cũng được.
- **Không mất phím:** phím bấm trong lúc chu kỳ trước còn đang chạy hoạt ảnh được giữ lại làm nước của lượt sau. **Giữ phím** thì tank đi tiếp mỗi lượt, như game arcade.
- Tank của người có nhãn **YOU** (hoặc 1P/2P khi hai người chơi). Khi đến lượt, tank có **khung nhấp nháy** và thanh trên cùng hiện **YOUR MOVE**.
- Bảng bên phải thay số liệu của AI bằng **hình phím bấm** và nước đi kế tiếp đã nhận.
- Đường đi dự tính của AI (`V`) tắt sẵn, vì nó để lộ ý định của AI. Vẫn bật lại được.
- `P` tạm dừng, hiện chữ **PAUSE** lớn giữa sân như game gốc. Hết ván, màn kết thúc nói thẳng với người chơi: **YOU WIN!**, **GAME OVER** hoặc **DRAW**.

**Khi chơi:** hoạt ảnh đạn bay từng ô, bánh xích chuyển động khi tank đi, tank xoay hướng giữa lúc di chuyển (sprite pixel không xoay mượt nên đổi hướng tức thì), HP giảm đúng lúc va chạm. Trúng tường hiện vụ nổ nhỏ, trúng tank hoặc căn cứ hiện vụ nổ lớn hơn khi bị phá huỷ, kèm số sát thương. Căn cứ là con đại bàng, hết máu thì thành đống đổ nát. Tường gạch mất dần từng mảng khi bị bắn (3 máu: nguyên khối, 2 máu: nửa phải, 1 máu: một mảng). Tác nhân chạy ở luồng riêng để cửa sổ không bị treo. Cửa sổ tự co giãn theo màn hình.

**Nhìn thấy AI đang nghĩ gì:**

- **Đường đạn (`L`):** nơi phát bắn kế tiếp sẽ đi tới.
- **Kế hoạch (`V`):** đường đi mà tìm kiếm đang dự tính cho tank.
- **Bản đồ công sức (`H`):** công sức từ mỗi ô để bắn được căn cứ địch, kèm con số.
- **Biểu đồ "Who is ahead":** ý kiến trung lập về lợi thế theo chu kỳ, giống nhau với mọi thuật toán, rê chuột để đọc từng chu kỳ.
- **Bảng người chơi:** hành động, thời gian, độ sâu, số trạng thái, giá trị.
- **Kết thúc ván:** lý do thắng, số phát bắn, số phát trúng, số tường đã phá. Có thể xem lại từng chu kỳ bằng `←`/`→`.

**Cách nhóm khác tham gia.** Có ba cách: **kéo tệp `.py` thả vào cửa sổ**; chép vào thư mục [plugins/](Task%202/plugins/) rồi bấm **Reload**; hoặc truyền đường dẫn qua `--p1`/`--p2`. Có hai dạng tệp:

```python
# Dạng 1: một hàm, không cần import gì từ dự án này
AGENT_NAME = "Nhóm 9"

def choose_action(observation):
    me = observation["my_tank"]         # {"x", "y", "facing", "hp"}
    base = observation["enemy_base"]    # {"x", "y", "hp"}
    # Các khoá khác: player, width, height, cycle, max_cycles, enemy_tank, my_base,
    # walls [{"x","y","hp"}], bullets [{"x","y","direction","mine"}]
    return "FIRE"                       # hoặc MOVE_UP, MOVE_DOWN, MOVE_LEFT, MOVE_RIGHT, STAY
```

```python
# Dạng 2: lớp con của Agent, dùng được GameRules để mô phỏng
from tank_battle.agents import Agent
from tank_battle.model import Action
from tank_battle.rules import GameRules

class MyAgent(Agent):
    name = "Nhóm 3"
    def choose_action(self, state, player):
        return Action.FIRE
```

Lớp có tên bắt đầu bằng `_` được coi là lớp phụ trợ và không xuất hiện trong danh sách người chơi.

Có các ví dụ chạy được: [plugins/example_function_agent.py](Task%202/plugins/example_function_agent.py), [plugins/example_class_agent.py](Task%202/plugins/example_class_agent.py), và 4 đối thủ tập luyện ở [plugins/sparring_partners.py](Task%202/plugins/sparring_partners.py).

**Luật áp dụng như nhau cho mọi thuật toán** ([session.py](Task%202/tank_battle/session.py)):

- Hai bên cùng nhận một trạng thái và lần lượt được toàn bộ CPU.
- Mỗi tác nhân chỉ nhận **bản sao** trạng thái, nên không thể sửa game thật.
- Tác nhân gặp lỗi, trả về giá trị sai, hoặc quá `1,5 × thời gian + 0,05 giây` thì đứng yên ở chu kỳ đó, và lỗi được ghi lại.
- Tệp plugin hỏng được báo trên menu và không làm dừng chương trình.

**Giới hạn đã biết.** Plugin chạy trong cùng tiến trình và không bị cách ly, nên chỉ nên nạp mã của nhóm mà bạn tin tưởng. Python cũng không dừng được luồng đang chạy, nên một plugin bị treo sẽ đứng yên ở các chu kỳ sau nhưng vẫn chiếm CPU.

### Giả định về luật game (đề không nói rõ)

| Tình huống | Quyết định | Lý do |
|---|---|---|
| Di chuyển bị chặn | Tank vẫn quay hướng, không tiến | Nếu không, tank không thể ngắm tường ngay bên cạnh |
| Hai tank vào cùng một ô, hoặc đổi chỗ | Không tank nào được đi | Công bằng cho cả hai bên |
| Đạn trúng tank hoặc căn cứ phe mình | Vẫn tính sát thương | Đề nói đạn gây va chạm khi gặp tank hoặc căn cứ, không loại trừ phe mình |
| Hai viên đạn gặp nhau | Bay xuyên qua nhau | Đề không liệt kê đạn là vật thể va chạm |
| Giới hạn số đạn hoặc hồi chiêu | Không có | Đề không yêu cầu |
| Hai bên cùng mất một tài sản trong một bước | Hoà | Mỗi bên còn số tài sản như nhau |
| Giới hạn chu kỳ | 300, sau đó hoà | Cần để ván đấu luôn kết thúc; đề không quy định |

Nếu đề hoặc giảng viên quy định khác, các điểm này đều nằm trong [rules.py](Task%202/tank_battle/rules.py) và dễ sửa. Khi đó nên chạy lại `run_tuning.py`, vì trọng số được tinh chỉnh theo luật hiện tại.

---

## Task 3: Kakuro (Constraint Satisfaction Problem)

### Cách chạy

Chạy trong thư mục `Task 3`:

```bash
python main.py                          # mở giao diện
python main.py --solve "Complex (9x9)"  # giải trong terminal
python main.py --file board.txt         # thêm bàn cờ từ tệp văn bản vào giao diện
python run_evaluation.py                # đánh giá, khoảng 15 phút
python -m unittest discover -s tests    # kiểm thử
```

| Tệp | Vai trò |
|---|---|
| [kakuro/puzzle.py](Task%203/kakuro/puzzle.py) | `KakuroPuzzle`, `Run`, `SolutionChecker`, các bàn cờ |
| [kakuro/csp.py](Task%203/kakuro/csp.py) | `KakuroCSP`, `RunFilter` (lọc GAC) |
| [kakuro/solver.py](Task%203/kakuro/solver.py) | `BacktrackingSolver`, `SolverConfig`, `SearchObserver` |
| [kakuro/generator.py](Task%203/kakuro/generator.py) | `BoardGenerator`: sinh bàn ngẫu nhiên để đánh giá |
| [kakuro/trace.py](Task%203/kakuro/trace.py) | `TraceRecorder`, `Replay`, `SearchTree` |
| [kakuro/play.py](Task%203/kakuro/play.py) | `PlayBoard`: luật chơi cho người, ứng viên, gợi ý |
| [kakuro/gui/](Task%203/kakuro/gui/) | Giao diện PyGame |
| [kakuro/evaluation.py](Task%203/kakuro/evaluation.py) | Đánh giá độ đúng, độ ổn định, hiệu quả, bàn khó |

### Yêu cầu 1: Mô hình hoá CSP

| Thành phần | Định nghĩa |
|---|---|
| **Biến** | Mỗi ô trắng là một biến. Bàn 5×5 có 12 biến, bàn 9×9 có 48 biến. |
| **Miền giá trị** | {1, …, 9} cho mọi biến, lưu dưới dạng bit mask. |
| **Ràng buộc** | Mỗi "run" (dãy ô trắng liên tiếp thuộc một gợi ý) có một ràng buộc n-ngôi: các số **đều khác nhau** và **tổng bằng gợi ý**. Bàn 5×5 có 8 ràng buộc, bàn 9×9 có 28. |

Mỗi ô trắng thuộc đúng hai run, một ngang và một dọc, nên ràng buộc đan xen với nhau qua các ô chung.

**Nhập bàn cờ.** Mình chép hai bàn từ ảnh trong đề, với mỗi ô là `X` (ô đen), `.` (ô trắng), hoặc `dọc\ngang` (ô gợi ý). Bàn được kiểm chứng theo ba cách:

- Mọi ô trắng được cộng đúng một lần theo mỗi chiều, nên tổng gợi ý ngang phải bằng tổng gợi ý dọc: 60 = 60 ở bàn 5×5 và 249 = 249 ở bàn 9×9.
- Mỗi bàn có đúng một nghiệm, điều mà một lỗi chép đề khó có thể tạo ra.
- Bàn 5×5 được giải tay độc lập và cho cùng kết quả.

#### Các kỹ thuật và lý do chọn

**Lọc ràng buộc bằng GAC.** Ràng buộc là n-ngôi nên AC-3 dạng nhị phân không áp dụng trực tiếp được. Mình dùng tính nhất quán cung tổng quát (GAC): giữ một chữ số trong miền chỉ khi nó thuộc một cách điền đầy đủ và hợp lệ nào đó của run.

Thay vì thử mọi hoán vị (đến 9!), `RunFilter` điền từ trái sang phải và chỉ theo dõi *tập chữ số đã dùng*. Chỉ có tối đa 512 tập, và mỗi tập đã xác định luôn tổng, nên bước quét xuôi tìm tập đến được, bước quét ngược giữ lại tập còn hoàn thành được đúng gợi ý. Kết quả được ghi nhớ vì tìm kiếm gặp lại cùng miền rất nhiều lần. Test so khớp bộ lọc với vét cạn trên 1.500 miền ngẫu nhiên.

GAC mạnh hơn kiểm tra từng cặp. Ví dụ 3 ô cùng có miền {1, 2} bị phát hiện mâu thuẫn ngay, dù mỗi cặp ô riêng lẻ đều thoả được.

Bộ lọc tự suy ra các tập chữ số đặc trưng của Kakuro: tổng 16 trên 2 ô cho {7, 9}, tổng 3 trên 2 ô cho {1, 2}, tổng 28 trên 7 ô cho {1, …, 7}, tổng 44 trên 8 ô cho {2, …, 9}.

**Ba mức lan truyền**, chọn được trong giao diện:

| Mức | Cách làm | Khi nào nên dùng |
|---|---|---|
| Không | Chỉ kiểm tra giá trị mới với các ô đã gán: không trùng, tổng còn đạt được | Làm mốc so sánh |
| Forward checking | Sau khi gán, chỉ lọc các ô cùng run, không lan tiếp. Bắt đầu bằng một lượt lọc từng run | Chi phí thấp, vẫn còn tìm kiếm thật |
| **MAC (GAC-3)** | Sau mỗi phép gán, chạy hàng đợi run: run nào đổi miền thì đưa run giao với nó vào lại hàng đợi | Mạnh nhất, được dùng làm mặc định |

**Heuristic thứ tự biến và giá trị:**

- **MRV** chọn biến có ít giá trị còn lại nhất, để gặp thất bại sớm.
- **Degree** phá hoà bằng số ô chưa gán cùng run.
- **dom/wdeg** chọn biến có tỉ số nhỏ nhất giữa kích thước miền và trọng số. Mỗi lần một run gây bế tắc thì trọng số của run đó tăng, nên tìm kiếm tự học chỗ nào của bàn là khó và xử lý trước.
- **LCV** thử trước giá trị loại ít chữ số của các ô lân cận nhất, đo bằng chính `RunFilter`.

**Restart.** Thời gian tìm kiếm trên các bàn này có phân bố đuôi nặng: vài lựa chọn sớm quyết định giữa trả lời ngay và chạy rất lâu. Restart từ bỏ khởi đầu xấu, trong khi dom/wdeg vẫn giữ những gì đã học. Ngân sách số lần lùi tăng dần (64, nhân 1,5 mỗi lần) nên tìm kiếm vẫn đầy đủ: bàn vô nghiệm cuối cùng vẫn được chứng minh là vô nghiệm.

**Cấu hình mặc định** (`SolverConfig.best()`): MAC + dom/wdeg + tăng dần + restart, chọn theo kết quả đo ở dưới.

**Tối ưu cài đặt.** Các tối ưu sau không làm đổi lần tìm kiếm nào: cùng nghiệm, cùng số lần gán, số lần lùi và số lần lọc.

- **Degree tính trong O(1).** Run ngang và run dọc của một ô chỉ chung đúng ô đó, nên số hàng xóm chưa gán là `(ô chưa gán của run ngang − 1) + (của run dọc − 1)`. Số ô chưa gán của mọi run được đếm một lần cho mỗi lượt chọn, thay vì duyệt hàng xóm của từng ô.
- **Bỏ qua biến chắc chắn thua.** Với MRV + degree, biến có miền lớn hơn miền nhỏ nhất đã gặp không thể được chọn, nên không cần tính degree cho nó.
- **dom/wdeg** dùng cùng bảng đếm đó để biết run nào còn ô chưa gán khác.
- **`RunFilter` cắt sớm theo tổng.** Khi quét xuôi, tập chữ số nào không thể đạt gợi ý (kể cả khi các ô còn lại lấy chữ số nhỏ nhất hoặc lớn nhất) bị bỏ ngay. Lượt quét ngược vốn cũng sẽ loại các tập này.
- Miền của một run được đọc bằng `itemgetter` dựng sẵn cho từng run.

Test so với cài đặt cũ trên nhiều bàn và cấu hình, và so `RunFilter` mới với bản cũ trên 3.000 bộ miền ngẫu nhiên. Đo trong cùng điều kiện trên 8 bàn 20×20 cùng hai bàn mẫu: MAC + MRV + degree nhanh hơn 1,5 lần, FC + dom/wdeg nhanh hơn 2 lần, cấu hình mặc định nhanh hơn 1,15 lần.

### Yêu cầu 2: Đánh giá trên bàn cờ phức tạp

**Nghiệm của bàn 9×9** (hàng 2 đến 9, `.` là ô đen hoặc ô gợi ý; hàng 1 không có ô trắng):

```
. . 5 9 8 . 1 2 .
. . 2 7 1 3 4 6 5
. 8 6 . . 1 2 8 9
. 9 8 . 3 2 8 9 .
. . 9 8 6 5 . 7 5
. 3 4 5 2 . . 4 2
. 9 3 7 1 6 8 5 .
. . 7 9 . 1 4 3 .
```

**Nghiệm của bàn 5×5** (hàng 2 đến 5):

```
. . 8 4 .
. 9 3 1 8
. 5 1 2 3
. . 9 7 .
```

#### Độ đúng

| Kiểm tra | 5×5 | 9×9 |
|---|---:|---:|
| Bộ kiểm tra độc lập (duyệt lại lưới gốc, không dùng mô hình CSP) không thấy lỗi | Đạt | Đạt |
| Số nghiệm khi tìm vét cạn | 1 | 1 |
| Mọi cấu hình cho cùng một nghiệm | Đạt | Đạt |
| Trạng thái khôi phục đúng sau tìm vét cạn | Đạt | Đạt |
| Tăng một gợi ý ngang thêm 1 (bàn chắc chắn vô nghiệm vì hai tổng lệch nhau) bị từ chối | 4/4 | 14/14 |

#### Độ hiệu quả (bàn 9×9, thứ tự theo hàng, trung vị 15 lần chạy)

| Cấu hình | ms | Lần gán | Điểm rẽ nhánh | Backtrack | Lần lọc | Chữ số bị loại |
|---|---:|---:|---:|---:|---:|---:|
| Không / cố định / tăng dần | 7,85 | 1.436 | 1.436 | 1.388 | 0 | 0 |
| FC / cố định / tăng dần | 1,67 | 133 | 29 | 85 | 262 | 610 |
| FC / MRV / tăng dần | 1,66 | 96 | 16 | 48 | 214 | 551 |
| FC / MRV + degree / tăng dần | 1,75 | 79 | 11 | 31 | 179 | 473 |
| FC / MRV + degree / LCV | 2,38 | 86 | 11 | 38 | 196 | 499 |
| FC / dom/wdeg / tăng dần | 3,89 | 326 | 80 | 278 | 634 | 1.198 |
| MAC / cố định / tăng dần | 2,07 | 48 | 0 | 0 | 190 | 384 |
| MAC / MRV + degree / LCV | 2,51 | 48 | 0 | 0 | 190 | 384 |
| MAC / dom/wdeg / tăng dần | 2,56 | 48 | 0 | 0 | 190 | 384 |

#### Độ ổn định (bàn 9×9, 30 lần chạy, giới hạn 5 giây mỗi lần)

Mỗi lần chạy xáo thứ tự giá trị và phá hoà ngẫu nhiên. Với "thứ tự cố định", bản thân thứ tự biến cũng ngẫu nhiên.

| Cấu hình | Giải xong | Số nghiệm khác nhau | ms (TB ± ĐLC) | ms lớn nhất | Lần gán (TB) | Backtrack lớn nhất |
|---|---:|---:|---:|---:|---:|---:|
| Không / cố định / tăng dần | **0/30** | 0 | 5.000 (chạm giới hạn) | 5.000 | 601.297 | 692.599 |
| FC / cố định / tăng dần | 28/30 | 1 | 1.106 ± 1.578 | 5.001 | 260.875 | 1.241.306 |
| FC / MRV / tăng dần | 30/30 | 1 | 2,23 ± 0,47 | 3,31 | 99,8 | 169 |
| FC / MRV + degree / tăng dần | 30/30 | 1 | 2,77 ± 0,92 | 4,45 | 107,0 | 140 |
| FC / MRV + degree / LCV | 30/30 | 1 | 3,86 ± 0,88 | 6,46 | 119,9 | 129 |
| FC / dom/wdeg / tăng dần | 30/30 | 1 | 5,40 ± 3,03 | 16,67 | 280,4 | 1.130 |
| MAC / cố định / tăng dần | 30/30 | 1 | 2,84 ± 0,61 | 4,68 | 48,0 | 0 |
| MAC / MRV + degree / LCV | 30/30 | 1 | 3,29 ± 0,65 | 4,82 | 48,0 | 0 |
| MAC / dom/wdeg / tăng dần | 30/30 | 1 | 3,23 ± 0,50 | 4,13 | 48,0 | 0 |

#### Bàn khó sinh ngẫu nhiên (24 bàn mỗi cỡ, giới hạn 10 giây mỗi bàn)

Hai bàn của đề quá dễ với MAC nên không phân biệt được các heuristic. Bộ sinh tạo ra các bàn lớn hơn, cùng một bộ bàn cho mọi cấu hình. Các bàn này thường có nhiều nghiệm, nên đây là đo việc **tìm một nghiệm**.

| Cỡ bàn | Cấu hình | Giải xong | ms (trung vị) | ms (TB) | Backtrack (TB) |
|---|---|---:|---:|---:|---:|
| 13×13 | FC / MRV + degree / tăng dần | 18/24 | 9 | 2.510 | 270.879 |
| 13×13 | MAC / MRV + degree / LCV | 21/24 | 33 | 1.299 | 47.911 |
| 13×13 | MAC / dom/wdeg / tăng dần | 23/24 | 28 | 498 | 3.983 |
| 13×13 | **MAC / dom/wdeg / tăng dần / restart** | **24/24** | 30 | **35** | 20 |
| 16×16 | FC / MRV + degree / tăng dần | 9/24 | 10.000 | 6.628 | 471.701 |
| 16×16 | MAC / MRV + degree / LCV | 17/24 | 79 | 3.246 | 87.413 |
| 16×16 | MAC / dom/wdeg / tăng dần | 23/24 | 58 | 1.317 | 18.338 |
| 16×16 | **MAC / dom/wdeg / tăng dần / restart** | **24/24** | 52 | **75** | 115 |
| 20×20 | FC / MRV + degree / tăng dần | 3/24 | 10.000 | 8.757 | 428.823 |
| 20×20 | MAC / MRV + degree / LCV | 9/24 | 10.000 | 6.387 | 155.261 |
| 20×20 | MAC / dom/wdeg / tăng dần | 17/24 | 434 | 3.442 | 28.130 |
| 20×20 | **MAC / dom/wdeg / tăng dần / restart** | **24/24** | 135 | **235** | 423 |

Với các cấu hình chạm giới hạn 10 giây, số lần lùi trung bình cao hơn lần đo trước vì bộ giải nhanh hơn, nên lùi được nhiều lần hơn trong cùng thời gian. Riêng MAC + dom/wdeg ở 16×16 giờ giải được 23/24 bàn (trước là 21/24) trong giới hạn đó.

Bảng đầy đủ (8 cấu hình) nằm trong [Task 3/results/hard_boards.csv](Task%203/results/hard_boards.csv), các bảng khác cũng trong [Task 3/results/](Task%203/results/).

#### Nhận xét

1. **MAC giải cả hai bàn của đề hoàn toàn bằng lan truyền.** Không có điểm rẽ nhánh nào: 48 lần gán cho 48 biến, và 0 backtrack trong cả 30 lần chạy, bất kể thứ tự biến.
2. **Thứ tự theo hàng là may mắn.** Backtracking thuần chỉ mất 7,6 ms với thứ tự đó, nhưng với thứ tự biến ngẫu nhiên thì không lần nào xong trong 5 giây. Nếu chỉ nhìn bảng hiệu quả sẽ tưởng backtracking thuần đủ tốt.
3. **Restart + dom/wdeg là cải tiến lớn nhất trên bàn khó.** Ở 20×20, giải được 24/24 với trung bình 0,24 giây, so với 9/24 và 6,4 giây của cấu hình MAC + MRV + degree + LCV trước đây. Phân bố đuôi nặng thấy rõ ở chỗ trung vị thấp trong khi trung bình rất cao, và restart xử lý đúng phần đuôi đó.
4. **Heuristic tốt phụ thuộc vào độ khó.** Trên bàn 9×9 dễ, dom/wdeg với FC lại **tệ hơn** MRV + degree (278 so với 31 lần lùi), vì lúc đầu chưa có bế tắc nào để học. Nó chỉ phát huy trên bàn khó. Đó là lý do nên đánh giá trên nhiều loại bàn.
5. **LCV không có lợi rõ rệt, kể cả trên bàn nhiều nghiệm.** Trước đó mình đoán LCV sẽ giúp khi có nhiều nghiệm. Phép đo không ủng hộ điều này: với MAC + dom/wdeg, thứ tự tăng dần giải được 23, 23, 17 bàn trên 24 (13×13, 16×16, 20×20), còn LCV giải 23, 21, 17, và thời gian trung bình không tốt hơn một cách nhất quán. Vì vậy mặc định dùng thứ tự tăng dần.
6. **Về thời gian tuyệt đối trên bàn của đề,** các cấu hình tốt đều chỉ mất vài mili giây, nên chênh lệch giữa chúng không có nhiều ý nghĩa ở kích thước này.

### Yêu cầu 3: Giao diện

Bộ giải ghi lại từng bước, nên giao diện có thể tua tới, tua lui và kéo tự do trên thanh thời gian. Cửa sổ tự co giãn theo màn hình. Có hai chế độ.

#### Chế độ xem bộ giải

| Đề yêu cầu | Trên giao diện |
|---|---|
| **Miền giá trị** | Mỗi ô trống hiện các chữ số còn lại theo lưới 3×3, chữ số đã bị loại vẫn hiện mờ. Ô chỉ còn một giá trị hiện số to màu xanh dương. Ô đã gán hiện số to màu đậm. Ô ít giá trị được tô vàng, cho thấy MRV đang nhắm vào đâu (tắt bằng nút `Heat`). |
| **Lan truyền ràng buộc** | Run đang lọc được tô xanh và gợi ý của nó được khoanh tròn. Chữ số vừa bị loại hiện màu đỏ và bị gạch. Bảng bên phải hiện hàng đợi và **các tập chữ số còn khả dĩ** của run, tức lý do chữ số bị loại. Bấm vào ô hoặc gợi ý bất kỳ để xem. Dòng mô tả giải thích từng bước. |
| **Backtracking** | Bảng đường đi hiện theo từng độ sâu: giá trị đã thất bại (đỏ, gạch), đang thử (xanh lá), còn lại (xám). Cây tìm kiếm lớn dần theo thời gian, nhánh thất bại màu đỏ, nhánh hiện tại nổi bật; rê chuột để đọc nút, bấm để nhảy tới đúng thời điểm đó. Thanh thời gian đánh dấu mọi lần gán và lần lùi. |

**Lưu ý khi trình bày.** Với hai bàn của đề, MAC giải xong mà không backtrack lần nào. **Muốn xem backtracking, hãy chọn bàn `Extra (10x10)`** (MAC lùi 27 lần), hoặc chọn `Forward checking` trên bàn 9×9. Bàn Extra do bộ sinh tạo ra, **không thuộc đề và có nhiều nghiệm**, chỉ dùng để minh hoạ. Giao diện không dùng restart để cây tìm kiếm là một lần tìm kiếm liên tục.

**Phím:** `Space` chạy hoặc dừng, mũi tên trái/phải đi từng bước, mũi tên lên/xuống nhảy tới lựa chọn tiếp theo, `-`/`=` đổi tốc độ, `M` bật tắt tô vàng, `Esc` thoát.

#### Chế độ tự chơi

Đề yêu cầu giao diện "cho trò chơi", nên người dùng có thể tự giải. Kiểu dáng bám theo kakuros.com, đọc trực tiếp từ mã nguồn trang đó: nền trắng, ô trống màu trắng, ô chặn và ô gợi ý màu xám `#e2e2e2` với đường chéo, ô đang sửa màu `#eeeeee`, run đang xét màu xanh nhạt `#dff8ff`, **bảng chọn số màu xanh `#69d`** hiện cạnh ô vừa bấm, chữ số đúng màu xanh lá và chữ số sai màu đỏ.

- Bấm một ô trắng để hiện bảng 1–9 và X (xoá); bấm số để điền. Hoặc gõ `1`–`9`, `Backspace` để xoá, mũi tên để di chuyển. Bấm lại ô đó để đóng bảng.
- **Rê chuột vào một gợi ý** để xem mọi tập chữ số có thể tạo nên tổng đó (ví dụ `17 = 8 + 9`), như phần chú thích của kakuros.com.
- Ô vi phạm luật (trùng số, tổng không thể đạt được) hiện số màu đỏ ngay.
- Chọn **bàn của đề** hoặc **bàn ngẫu nhiên** cỡ 4×4, 5×5, 7×7, 9×9, 10×10, 13×13 (cỡ tính cả hàng và cột gợi ý, như trên kakuros.com). Nút **New puzzle** sinh bàn mới cùng cỡ.
- **Show solution** điền đáp án, **Candidates** hiện các chữ số mà lan truyền ràng buộc còn cho phép, **Hint** điền ô đang chọn hoặc ô đầu tiên đang trống hay sai.
- **Undo** (hoặc `Ctrl+Z`) lấy lại thay đổi gần nhất: một chữ số, một lần xoá, một gợi ý, kể cả lần xoá cả bàn bằng **Clear**.
- **Đồng hồ** đếm thời gian giải và số lần dùng Hint, dừng khi giải xong ("Solved in 03:12!"). Bàn được điền bằng Show solution không tính là tự giải.
- Khi giải xong, bàn mờ đi và hiện dòng "The current puzzle is successfully solved!" kèm nút New puzzle, giống kakuros.com. Game nhận mọi lời giải hợp lệ, không chỉ một đáp án cố định, vì bàn ngẫu nhiên thường có nhiều nghiệm.
- Bảng bên phải hiện các tập chữ số còn khả dĩ của hai run đi qua ô đang chọn.

**Hai bộ màu.** Mặc định là bộ sáng kiểu kakuros.com ("classic"); nút **Theme** ở góc dưới bên trái (hoặc phím `T`) chuyển sang bộ tối cũ. Cả chế độ xem bộ giải lẫn chế độ tự chơi dùng chung bộ màu. Màu xanh lá của kakuros.com (`#00cc00`) được làm đậm hơn một chút để đọc rõ trên nền trắng.

**Gõ số khi có bộ gõ tiếng Việt.** Cửa sổ tắt chế độ nhập văn bản, vì bộ gõ (Telex, Unikey) có thể giữ phím số lại ở dạng "đang soạn" và chỉ gửi đi khi bấm phím khác. Nếu bộ gõ vẫn gửi số dưới dạng văn bản, game cũng nhận.

### Giới hạn của Task 3

- Đề nói các heuristic thuộc Lecture 08 nhưng mình không có slide. MRV, Degree, LCV, MAC theo giáo trình AIMA. dom/wdeg và restart **không nằm trong AIMA** mà là kỹ thuật bổ sung từ các bộ giải CSP thực tế, nên nếu giảng viên yêu cầu chỉ dùng kỹ thuật trong bài giảng thì có thể chọn cấu hình khác trong giao diện. Hãy đối chiếu tên gọi "GAC" so với AC-3 với slide của lớp.
- Bộ sinh rất khó tạo ra bàn có đúng một nghiệm: chỉ 3/900 lần thử được chứng minh là duy nhất, và không bàn nào trong số đó có độ khó phù hợp để minh hoạ. Vì vậy bảng bàn khó đo việc tìm một nghiệm, không phải bài toán có nghiệm duy nhất như Kakuro chuẩn.

---

## Tối ưu hiệu năng

Trừ một ngoại lệ ghi rõ ở Task 1, mọi tối ưu dưới đây **không đổi kết quả**, chỉ đổi tốc độ. Mỗi tối ưu đều được kiểm chứng hai cách:

1. Bài đo cho cùng dấu vân tay (SHA-256 của mọi nước đi, giá trị, số nút, số bước, nghiệm) với bản trước khi tối ưu.
2. Có test so trực tiếp với một cài đặt tham chiếu viết theo cách cũ.

| Task | Chỗ tối ưu | Cách làm | Nhanh hơn (đo cùng điều kiện) |
|---|---|---|---:|
| 2 | Hàm đánh giá (59% thời gian tìm kiếm) | Dijkstra dừng ngay khi ô cần hỏi đã chắc chắn và chạy tiếp ở lần hỏi sau; thêm một cận để bỏ hẳn việc tìm đường tới tank khi chắc chắn căn cứ là mục tiêu tốt hơn | Ván thật, độ sâu 4: **2,3×** (5,73 → 2,53 s) |
| 2 | `step`, `_order`, `can_enter` | Giữ lại đối tượng tank không đổi, bỏ lambda khi sắp xếp, bỏ generator | (đã gồm ở trên) |
| 1 | Min-Conflicts: chọn giá trị | Quét bằng hàm C (`list.count`/`index`); bốc ngẫu nhiên phần tử hoà mà không dựng danh sách | Mỗi bước ở N = 4096: **1,36×** |
| 1 | Min-Conflicts: heuristic chọn biến | Giữ các hàng theo nhóm số xung đột, lấy nhóm cao nhất thay vì duyệt mọi hàng. **Ngoại lệ:** vẫn chọn đều ngẫu nhiên trong đúng tập hàng như trước, nhưng thứ tự bốc khác nên từng lần chạy khác; bảng kết quả đã được đo lại | Mỗi bước ở N = 4096: **1,76×**. Heuristic giờ nhanh hơn bản chuẩn khoảng 20% về thời gian, thay vì 3% |
| 3 | Chọn biến MRV + degree, dom/wdeg; lọc run | Đếm ô chưa gán theo run một lần (degree = hai phép cộng); bỏ qua biến có miền lớn hơn mức nhỏ nhất; cắt sớm theo tổng trong quy hoạch động | MAC + MRV + degree **1,5×**, FC + dom/wdeg **2,0×** |

Phần SAT của Task 1 không tối ưu thêm được bằng code: ở N = 120, thời gian nằm ở việc tạo và nạp 2,85 triệu mệnh đề (gần giới hạn của Python), còn bộ giải chỉ mất khoảng 19 ms. Cách giảm thật sự là mã hoá sequential counter, đã có sẵn.

## Kiểm thử

Trong mỗi thư mục task:

```bash
python -m unittest discover -s tests
```

Giao diện được kiểm thử tự động qua SDL dummy driver, không cần cửa sổ thật, và cả hai cửa sổ thật đã được mở chạy thử trên Windows. Các thao tác bằng chuột và bàn phím thật, cũng như kéo thả tệp thật vào cửa sổ, chưa được thử trực tiếp, nên hãy thử một lượt trước khi demo. Riêng việc **giữ phím** để tank đi tiếp (Task 2) chỉ được test bằng cách giả lập trạng thái bàn phím, còn phím tắt `Ctrl+Z` (Task 3) chưa có test tự động (nút Undo thì có), nên càng cần thử bằng tay.

## Lưu ý về số liệu

Mọi số liệu đo trên Windows 11, Intel (Family 6 Model 183), Python 3.14.7, ghim vào các nhân hiệu năng, **không phải cấu hình đánh giá của đề** (macOS 13.7.8, Intel Core i5). Cần chạy lại các thí nghiệm trên máy đó trước khi đưa thời gian vào báo cáo:

- **Task 1:** số mệnh đề, số bước và tỉ lệ thành công không phụ thuộc vào máy về mặt thuật toán; riêng số conflicts có thể khác nếu phiên bản PySAT khác.
- **Task 2:** chạy lại `run_experiments.py`. Tương quan giữa các cấu hình sẽ tương tự, nhưng thời gian tuyệt đối và độ sâu đạt được trong giới hạn thời gian sẽ khác.
- **Task 3:** chạy lại `run_evaluation.py`. Số lần gán ở các bảng không ngẫu nhiên sẽ giữ nguyên, còn thời gian sẽ khác, và số lần chạy chạm giới hạn thời gian có thể thay đổi theo tốc độ máy.

Khi đo thời gian trên máy có nhân hiệu năng và nhân tiết kiệm điện (như máy dùng để đo ở đây), Windows có thể chuyển tiến trình giữa hai loại nhân, làm thời gian dao động tới 2–3 lần. Đó là lý do các số liệu ở trên được đo khi đã ghim vào nhân hiệu năng. Số trạng thái, số bước và kết quả ván đấu ở độ sâu cố định thì không bị ảnh hưởng.

## Việc còn lại phải làm

1. **Task 4 (1 điểm): báo cáo và vấn đáp.**
   - Báo cáo dùng mẫu IEEE conference trên Overleaf, tối đa 5 trang 2 cột, trích dẫn theo chuẩn IEEE.
   - Gồm các mục: Title, Authors (giảng viên là tác giả cuối), Abstract, mỗi task một mục có hình và bảng, Contributions (việc và mức hoàn thành 0–100% của từng người), Self-evaluation (tự đánh giá và ước điểm), Conclusion.
   - Số liệu và nhận xét đã có sẵn trong các mục Task 1, 2, 3 ở trên. Tên thành viên và phần đóng góp thì nhóm phải tự điền.
   - **Vấn đáp:** đề ghi rõ nếu không giải thích được ý tưởng và cài đặt thì task đó bị 0 điểm. Mỗi thành viên nên đọc kỹ mục của phần mình và chạy thử code.
2. **Trang 7 của đề vẫn chưa có.** Nhiều khả năng là hướng dẫn nộp bài.
3. **Chạy lại thí nghiệm trên macOS 13.7.8, Intel Core i5** (xem mục "Lưu ý về số liệu"). Code chưa từng được chạy trên macOS. Cú pháp đã được kiểm tra tương thích với Python 3.9 (bản đi kèm macOS 13).
4. **Xem lại các giả định về luật game** ở mục "Giả định về luật game" của Task 2, vì đề không nói rõ một số trường hợp.
