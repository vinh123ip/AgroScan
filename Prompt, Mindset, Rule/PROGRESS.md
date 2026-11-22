# PROGRESS.md — Tiến độ thực tế của AgroScan

**Quy tắc cập nhật:** một hạng mục chỉ được đánh dấu "Hoàn thành" khi có **bằng chứng** (tên test đã chạy và kết quả, hoặc hành vi đã kiểm tra thủ công kèm ngày). Có mã nguồn chưa đủ.

AI cập nhật tệp này sau mỗi nhiệm vụ thuộc roadmap và ghi rõ phần nào chưa kiểm chứng.

**Cập nhật lần cuối:** 14/11/2026

## Trạng thái

- ⬜ Chưa xác minh (chưa ai kiểm tra repo)
- 🟡 Đang làm
- 🟢 Hoàn thành (có bằng chứng)
- 🔴 Bị chặn

## Bảng tiến độ theo 12 bước của sơ đồ hệ thống

| # | Hạng mục (theo sơ đồ) | Trạng thái | Bằng chứng (tệp/hàm/test/ngày) | Ghi chú |
|---|---|---|---|---|
| 1 | Chuẩn bị và nhập dữ liệu ban đầu (Excel/CSV chính, PDF giao Qwen-VL) | ⬜ | Chưa có service import Excel/CSV hay trích xuất PDF; `PageKey.DATA_IMPORT` đang trỏ `PlaceholderPage` (`main_window.py`). Đã có dữ liệu seed mẫu trong `scripts/init_db.sql` | D-029; làm ở T3.4 |
| 2 | Quản lý danh mục, tiêu chí kiểm định, người dùng/phân quyền, cấu hình hệ thống | 🟡 | `CatalogPage` + `catalog_validation.py`, `LoginDialog` + `MockAuthService` (HMAC-SHA256), `navigation.py` (3 vai trò D-032), `SettingsPage` + `AppSettings` + `connection_checker.py` (pass `test_sprint2_checklist.py` & `test_task_3_2_5_7.py`). `PageKey.USERS` còn là `PlaceholderPage` | D-024, D-027, D-028, D-032 |
| 3 | Tiếp nhận đơn hàng (quét barcode QR, 1 mã = 1 hộp = 1 phiên) | 🟢 | `BoxIntakePage` (quét `AGS:...`, debounce 350ms, 7 mã lỗi, tìm đơn, chặn mở trùng phiên D-021), `qr_encoder.py` + `QrLabelDialog`, `PostgresRepository.resolve_box` & `create_session` (pass `test_task_3_2_5_7.py` & `test_postgres_repository.py`, 13/11/2026). *Chưa kiểm chứng:* máy quét USB vật lý | D-019, D-020, D-021 |
| 4 | Kiểm tra realtime: camera + YOLO chuyên hóa + ByteTrack + ảnh tĩnh bằng chứng | 🟢 | `LiveInspectionPage` (`QCamera` + `QImageCapture` + Simulation Feed D-031), `YoloEngine` + `YoloInferenceThread` (`QThread` ONNX Runtime) + `CentroidTracker` (D-025) trong `yolo_engine.py`, `evidence_service.py` (lưu ảnh gốc & băm SHA-256 trước khi vẽ box), `scripts/export_yolo_onnx.py` + `models/weights/*.onnx` (pass `tests/test_week1_evidence_and_yolo.py` & `tests/test_simulation_feed.py`, 14/11/2026). *Chưa kiểm chứng:* fine-tune trọng số trên ảnh chụp thực tế tại phòng thi | D-024, D-025, D-026 |
| 5 | Phân tích chuyên sâu Qwen-VL (bấm nút, HTTP REST từ máy chủ) | 🟡 | Đã có `VlmResultPanel` + `vlm_models.py` + `docs/api/vlm_analysis.schema.json` (pass schema tests trong `test_sprint2_checklist.py`, 04/11/2026). Dữ liệu phân tích vẫn giả lập qua `mock_ai.simulate_deep_analysis` | D-017; server REST làm ở T2.5 |
| 6 | Đối chiếu và đánh giá kết quả bằng Python theo tiêu chí trong DB | 🟡 | Đã có `mock_ai.assess_quality` đọc `Product.criteria` (nay tải từ PostgreSQL) + `AssessmentResultPage`. Chưa tách thành `rule_engine.py` chính thức | D-023; làm ở T2.3 (còn phụ thuộc Q-004) |
| 7 | Màn hình báo cáo và người kiểm duyệt xác nhận (reviewer trên LAN) | 🟡 | `ReviewQueuePage` + `RecordDetailWidget` + `EvidenceStrip` (đọc lại ảnh từ `relative_path`) + `PostgresRepository.pending_records` & `apply_review` (pass `test_postgres_repository.py`, 14/11/2026). Chưa kiểm thử thư mục mạng SMB thật giữa 2 máy | D-027, D-030; hoàn thiện ở T2.4 & T2.6 |
| 8 | Lưu kết quả vào PostgreSQL (ảnh gốc trên SMB, SHA-256, kết quả AI, quyết định, lịch sử) | 🟢 | `scripts/init_db.sql` (7 bảng trên PostgreSQL 18.3), `database.py`, `postgres_repository.py`, `evidence_service.py` (lưu ảnh gốc không ghi đè D-008 + SHA-256 64 ký tự hex), nối `main.py` & `LiveInspectionPage`. Pass 28/28 tests (`test_postgres_repository.py` + `test_week1_evidence_and_yolo.py`, 14/11/2026). *Chưa kiểm chứng:* ghi trực tiếp qua đường dẫn SMB LAN 2 máy (T2.6) | D-008, D-014, D-018, D-026 |
| 9 | Quản lý và tra cứu dữ liệu | ⬜ | Đã có `PostgresRepository.filter_records` & `all_records`; `PageKey.INSPECTION_HISTORY` đang trỏ `PlaceholderPage` (`main_window.py`) | Làm ở T3.3 |
| 10 | Báo cáo và thống kê (bộ lọc, KPI, biểu đồ, kết quả cấp đơn tổng hợp từ hộp) | 🟡 | `DashboardPage` hiển thị KPI cơ bản; `PostgresRepository.order_summaries` & `daily_outcomes` đã chạy & pass test. `PageKey.REPORTS` đang trỏ `PlaceholderPage` | D-022, D-029; làm ở T3.2 |
| 11 | Xuất báo cáo PDF/Excel, lịch sử xuất | ⬜ | Chưa có service xuất PDF/Excel và chưa có bảng `export_history` trong DB | Làm ở T3.1 & T3.2 |
| 12 | Kết thúc và sử dụng tiếp (lưu trữ, tải lại báo cáo) | ⬜ | Chưa có luồng lưu trữ & tải lại báo cáo đã xuất | Làm sau Bước 11 |
| 13 | Đóng gói EXE trên Windows | ⬜ | Chưa có file `.spec` hay script build PyInstaller | Làm ở T4.1 |

## Hiện trạng kiến trúc & Định hướng tương lai (14/11/2026)

* **Tiến độ hiện tại (Hoàn tất 100% Tuần 1 — 6/6 nhiệm vụ `T1.1` → `T1.6`):**
  * **Giao diện & Phân quyền:** UI Shell PySide6/QSS (`PageKey` + 3 vai trò RBAC `ADMIN`, `INSPECTOR`, `REVIEWER`), luồng tiếp nhận & in/quét QR (`BoxIntakePage`, `QrLabelDialog`), cấu hình danh mục & tiêu chí (`CatalogPage`), chế độ kép Camera / Simulation Feed (`LiveInspectionPage`).
  * **Lưu trữ & Dữ liệu thật:** Tầng PostgreSQL 18 (`PostgresRepository`, `database.py`, `scripts/init_db.sql`), dịch vụ chụp ảnh gốc & băm SHA-256 không ghi đè (`evidence_service.py`), `EvidenceStrip` đọc lại ảnh từ đĩa.
  * **AI & Kiểm thử:** `YoloEngine` (ONNX Runtime chạy nền `QThread` + `CentroidTracker`) kèm 4 file `.onnx` (`fruit_defect.onnx`, `banana_defect.onnx`, `apple_defect.onnx`, `mango_defect.onnx`), đạt **28/28 tests pass** (`run_tests.py`).
* **Trạng thái MVP:** Chạm mốc *Core & ONNX Pipeline Ready* — toàn bộ xương sống lưu trữ DB, ảnh bằng chứng SHA-256 và suy luận ONNX nền đã thông suốt.
* **Lộ trình tương lai (theo [PLANLIST.md](file:///d:/Github%20Clone/AgroScan/Prompt,%20Mindset,%20Rule/PLANLIST.md)):**
  1. **Tuần 2 (`T2.1` → `T2.6` — Thông luồng End-to-End):**
     * Tách `src/agroscan/services/rule_engine.py` chính thức (`T2.3`, thay `mock_ai.assess_quality`).
     * Kiểm thử & hoàn thiện luồng khép kín `BoxIntakePage` ➔ `LiveInspectionPage` (tự nạp model theo `product.model_file`) ➔ `AssessmentResultPage` ➔ `ReviewQueuePage` kèm phóng to xem ảnh bằng chứng (`T2.1`, `T2.2`, `T2.4`).
     * Dựng HTTP REST API cho Qwen-VL trên PC RTX 3060 (`server/qwen_service.py`, `T2.5`) và lưu trữ ảnh qua Windows Share SMB (`storage_service.py`, `T2.6`).
  2. **Tuần 3 (`T3.1` → `T3.6` — Xóa Placeholder & Báo cáo):**
     * Xây dựng xuất PDF biên bản kiểm định (`reportlab`, `T3.1`) và xuất Excel (`openpyxl`).
     * Thay thế toàn bộ 4 trang `PlaceholderPage`: `ReportsPage` (`T3.2`), `InspectionHistoryPage` (`T3.3`), `DataImportPage` (`T3.4`), `UsersPage` (`T3.5`), và hoàn thiện kiểm tra kết nối thật trên `SettingsPage` (`T3.6`).
  3. **Tuần 4 (`T4.1` → `T4.5` — Đóng gói & Nghiệm thu):**
     * Đóng gói standalone `AgroScan.exe` bằng PyInstaller (`T4.1`), fine-tune thêm trọng số `.onnx` trên ảnh thực tế từ Roboflow nếu cần.
     * Kiểm thử LAN 2 máy (Laptop ↔ PC, `T4.2`), đo hiệu năng thực tế (`docs/benchmark_report.md`, `T4.3`), và diễn tập 3 kịch bản demo + phương án dự phòng 1-click (`T4.4`, `T4.5`).

## Nhật ký

| Ngày | Nhiệm vụ | Kết quả | Kiểm chứng | Việc còn lại |
|---|---|---|---|---|
| 29/10/2026 | Phiên AI khác phân tích luồng 12 bước so với repo, chỉ đọc | Báo cáo `agroscan_flow_review.md` | **Chưa kiểm chứng bởi phiên này** | Xác minh các nhận định khi khảo sát repo |
| 01/11/2026 | Phiên hỏi đáp làm rõ yêu cầu: chốt 15 quyết định mới (D-016 → D-029), đóng Q-001/Q-002/Q-007, hủy P-005 | Cập nhật `DECISIONS.md`, `PROJECT.md`, `PROGRESS.md` | File đã ghi, chưa commit | Khảo sát repo, lập kế hoạch triển khai |
| 01/11/2026 | Chốt D-030 (trạng thái), D-031 (camera-first + sim feed), D-032 (dynamic RBAC); phát hiện mã nguồn đang dở dang giữa Bước 2 và 3 | Ghi nhận D-030→D-032; đã tạo các module trang mới và services | `python run.py` văng `ImportError: CommodityType` do `main_window.py` chưa nối `navigation.py` | Ráp nối `main_window.py` & `main.py` với `navigation.py`, hoàn thiện UI shell |
| 01/11/2026 | Ráp nối `main_window.py`, `main.py`, `placeholder_page.py`, `dark_theme.qss`; gỡ xung đột `new_inspection_page.py` | Khởi chạy hoàn chỉnh luồng `LoginDialog` ↔ `MainWindow` theo `PageKey` và phân quyền động D-032 (3 vai trò), nối luồng `BoxIntake` → `LiveInspection` → `AssessmentResult` → `ReviewQueue` (mock RAM) | Chạy pass toàn bộ smoke test & vòng lặp `run.py` trên `QT_QPA_PLATFORM=offscreen` (01/11/2026) | Bổ sung toggle simulation feed D-031 trong `LiveInspectionPage`, hoàn thiện UI chi tiết cho 5 trang placeholder, tích hợp PostgreSQL / YOLO / Qwen-VL |
| 04/11/2026 | Hoàn thiện thẻ `[Desktop] (8) 3.2.4.2 – Design Login/Criteria/QR Screens and VLM JSON Schema` | Xây dựng `CatalogPage` + `catalog_validation.py` (Goods Category & Criteria Editor, nối `MainWindow`); định nghĩa hợp đồng `vlm_models.py` + `docs/api/vlm_analysis.schema.json` (JSON Schema 1.0); tạo `VlmResultPanel` (defects, label OCR + đối chiếu đơn, uncertainty, 5 mã lỗi & loading/cancel) tích hợp vào `LiveInspectionPage` & `RecordDetailWidget`; xuất `docs/ui-spec/3.2.4.2-ui-spec.md`; sửa lỗi ẩn `error_label` sớm trong `LoginDialog` | Chạy pass 10/10 unit test trong `tests/test_sprint2_checklist.py` trên `QT_QPA_PLATFORM=offscreen` (04/11/2026) | Hoàn thiện 4 trang placeholder còn lại (`USERS`, `DATA_IMPORT`, `INSPECTION_HISTORY`, `REPORTS`), nối PostgreSQL & HTTP client Qwen-VL thật |
| 06/11/2026 | Hoàn thiện thẻ `[Desktop] (10) 3.2.5.7 – Build PySide6 Login, Criteria Editor and QR/Barcode UI` | Fast-forward nhánh `main` gộp nền tảng `3.2.4.2`; triển khai `AuthSession` & quản lý Bearer Token ký HMAC-SHA256 trong `MockAuthService` + lưu trạng thái phiên an toàn vào `AppSettings` (`LoginDialog` + `MainWindow`); nâng cấp `CatalogPage` (tìm kiếm sản phẩm, cảnh báo trùng tiêu chí realtime, chặn rời trang khi chưa lưu, đồng bộ trực tiếp sang `BoxIntakePage`); nâng cấp `BoxIntakePage` (hiển thị đầy đủ Order, Lot Size, Declared Category, bảng Criteria & ngưỡng lỗi, 7 mã phân loại lỗi quét kể cả quét nhầm EAN-13 bán lẻ, tìm theo mã đơn gõ tay, debounce 350 ms chống nảy cò máy quét USB, chặn mở trùng phiên D-021); xây dựng bộ sinh mã QR chuẩn ISO/IEC 18004 thuần Python (`qr_encoder.py`) và hộp thoại `QrLabelDialog` | Chạy pass 16/16 unit test (`tests/test_sprint2_checklist.py` + `tests/test_task_3_2_5_7.py`) và smoke test `AppController` + 2 file QSS trên `QT_QPA_PLATFORM=offscreen` (06/11/2026). *Phần chưa kiểm chứng:* kết nối PostgreSQL thật & máy quét USB vật lý ngoài đời | Hoàn thiện 4 trang placeholder còn lại, tích hợp PostgreSQL / YOLO / Qwen-VL thật |
| 13/11/2026 | Khởi tạo PostgreSQL 18 thật (T1.1) & Hoàn thiện Simulation Feed trong `LiveInspectionPage` (T1.5 - D-031) | Tạo script `scripts/init_db.sql` đầy đủ 7 bảng và nạp seed data mẫu thành công 100% trên pgAdmin 4; nâng cấp `LiveInspectionPage` hỗ trợ chế độ kép: Live Camera ↔ Simulation Feed (D-031), tích hợp sẵn các kịch bản mẫu (Fresh, Bruised, Rotten, Apple, Custom image picker) và nút chuyển đổi 1-click khi không có webcam, cho phép chụp bằng chứng và chạy đánh giá offline hoàn toàn | Chạy pass 18/18 unit test (`tests/test_sprint2_checklist.py` + `tests/test_task_3_2_5_7.py` + `tests/test_simulation_feed.py`) trên `QT_QPA_PLATFORM=offscreen` (13/11/2026) | Viết `PostgresRepository` (T1.2) nối DB thật thay `MockRepository`, tích hợp model YOLO ONNX |
| 13/11/2026 | Hoàn thành **T1.2**: Tầng dữ liệu PostgreSQL (`database.py`, `postgres_repository.py`) và nối `main.py` | Tạo `database.py` (đọc `AppSettings` + `.env`/`os.environ`, không hardcode mật khẩu), tạo `.env.example` & `.env` cục bộ (`.gitignore` đã chặn); triển khai `PostgresRepository` tương thích 100% giao diện `MockRepository` (CRUD sản phẩm/tiêu chí, `resolve_box`, `submit_for_review`, `apply_review`, `order_summaries`, `daily_outcomes`); nối `main.py` dùng `PostgresRepository` (kèm fallback an toàn sang `MockRepository` nếu DB offline) | Chạy pass 23/23 tests (`tests/test_postgres_repository.py` + toàn bộ suite cũ) kết nối trực tiếp tới PostgreSQL 18 (`agroscan`) và xác minh `create_repository` chọn `PostgresRepository` (13/11/2026). *Phần chưa kiểm chứng:* lưu ảnh thật qua SMB và mở UI thủ công trên desktop | Làm **T1.3 & T1.4**: tìm dataset, train/export YOLO ONNX và viết `YoloEngine`; làm **T1.6**: lưu ảnh tĩnh & tính SHA-256 |
| 14/11/2026 | Hoàn thành **T1.6**, **T1.3** & **T1.4**: Chụp ảnh bằng chứng + SHA-256 (`evidence_service.py`), xuất model YOLOv8 ONNX (`scripts/export_yolo_onnx.py` + `models/weights/*.onnx`) và tích hợp `YoloEngine` (`yolo_engine.py`) vào `LiveInspectionPage` | Xây dựng `evidence_service.py` mã hóa PNG gốc, băm SHA-256 64 ký tự trước khi vẽ bounding box, lưu ra ổ đĩa không ghi đè (D-008) và nạp lại ảnh trong `EvidenceStrip`; xây dựng `scripts/export_yolo_onnx.py` xuất và kiểm chứng 4 model `.onnx` chuẩn đầu vào/đầu ra YOLOv8 (`[1,3,640,640]` → `[1,7,8400]`, 3 lớp `fresh`, `bruised`, `rotten`); xây dựng `YoloEngine` + `CentroidTracker` (D-025) + `YoloInferenceThread` (`QThread` chạy nền không đơ UI) nối vào `LiveInspectionPage` | Chạy pass 28/28 tests (`tests/test_week1_evidence_and_yolo.py` + toàn bộ suite cũ). *Phần chưa kiểm chứng:* fine-tune trọng số `.onnx` trên tập ảnh thực tế quy mô lớn từ Roboflow | Bước sang **Tuần 2**: tách `rule_engine.py` (**T2.3**), dựng Qwen-VL REST (**T2.5**) và lưu trữ SMB (**T2.6**) |

## Rủi ro và vấn đề tồn đọng

| Mức | Mô tả | Ảnh hưởng | Cách giảm thiểu |
|---|---|---|---|
| *Đã xử lý một phần (14/11/2026)* | Model YOLO ONNX đã chạy qua `YoloEngine`, chưa fine-tune trên ảnh thực tế | Ảnh mẫu chạy chuẩn trên pipeline ONNX; cần đo độ chính xác trên ảnh hộp quả thật | Dùng `scripts/export_yolo_onnx.py --from-pt ... --train-yaml ...` khi có dataset Roboflow, đo trên GTX 1650 Ti |
| *Cần xử lý trước nghiệm thu* | Qwen-VL trên máy chủ chưa cài/đo | Chưa biết hiệu năng thực tế của Qwen-VL trên RTX 3060 | Cài, cấu hình, đo thời gian phản hồi |
| *Đã xử lý (13/11/2026)* | `LiveInspectionPage` hiện chỉ đọc `QCamera` vật lý (D-031) | Máy demo không gắn webcam sẽ hiện "No camera detected" | Đã bổ sung chế độ Simulation Feed (D-031) với preset Chuối/Táo & nút 1-click chuyển đổi khi không có webcam |
| *Đã xử lý (13/11/2026)* | Cơ sở dữ liệu PostgreSQL chưa khởi tạo | Ứng dụng phải lưu dữ liệu tạm trên RAM | Đã cài PostgreSQL 18 và chạy script `scripts/init_db.sql` thành công trên pgAdmin 4 |
| *Đã xử lý (01/11/2026)* | Chuyển trang theo số thứ tự cố định trong `main_window.py` | Đã thay hoàn toàn bằng `PageKey` và `PAGE_SPECS` từ `navigation.py` | Đã kiểm chứng qua smoke test 3 vai trò |
| *Đã xử lý (13/11/2026)* | `.gitignore` chặn tệp DB, ảnh, model AI và `.env` | Đã xác minh: `.gitignore` chặn `.env`, `*.db`, `*.sqlite*`, `*.onnx`, `*.pt*`, `data/`, `exports/`, `images/`, `captures/`, `models_ai/`, `settings.ini` | Kiểm tra `git status` xác nhận `.env` không bị track |
| *Đã xử lý một phần (14/11/2026)* | Test tự động và CI | Đã có 5 bộ test tự động (`28/28` pass qua `run_tests.py`); chưa thiết lập GitHub Actions CI | Duy trì chạy `run_tests.py` trước mỗi lần gộp code |
