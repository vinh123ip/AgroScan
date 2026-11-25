# AgroScan — Hướng dẫn Cài đặt, Database v1.2 & Kiểm thử Toàn diện

> **Tài liệu hợp nhất duy nhất** hướng dẫn cài đặt môi trường, khởi tạo cơ sở dữ liệu PostgreSQL Design v1.2 (15 bảng & 5 seed mẫu), chạy ứng dụng ở chế độ vận hành/demo, kiểm thử thủ công, kịch bản trình diễn bảo vệ đồ án và chạy bộ kiểm thử tự động.

---

## 1. Tổng quan Kiến trúc Hệ thống

AgroScan là ứng dụng Desktop Windows kiểm tra chất lượng nông sản & thủy sản theo quy trình 12 bước:

- **Desktop Client (`src/agroscan/`):** Python 3.13 + PySide6 + QSS, chuyển đổi ngôn ngữ động **EN / VI** (`i18n.py`) và phân quyền 4 vai trò (**Admin**, **Inspector**, **Reviewer**, **Manager**) qua `navigation.py`.
- **Thị giác máy tính Edge (`yolo_engine.py`):** YOLOv8 ONNX (`onnxruntime`) chạy trên `QThread` nền (`YoloInferenceThread`) kèm `CentroidTracker` chống đếm trùng.
- **Đánh giá nghiệp vụ (`rule_engine.py`):** Python tính toán deterministic `PASS / FAIL / NEEDS_REVIEW` theo tiêu chí lưu trong DB (`gt`/`ge` & cờ loại trừ `exclusion`).
- **Phân tích chuyên sâu VLM (`vlm_client.py` ↔ `server/qwen_service.py`):** HTTP REST JSON Schema 1.0 (`docs/api/vlm_analysis.schema.json`), kết nối LM Studio (`127.0.0.1:1234`) hoặc bridge mặc định (`127.0.0.1:8000`).
- **Cơ sở dữ liệu PostgreSQL v1.2 (`scripts/db_v1_2/` & `postgres_repository.py`):** Schema `agroscan` gồm **15 bảng, 19 khóa ngoại, 3 views** (`current_selections`, `latest_lot_decisions`, `box_rule_counts`) và cơ chế bảo toàn ảnh gốc SHA-256 trước khi vẽ bounding box (`evidence_service.py`).
- **Báo cáo (`pdf_report_service.py`):** Xuất chứng nhận PDF từng phiên (`reportlab`) và file Excel 3-sheet (`openpyxl`: `Order Summary`, `Inspection Sessions`, `Evidence Integrity`) luôn chuẩn tiếng Anh.

---

## 2. Cài đặt Môi trường từ đầu (Thành viên mới)

Từ thư mục mã nguồn `E:\AgroScan_Project\AgroScan` trên Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/export_yolo_onnx.py
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

Mở `.env` và kiểm tra thông số kết nối PostgreSQL khớp với máy của bạn (`AGROSCAN_DB_HOST`, `AGROSCAN_DB_PORT`, `AGROSCAN_DB_NAME`, `AGROSCAN_DB_USER`, `AGROSCAN_DB_PASSWORD`). Mặc định dev dùng database `agroscan_dev` và tài khoản `agro_user`.

---

## 3. Khởi tạo PostgreSQL Design v1.2 & 5 Seed mẫu

### 3.1. Nạp SQL qua pgAdmin 4 (chạy 1 lần khi tạo mới DB)

1. Mở **Query Tool** tại database đích (ví dụ `agroscan_dev`) bằng tài khoản quản trị PostgreSQL (`postgres`). Có thể kiểm tra nhanh bằng `SELECT current_database(), current_user;`.
2. Mở và chạy toàn bộ [`scripts/db_v1_2/01_schema.sql`](../scripts/db_v1_2/01_schema.sql) — tạo schema `agroscan` gồm 15 bảng, 19 khóa ngoại, 3 views và các trigger/hàm kiểm tra tính toàn vẹn. *(Nếu schema đã tồn tại, script dừng để giữ dữ liệu; nếu Query Tool báo transaction lỗi, chạy `ROLLBACK;` trước câu lệnh tiếp theo).*
3. Mở và chạy toàn bộ [`scripts/db_v1_2/02_seed.sql`](../scripts/db_v1_2/02_seed.sql) — nạp 5 lô mẫu `DEMO-V12-01` → `DEMO-V12-05` và 5 tài khoản lịch sử (dùng ID âm cố định; chạy lại sẽ tự bỏ qua nếu fixture đã nạp).
4. Mở và chạy [`scripts/db_v1_2/03_grant_app.sql`](../scripts/db_v1_2/03_grant_app.sql) để cấp quyền cho tài khoản ứng dụng `agro_user` (sửa tên role trong file nếu `.env` dùng role khác).
5. Refresh **Schemas → agroscan → Tables** trong pgAdmin 4 để xác nhận đủ 15 bảng.

### 3.2. Tạo tài khoản Admin đầu tiên trên Desktop

5 tài khoản trong seed (`demo12.*`) chỉ là danh tính lịch sử không có mật khẩu đăng nhập (`!`). Tạo tài khoản đăng nhập ứng dụng từ PowerShell:

```powershell
python run.py --create-admin TEN_DANG_NHAP
python run.py
```

### 3.3. Chi tiết 5 Lô Seed mẫu & Truy vấn đối chiếu nhanh

| Mã đơn | Sản phẩm | Điểm cần kiểm chứng theo Database Design v1.2 |
|---|---|---|
| `DEMO-V12-01` | Apple (Táo) | Nhập 3 thùng. Profile đã gắn, kế hoạch lấy mẫu **chưa khóa** (`active_revision = NULL`). |
| `DEMO-V12-02` | Orange (Cam) | Bổ sung thùng thứ 4 (`04/04`), chuyển từ revision 1 → 2. Vị trí 1 ở revision 2 thay thùng không tiếp cận được qua `sample_selections.replaces_id`, giữ lịch sử & lý do. Hỗ trợ scan token `00000000-0000-4000-8000-000000120024`. |
| `DEMO-V12-03` | Banana (Chuối) | Attempt `INS--120311` đang ở trạng thái `draft`, có sẵn 1 batch, ảnh đếm và quan sát. |
| `DEMO-V12-04` | Shrimp (Tôm) | Attempt `INS--120411` ở trạng thái `submitted` chờ Reviewer (2 batch, 2 ảnh đếm, 1 ảnh bổ sung, 4 vật thể). Thùng `AGS:DEMO-V12-04-02/03` chưa kiểm, sẵn sàng test luồng kiểm mới. |
| `DEMO-V12-05` | Squid (Mực) | Thùng 1 có tái kiểm (`INS--120511` → `INS--120512` qua `previous_id`), thùng 2 không phù hợp. Với `d = 1, Ac = 0, Re = 1`, khuyến nghị là `reject`, nhưng Reviewer ký RSA-PSS/SHA-256 `approve` theo ngoại lệ có `override_reason`. |

> **Phân biệt thay thùng vs Tái kiểm:** Thùng chưa kiểm nhưng không tiếp cận được → thay thùng (`sample_selections.replaces_id`). Thùng đã kiểm nhưng bằng chứng chưa đủ → tái kiểm (`inspections.previous_id`).

**Truy vấn SQL đối chiếu 5 lô mẫu trong Query Tool:**

```sql
SELECT o.order_code, p.name AS product, l.declared_boxes,
       (l.plan_snapshot->>'active_version')::int AS active_revision,
       (SELECT count(*) FROM agroscan.current_selections s
        JOIN agroscan.boxes b ON b.id = s.box_id WHERE b.lot_id = l.id) AS active_slots,
       d.version AS decision_version, d.outcome
FROM agroscan.orders o
JOIN agroscan.lots l ON l.order_id = o.id
JOIN agroscan.inspection_profiles ip ON ip.id = l.profile_id
JOIN agroscan.products p ON p.id = ip.product_id
LEFT JOIN agroscan.latest_lot_decisions d ON d.lot_id = l.id
WHERE o.order_code LIKE 'DEMO-V12-%'
ORDER BY o.order_code;
```

**Đọc nội dung bản kê đã ký của lô mực (`DEMO-V12-05`):**

```sql
SELECT manifest->>'d' AS nonconforming_boxes, manifest->>'Ac' AS ac,
       manifest->>'Re' AS re, manifest->>'recommendation' AS recommendation,
       manifest->>'outcome' AS signed_outcome, manifest->>'override_reason' AS reason
FROM (
    SELECT convert_from(d.manifest_bytes, 'UTF8')::jsonb AS manifest
    FROM agroscan.latest_lot_decisions d
    JOIN agroscan.lots l ON l.id = d.lot_id
    JOIN agroscan.orders o ON o.id = l.order_id
    WHERE o.order_code = 'DEMO-V12-05'
) signed;
```

---

## 4. Các chế độ khởi chạy Ứng dụng

- **Chế độ Vận hành PostgreSQL v1.2:**
  ```powershell
  python run.py
  ```
  Launcher tự chọn `.venv`, đọc `.env` để kết nối PostgreSQL `agroscan_dev` và khởi chạy VLM bridge tại `127.0.0.1:8000` (nếu cấu hình `ai_url` mặc định). Nếu mở LM Studio tại cổng `1234`, bridge tự động chuyển ảnh tới model Qwen-VL thật.
- **Chế độ Demo trên RAM (không cần DB):**
  ```powershell
  python run.py --demo
  ```
  Sử dụng `MockRepository` trên RAM với 3 tài khoản mẫu:
  - **Inspector:** `inspector` / `inspector123`
  - **Reviewer:** `reviewer` / `reviewer123`
  - **Admin:** `admin` / `admin123`

---

## 5. Kiểm thử Thủ công (Manual QA)

### 5.1. Kiểm thử PostgreSQL v1.2 trực tiếp (`python run.py`)

1. Đăng nhập bằng tài khoản Admin vừa tạo qua `--create-admin`.
2. Vào **Box Intake**: tra `AGS:DEMO-V12-02-04/04` và thử nhập UUID token `00000000-0000-4000-8000-000000120024` → phải trỏ về cùng thùng `04/04` của đơn Cam.
3. Vào **Data Import**: kiểm tra 5 đơn `DEMO-V12-01` → `DEMO-V12-05`.
4. Vào **Dashboard**: kiểm tra lô chưa khóa (`DEMO-V12-01`) hiển thị dấu gạch ngang; lô Mực (`DEMO-V12-05`) hiển thị 2 thùng đã duyệt và quyết định ngoại lệ `approve`.
5. Vào **Users**: tạo 1 tài khoản `Inspector` và 1 tài khoản `Reviewer`.
6. Đăng nhập **Inspector**, mở thùng `AGS:DEMO-V12-04-02/03`, nạp ảnh bằng **Import original** hoặc **Simulation Feed**, chụp ít nhất 1 ảnh có detector phát hiện vật thể, xác nhận độ phủ toàn thùng (**Confirm whole-box coverage**) khi nộp.
7. Đăng nhập **Reviewer** độc lập (khác người nộp), vào **Review Queue** để kiểm tra ảnh, SHA-256 và duyệt; sau đó mở **Inspection History** thêm **Attributed Note** và kiểm tra lại rằng bản kê đã ký của lô `DEMO-V12-05` không bị thay đổi.

### 5.2. Bộ ca kiểm thử thủ công 12 chức năng (TC01 → TC12 trên `python run.py --demo`)

| Mã | Thao tác chính | Kết quả mong đợi |
|---|---|---|
| **TC01 · Đăng nhập** | Nhập sai mật khẩu Inspector, sau đó đăng nhập đúng `inspector` / `inspector123`. | Lần đầu báo lỗi inline; lần sau vào đúng giao diện Inspector kèm session token. |
| **TC02 · Tra mã QR** | Trong **Box Intake**, nhập `AGS:NOPE999-01/10` rồi nhập `AGS:DH00123-07/10`. | Mã đầu báo `ERR_ORDER_NOT_FOUND`; mã sau hiện đơn BANANA, số thùng và bảng tiêu chí. |
| **TC03 · Chụp bằng chứng** | **Start Inspection → Simulation Feed → Fresh Bananas → Capture Evidence**. | Hiển thị preview bounding box ONNX, đếm đối tượng và ảnh thu nhỏ trong `EvidenceStrip`. |
| **TC04 · Đánh giá & Gửi** | **Finish Inspection → Submit for Review**. Thử thêm thùng khác với **Rotten Bananas**. | Ca tươi đề xuất `PASS`, ca thối đề xuất `FAIL`. Phiên sau khi gửi xuất hiện ở **Review Queue**. |
| **TC05 · Kiểm duyệt** | Đăng nhập Reviewer, mở phiên vừa gửi, bấm ảnh xem SHA-256, chọn **Pass / Fail / Re-inspect**. | Ảnh hiển thị trạng thái `Verified`, phiên rời hàng đợi, ca `Re-inspect` cho phép kiểm lại. |
| **TC06 · Lịch sử & Song ngữ** | Chuyển **EN / VI** trong lúc thao tác và mở **Inspection History**. | Giao diện đổi ngôn ngữ tức thì mà không mất phiên đang mở; lịch sử tách biệt khuyến nghị máy & quyết định người duyệt. |
| **TC07 · Xuất PDF / Excel** | Xuất PDF phiên từ History; vào **Reports** lọc ngày/sản phẩm rồi xuất PDF & Excel. | PDF mở được có ảnh + hash; Excel có đủ 3 sheets **Order Summary**, **Inspection Sessions**, **Evidence Integrity** chuẩn tiếng Anh. |
| **TC08 · Nhập đơn CSV/XLSX** | Admin mở **Data Import**, nạp file có cả dòng hợp lệ, product code lạ và `total_boxes=0`. | Preview chỉ rõ dòng lỗi, nút **Import Valid Orders to DB** chỉ lưu các đơn hợp lệ. |
| **TC09 · Tiêu chí & RBAC** | Admin mở **Catalog**, thử nhập trùng tên lỗi rồi sửa hợp lệ và lưu; so sánh menu với Inspector. | Báo xung đột trùng lớp; lưu thành công đồng bộ sang Box Intake; Inspector không thấy menu Admin. |
| **TC10 · Quản lý Users** | Admin vào **Users**, tạo tài khoản thử, đăng nhập thử rồi vô hiệu hóa tài khoản đó. | Tài khoản hoạt động đăng nhập được; sau khi vô hiệu hóa bị từ chối đăng nhập. |
| **TC11 · Qwen-VL Deep Analysis** | Sau khi chụp ảnh, bấm **Deep Analysis (Qwen-VL)**. | Panel `VlmResultPanel` hiển thị lỗi chi tiết, OCR nhãn thùng đối chiếu đơn hàng và mức bất định. |
| **TC12 · Camera & Settings** | Admin chọn camera trong **Settings**, bấm **Test All**; thử chế độ thiếu camera. | Có camera thì chụp trực tiếp; thiếu camera thì nút chuyển 1-click sang **Simulation Feed** hoạt động ngay. |

---

## 6. Kịch bản Trình diễn Bảo vệ Đồ án & Dự phòng 1-Click

1. **Chuẩn bị trước giờ demo (2 phút):** Kiểm tra PostgreSQL đã chạy; nếu dùng VLM thật thì bật LM Studio (nạp `Qwen2.5-VL`, Start Local Server cổng `1234`), hoặc dùng bridge mặc định `127.0.0.1:8000` khi `run.py` khởi động.
2. **Dự phòng 1-Click khi thiếu webcam:** Tại **Live Inspection**, chọn **Feed Source → Simulation Feed** (luồng ảnh vẫn chạy qua `YoloEngine` ONNX và băm SHA-256 thật).
3. **3 Kịch bản trình diễn trọng tâm:**
   - **Ca 1 (`PASS`):** `AGS:DH00123-07/10` → *Fresh Bananas* → Capture → Finish (`PASS` vì bruised 5% $\le$ 10%) → Submit.
   - **Ca 2 (`FAIL` critical):** `AGS:DH00123-08/10` → *Rotten Bananas* → Capture → Finish (`FAIL` ngay do `rotten` là critical exclusion) → Submit.
   - **Ca 3 (`Qwen-VL` + `Reviewer` + `PDF/Excel`):** `AGS:DH00123-09/10` → *Bruised Bananas* → Capture → **Deep Analysis (Qwen-VL)** (xem OCR nhãn + uncertainty) → Submit → Đăng nhập Reviewer xem **EvidenceViewerDialog (`SHA-256 Verified`)** & duyệt → Xuất PDF chứng nhận + Excel 3-sheet.

---

## 7. Kiểm thử Tự động (Automated QA) & Đóng gói

Chạy lần lượt 3 lệnh sau từ `E:\AgroScan_Project\AgroScan` (yêu cầu PostgreSQL `agroscan_dev` đang chạy và đã nạp schema + 5 seed mẫu ở mục 3):

```powershell
# 1. Toàn bộ Unit Tests & Integration Tests PostgreSQL v1.2 (tự rollback các ghi thử)
.\.venv\Scripts\python.exe run_tests.py

# 2. Kiểm thử tự động 7 giai đoạn E2E
.\.venv\Scripts\python.exe tests/e2e_walkthrough.py

# 3. Kiểm thử GUI tự động 18 bước (Inspector -> Reviewer -> Admin) ở chế độ headless
.\.venv\Scripts\python.exe tests/autorun.py --headless-check
```

- **Tiêu chí đạt:** `run_tests.py` báo `Failures: 0, Errors: 0, Skipped: 0`; `e2e_walkthrough.py` hoàn tất 7/7 bước; `autorun.py --headless-check` in `AgroScan Auto-Run headless check passed.`.
- **Đóng gói EXE (khi cần phát hành):** Script [`scripts/build_exe.bat`](../scripts/build_exe.bat) gọi PyInstaller với `agroscan.spec` để xuất ra `dist\AgroScan\AgroScan.exe` (lưu ý: tệp `agroscan.spec` cần được tạo trước bằng PyInstaller trên máy đóng gói nếu chưa có sẵn trong repo).
