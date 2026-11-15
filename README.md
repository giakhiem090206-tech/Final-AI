# Dự án cuối kỳ AI — N-Queens, Tank Battle và Kakuro

Dự án gồm ba bài tập Python độc lập. Hướng dẫn dưới đây dùng **Windows PowerShell**; các lệnh chạy từ thư mục `source`.

## 1. Cài đặt một lần

Bạn cần Python 3.9 trở lên. Kiểm tra Python đã cài và terminal đã nhận lệnh:

```powershell
python --version
```

Nếu PowerShell báo không tìm thấy `python` hoặc mở Microsoft Store, hãy cài Python và bật **Add Python to PATH**, sau đó mở lại PowerShell.

Tạo môi trường riêng cho dự án và cài các thư viện cần thiết:

```powershell
cd "đường-dẫn-đến-dự-án\source"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirement.txt
```

Ví dụ với thư mục tải về mặc định:

```powershell
cd "$HOME\Downloads\AI_final_GroupID_StudentID (2)\AI_final_GroupID_StudentID\source"
```

Nếu PowerShell chặn lệnh kích hoạt môi trường, chạy lệnh sau **trong cửa sổ PowerShell hiện tại**, rồi kích hoạt lại:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Mỗi lần mở terminal mới, quay lại thư mục `source` và kích hoạt môi trường bằng lệnh trên. Nếu không muốn kích hoạt, có thể chạy chương trình bằng `.\.venv\Scripts\python.exe`.

## 2. Task 1 — N-Queens

### Mở giao diện

```powershell
cd "Task 1"
python main.py ui
```

Trong cửa sổ giao diện:

- Chọn thuật toán ở mục **Algorithm**: **Glucose3 (SAT)**, **Min-Conflicts: random variable** (cách chuẩn, chọn ngẫu nhiên biến đang xung đột) hoặc **Min-Conflicts: most conflicted + tabu** (heuristic đề xuất).
- Đổi **Board size N** (1–32) và, với Min-Conflicts, **Random seed** của phép gán ban đầu bằng các nút **− / +**; nhấn **Solve** để chạy.
- **Nhấn vào ô để tự đặt/bỏ hậu** (phím **C** hoặc nút **Clear board** để xóa). Với Glucose3 (mỗi ô một biến), các hậu đã đặt được đưa vào solver dưới dạng *giả định* (assumptions): solver đặt nốt các hậu còn lại hoặc trả về UNSAT nếu không lời giải nào chứa chúng. Với Min-Conflicts (mỗi hàng một biến), nhấn vào ô sẽ dời hậu của hàng đó, và tìm kiếm bắt đầu từ thế cờ bạn đặt.
- Rê chuột lên một ô để xem biến logic `x = rN + c + 1` của ô, các ô nó tấn công và số mệnh đề CNF chứa nó. Với Glucose3, mục **CNF clauses** cho biết số mệnh đề của từng loại ràng buộc.
- Với Min-Conflicts, quá trình tìm kiếm được phát lại từng bước: hậu bị tấn công tô đỏ, đường đỏ nối các hậu tấn công nhau, hàng sắp sửa tô vàng kèm số xung đột của từng cột, ô xanh là các cột ít xung đột nhất. Biểu đồ **Attacking pairs per step** cho thấy số cặp tấn công sau mỗi bước; nhấn hoặc kéo trên biểu đồ để tua. Bảng kết quả so sánh số bước với cách chọn biến còn lại trên **cùng seed**.
- Phím tắt (ghi ở thanh dưới cùng cửa sổ): **Enter** giải, **Space** phát/dừng, **← / →** từng bước, **Home / End** về đầu/cuối, **↑ / ↓** đổi N, **1 / 2 / 3** hoặc **Tab** chọn thuật toán, **R** đổi seed, **Esc** đóng cửa sổ.
- N=2 và N=3 không có lời giải: Glucose3 trả về UNSAT, còn Min-Conflicts dừng sau 50 lần khởi động lại.

### Chạy bằng dòng lệnh

```powershell
python main.py sat --n 8
python main.py minconflicts --n 8 --selector tabu --seed 0
```

Chạy các thí nghiệm theo yêu cầu đề bài; kết quả được lưu trong thư mục `Task 1/results/`:

```powershell
python main.py experiment-sat
python main.py experiment-minconflicts
```

## 3. Task 2 — Tank Battle

Từ thư mục `source`, mở `Task 2`. Nếu terminal vẫn đang ở `Task 1`, chạy `cd ..` để quay về `source` trước.

```powershell
cd ..
cd "Task 2"
python main.py
```

Lệnh trên mở menu để chọn người chơi và bản đồ. Một số lệnh khác:

```powershell
python main.py --list
python main.py --p1 "Heuristic Alpha-Beta" --p2 plugins/example_function_agent.py --map Bunkers
python run_experiments.py
```

Trong trận, người chơi điều khiển xe bằng **WASD** hoặc phím mũi tên, **Space** để bắn và **X** để đứng yên. Nút trên màn hình dùng để tạm dừng, đi từng bước, đổi tốc độ, chơi lại hoặc về menu.

## 4. Task 3 — Kakuro

Từ thư mục `source`, mở `Task 3`. Nếu terminal vẫn đang ở một thư mục Task, chạy `cd ..` để quay về `source` trước.

```powershell
cd ..
cd "Task 3"
python main.py
```

Giao diện cho phép xem bộ giải từng bước. Để giải bảng Complex ngay trong terminal:

```powershell
python main.py --solve "Complex (9x9)"
python run_evaluation.py
```

Trong giao diện, **Space** chạy/tạm dừng; **← / →** đi từng bước; **↑ / ↓** chuyển lựa chọn; **M** bật/tắt bản đồ nhiệt; **Esc** đóng cửa sổ.

## 5. Notebook và kết quả

Mở notebook của từng bài bằng Jupyter:

```powershell
cd ..
python -m notebook
```

Sau đó chọn `Task 1/task1.ipynb`, `Task 2/task2.ipynb` hoặc `Task 3/task3.ipynb` trong trình duyệt. Các kết quả thí nghiệm nằm trong thư mục `results/` tương ứng của từng bài.

## 6. Lỗi thường gặp

- **`python` không chạy:** cài Python, bật **Add Python to PATH**, rồi mở lại terminal.
- **`No module named pygame` hoặc `pysat`:** từ `source`, kích hoạt `.venv` và chạy `python -m pip install -r requirement.txt`.
- **Không mở được cửa sổ:** chạy từ máy tính có môi trường đồ họa; phiên terminal từ xa/headless không thể hiện giao diện PyGame.
- **Không tìm thấy `main.py`:** kiểm tra đang ở đúng thư mục bài (`Task 1`, `Task 2` hoặc `Task 3`) trước khi chạy lệnh.

## Cấu trúc thư mục

```text
source/
├── requirement.txt
├── Task 1/   # N-Queens: CNF/Glucose3, Min-Conflicts và giao diện PyGame
├── Task 2/   # Tank Battle: Minimax, Alpha-Beta và giao diện PyGame
└── Task 3/   # Kakuro: CSP, lan truyền ràng buộc và giao diện PyGame
```
