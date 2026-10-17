# HƯỚNG DẪN & LƯU Ý KHI TRIỂN KHAI DATABASE VÀ MODEL AI THẬT
**Dự án:** AgroScan — AI-assisted Goods Inspection Desktop Application  
**Tài liệu tham khảo kỹ thuật khi nâng cấp từ Prototype (Phase 2) lên Production (Phase C & Phase 3)**

---

## TÓM TẮT NHANH: HIỆN TẠI (PROTOTYPE) VS TRIỂN KHAI THẬT (PRODUCTION)

* **Lưu trữ dữ liệu phiên kiểm định (Inspection Data):**
  * *Hiện tại:* Lưu tạm trên RAM qua Python Dataclass (`MainWindow._current_session`, tắt app là mất hết dữ liệu).
  * *Khi deploy thật:* Lưu vĩnh viễn vào SQLite database (`agroscan.db`) qua tầng Repository (`InspectionRepository`).
* **Mô hình Trí tuệ Nhân tạo (AI Model Engine):**
  * *Hiện tại:* Giả lập dữ liệu ngẫu nhiên (Mock generator sinh ngẫu nhiên số lượng khuyết tật, score, nhãn DEMO MODE).
  * *Khi deploy thật:* Tích hợp Model Computer Vision thật (YOLOv8 / YOLOv11 qua ONNX Runtime để phát hiện khuyết tật, sâu bệnh, kích cỡ).
* **Luồng xử lý suy luận (Thread & Concurrency):**
  * *Hiện tại:* Chạy timer giả lập giả vờ delay 1-2 giây ngay trên luồng chính.
  * *Khi deploy thật:* Bắt buộc chạy trên Worker Thread nền (`QRunnable` / `QThreadPool`) để AI tính toán không làm đơ giao diện (freeze GUI).
* **Quản lý tệp hình ảnh (Image Storage):**
  * *Hiện tại:* Chỉ đọc đường dẫn file ảnh trực tiếp từ máy người dùng qua `QPixmap`.
  * *Khi deploy thật:* Copy ảnh vào kho lưu trữ nội bộ (`data/storage/{session_id}/`), kiểm tra mã băm SHA-256 chống trùng lặp, chỉ lưu đường dẫn tương đối (Relative Path) vào database.
* **Lịch sử & Báo cáo (History & Analytics):**
  * *Hiện tại:* Danh sách mẫu (Mock 8-10 dòng) + gom danh sách RAM trong phiên làm việc.
  * *Khi deploy thật:* Truy vấn SQL thực tế (phân trang, lọc theo ngày tháng, mã lô hàng, xuất báo cáo PDF/Excel thật qua ReportLab/OpenPyXL).
* **Kiểm định viên & Phân quyền (Inspector & Audit):**
  * *Hiện tại:* Nhập tên tự do trên giao diện New Inspection.
  * *Khi deploy thật:* Đăng nhập người dùng (User Authentication), phân quyền (Inspector / Supervisor / Admin), lưu vết lịch sử duyệt (Audit Trail).

---

## 1. TỔNG QUAN KIẾN TRÚC MỤC TIÊU

Hiện tại trong **Phase 2**, hệ thống đang hoạt động ở chế độ **In-Memory** (dữ liệu lưu trên RAM thông qua các dataclass tại [`src/agroscan/models/inspection_models.py`](file:///d:/Github%20Clone/AgroScan/src/agroscan/models/inspection_models.py) và thuật toán AI là giả lập).

Khi chuyển sang hệ thống thật, kiến trúc cần tuân thủ mô hình **Clean Architecture / Layered Architecture**:

```
┌─────────────────────────────────────────────────────────────┐
│                       UI Layer (PySide6)                    │
│      MainWindow, Pages (NewInspectionPage, ImageInput, ...) │
└──────────────────────────────┬──────────────────────────────┘
                               │ Signals / Slots (Không chặn GUI)
┌──────────────────────────────▼──────────────────────────────┐
│                    Service & Worker Layer                   │
│   InferenceWorker (QRunnable), InspectionService, Exporter  │
└──────────────┬───────────────────────────────┬──────────────┘
               │                               │
┌──────────────▼──────────────┐ ┌──────────────▼──────────────┐
│      AI Engine Layer        │ │   Database / Storage Layer  │
│  ONNXRuntime / YOLO Engine  │ │  SQLite Repository / Disk   │
│  (Preprocessing / Postproc) │ │  (Session, Defect, History) │
└─────────────────────────────┘ └─────────────────────────────┘
```

---

## 2. LƯU Ý KHI TRIỂN KHAI CƠ SỞ DỮ LIỆU (DATABASE) THẬT

### 2.1. Lựa chọn Công nghệ
* **Khuyến nghị cho Desktop App:** Sử dụng **SQLite** kết hợp thư viện ORM nhẹ (như **SQLAlchemy** hoặc truy vấn qua **Repository Pattern** với `sqlite3` thuần).
* **Lý do:** SQLite là tệp cục bộ (`agroscan.db`), không cần người dùng cài đặt máy chủ database (PostgreSQL/MySQL), phù hợp với máy trạm kiểm định độc lập tại kho bãi / cửa khẩu.

---

### 2.2. Xử lý Đa luồng (Threading & SQLite Concurrency) — RẤT QUAN TRỌNG
> [!WARNING]
> Mặc định, một SQLite connection khởi tạo ở Thread A **không được phép** sử dụng ở Thread B. Nếu gọi từ luồng nền, Python sẽ ném ngoại lệ:
> `sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that same thread.`

* **Giải pháp 1 (Khuyên dùng):** Áp dụng mô hình **Connection-per-Thread** hoặc **Context Manager** mở và đóng connection trong từng tác vụ nền:
  ```python
  # Ví dụ trong Worker Thread:
  with sqlite3.connect("agroscan.db") as conn:
      repo = InspectionRepository(conn)
      repo.save_inspection_record(record)
  ```
* **Giải pháp 2:** Bật chế độ đa luồng với WAL (Write-Ahead Logging) và timeout:
  ```python
  conn = sqlite3.connect("agroscan.db", check_same_thread=False, timeout=30.0)
  conn.execute("PRAGMA journal_mode=WAL;")
  conn.execute("PRAGMA foreign_keys = ON;")
  ```
  * `PRAGMA foreign_keys = ON;`: Bắt buộc kích hoạt vì SQLite mặc định **tắt** ràng buộc khóa ngoại.
  * `journal_mode=WAL`: Cho phép nhiều luồng đọc đồng thời trong khi một luồng đang ghi, tránh tình trạng "database is locked".

---

### 2.3. Quy tắc Lưu trữ Hình ảnh (Images Storage)
> [!CAUTION]
> **Tuyệt đối không lưu tệp ảnh trực tiếp dưới dạng BLOB vào trong SQLite database.**
> Việc lưu hàng ngàn ảnh kích thước lớn (2MB - 10MB) vào DB sẽ làm database phình to hàng chục GB, gây nghẽn I/O, giảm tốc độ truy vấn và nguy cơ hỏng tệp cơ sở dữ liệu.

* **Cách làm chuẩn:**
  1. Khi người dùng tải ảnh lên, phần mềm copy ảnh vào thư mục lưu trữ cục bộ có cấu trúc, ví dụ:  
     `./data/storage/inspections/{session_id}/raw_{uuid}.jpg`  
     `./data/storage/inspections/{session_id}/annotated_{uuid}.jpg`
  2. Trong Database chỉ lưu:
     - `file_path`: Đường dẫn tương đối (Relative Path) tính từ thư mục gốc dữ liệu (tránh lưu tuyệt đối vì nếu copy app sang máy khác hoặc đổi ổ đĩa sẽ bị hỏng link).
     - `file_size`: Kích thước tệp (bytes).
     - `file_hash`: Mã băm SHA-256 để kiểm tra tính toàn vẹn (chống giả mạo hoặc trùng lặp ảnh).
     - `width`, `height`: Kích thước ảnh gốc.

---

### 2.4. Thiết kế Bảng & Khóa ngoại (Schema Mapping)
Thiết kế bảng tương ứng 1:1 với các model hiện tại trong [`src/agroscan/models/inspection_models.py`](file:///d:/Github%20Clone/AgroScan/src/agroscan/models/inspection_models.py):

| Bảng | Model tương ứng | Lưu ý khóa chính / ràng buộc |
| :--- | :--- | :--- |
| `inspection_sessions` | [`InspectionSession`](file:///d:/Github%20Clone/AgroScan/src/agroscan/models/inspection_models.py#L32) | `session_id` (PK, TEXT), `batch_number` (INDEXED), `status`, `created_at` |
| `inspection_images` | (Quản lý ảnh) | `id` (PK), `session_id` (FK $\rightarrow$ `inspection_sessions.session_id`), `raw_path`, `annotated_path`, `sha256` |
| `detection_boxes` | [`BoundingBox`](file:///d:/Github%20Clone/AgroScan/src/agroscan/models/inspection_models.py#L44) | `id` (PK), `image_id` (FK), `label`, `confidence`, `x_min`, `y_min`, `x_max`, `y_max` |
| `quality_assessments` | [`QualityAssessmentResult`](file:///d:/Github%20Clone/AgroScan/src/agroscan/models/inspection_models.py#L60) | `session_id` (PK/FK), `overall_grade`, `freshness_score`, `defect_ratio` |
| `inspection_records` | [`InspectionRecord`](file:///d:/Github%20Clone/AgroScan/src/agroscan/models/inspection_models.py#L71) | Bảng lịch sử chính thức, lưu quyết định của Inspector (`ACCEPTED`/`REJECTED`), `reviewer_notes`, `confirmed_at` |

---

### 2.5. Cơ chế Migration (Nâng cấp cấu trúc DB)
* Khi phát hành phiên bản mới có thêm cột hoặc bảng, không được xóa database cũ của người dùng.
* Nên sử dụng **Alembic** hoặc một bảng `schema_versions` đơn giản để tự động chạy các script `ALTER TABLE` khi khởi động ứng dụng.

---

## 3. LƯU Ý KHI TRIỂN KHAI MODEL AI THẬT

### 3.1. Tuyệt đối không chạy Model Inference trên Main Thread (GUI Thread)
> [!IMPORTANT]
> Việc suy luận mạng nơ-ron (Object Detection, Quality Classification) thường mất từ **100ms đến vài giây** tùy phần cứng. Nếu gọi hàm dự đoán trực tiếp trong sự kiện bấm nút của PySide6, toàn bộ giao diện sẽ bị **"Not Responding" (treo/đơ)**.

* **Kiến trúc xử lý:**
  * Kế thừa [`QRunnable`](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QRunnable.html) hoặc [`QThread`](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QThread.html) để tạo một `InferenceWorker`.
  * Giao tiếp giữa luồng tính toán AI và giao diện chỉ thông qua **PySide6 Signals**:
    - `progress_updated = Signal(int)`: Cập nhật thanh tiến trình % cho người dùng thấy.
    - `inference_finished = Signal(DetectionResult, QualityAssessmentResult)`: Bắn kết quả về khi hoàn thành.
    - `error_occurred = Signal(str)`: Báo lỗi nếu gặp sự cố.

---

### 3.2. Lựa chọn Runtime & Tối ưu hóa Thư viện
* **Vấn đề của PyTorch gốc:** Cài đặt `torch` và `torchvision` thường tiêu tốn từ **2GB đến 5GB** dung lượng ổ cứng, gây khó khăn lớn khi đóng gói bộ cài (Installer/PyInstaller) cho người dùng cuối.
* **Giải pháp chuẩn công nghiệp:**
  1. Huấn luyện model (YOLOv8, YOLOv11, EfficientNet...) trên môi trường server/GPU bằng PyTorch.
  2. Xuất mô hình sang định dạng **ONNX** (`.onnx`) hoặc **TensorRT** (nếu máy trạm có card NVIDIA).
  3. Ứng dụng Desktop chỉ cần cài đặt **`onnxruntime`** (bản CPU chỉ khoảng ~20MB, hoặc `onnxruntime-directml` hỗ trợ tăng tốc GPU trên mọi card Windows mà không cần CUDA phức tạp).

---

### 3.3. Xử lý Tọa độ Bounding Box & Hiển thị trên Qt Canvas
* **Quy chuẩn tọa độ:** Model AI thường nhận ảnh kích thước cố định (ví dụ $640 \times 640$) và trả về tọa độ chuẩn hóa $[0.0, 1.0]$ hoặc tọa độ trên kích thước $640 \times 640$.
* **Khi hiển thị lên UI:**
  * Phải có bước **Post-processing** để tính toán bù tỷ lệ (Letterbox offset & scale ratio) chuyển tọa độ bbox về tọa độ pixel thực tế của ảnh gốc:
    $$x_{\text{real}} = \frac{x_{\text{model}} - \text{pad}_x}{\text{scale}}$$
  * Lưu vào model [`BoundingBox`](file:///d:/Github%20Clone/AgroScan/src/agroscan/models/inspection_models.py#L44-L52) với tọa độ pixel ảnh gốc.
  * Khi hiển thị trên widget xem ảnh ([`QGraphicsView`](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QGraphicsView.html) hoặc `QPainter`), Qt sẽ tự scale đồng bộ khi người dùng phóng to/thu nhỏ (Zoom/Pan).

---

### 3.4. Cơ chế Model Warmup (Làm nóng mô hình)
* Lần suy luận đầu tiên sau khi load model thường bị trễ (Cold Start Latency) do bộ khởi tạo thư viện và cấp phát bộ nhớ RAM/VRAM.
* **Kỹ thuật:** Khi ứng dụng khởi động hoặc ở màn hình Splash Screen, truyền một tensor giả (Zero Tensor kích thước $1 \times 3 \times 640 \times 640$) qua model một lần để "làm nóng", giúp lần quét thật đầu tiên của người dùng phản hồi tức thì.

---

### 3.5. Xử lý Lỗi & Dự phòng (Fault Tolerance)
Cần có bẫy lỗi đầy đủ trong quá trình inference:
1. **Ảnh hỏng / Định dạng lạ:** Kiểm tra bằng thư viện `Pillow` hoặc `OpenCV` trước khi đưa vào pipeline (`verify()`, kiểm tra chiều rộng/chiều cao > 0).
2. **Hết bộ nhớ (Out Of Memory - OOM):** Bắt ngoại lệ và giải phóng cache, trả thông báo nhẹ nhàng cho người dùng thay vì crash đột ngột cả ứng dụng.
3. **Ảnh quá mờ hoặc thiếu sáng:** Nên có bộ lọc kiểm tra độ sắc nét (Laplacian variance) trước khi gọi AI để cảnh báo người dùng chụp lại ảnh rõ hơn.

---

## 4. CHECKLIST KIỂM TRA TRƯỚC KHI TÍCH HỢP VÀO AGROSCAN

- [ ] **Data Consistency:** Đã bật `PRAGMA foreign_keys = ON;` và `PRAGMA journal_mode=WAL;` cho SQLite.
- [ ] **Image Path:** Đường dẫn ảnh lưu trong DB là đường dẫn tương đối (Relative Path), ảnh gốc được sao lưu an toàn tại thư mục riêng.
- [ ] **Async Execution:** Hàm gọi Model và hàm ghi Database lớn được tách biệt hoàn toàn khỏi luồng chính (Main GUI Thread).
- [ ] **Model Engine:** Đã chuyển đổi trọng số sang định dạng nhẹ (`.onnx`), không phụ thuộc vào bộ cài đặt PyTorch cồng kềnh trên máy người dùng.
- [ ] **Data Model:** Các trường dữ liệu trả về từ AI map chính xác vào các thuộc tính của [`DetectionResult`](file:///d:/Github%20Clone/AgroScan/src/agroscan/models/inspection_models.py#L54) và [`QualityAssessmentResult`](file:///d:/Github%20Clone/AgroScan/src/agroscan/models/inspection_models.py#L60).
- [ ] **Audit Trail:** Mọi quyết định từ chối (`REJECTED`) hoặc duyệt có điều kiện (`CONDITIONAL`) đều bắt buộc lưu kèm ghi chú của kiểm định viên (`notes`) và nhãn thời gian (`timestamp`).
