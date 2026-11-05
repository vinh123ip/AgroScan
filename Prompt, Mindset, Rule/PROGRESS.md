# PROGRESS.md — Tiến độ thực tế của AgroScan

**Quy tắc cập nhật:** một hạng mục chỉ được đánh dấu "Hoàn thành" khi có **bằng chứng** (tên test đã chạy và kết quả, hoặc hành vi đã kiểm tra thủ công kèm ngày). Có mã nguồn chưa đủ.

AI cập nhật tệp này sau mỗi nhiệm vụ thuộc roadmap và ghi rõ phần nào chưa kiểm chứng.

**Cập nhật lần cuối:** 04/11/2026

## Trạng thái

- ⬜ Chưa xác minh (chưa ai kiểm tra repo)
- 🟡 Đang làm
- 🟢 Hoàn thành (có bằng chứng)
- 🔴 Bị chặn

## Bảng tiến độ theo 12 bước của sơ đồ hệ thống

Trạng thái ban đầu là **chưa xác minh**. Ở phiên đầu tiên, AI khảo sát repo và điền cột "Bằng chứng"; người dùng xác nhận.

| # | Hạng mục (theo sơ đồ) | Trạng thái | Bằng chứng (tệp/hàm/test/ngày) | Ghi chú |
|---|---|---|---|---|
| 1 | Chuẩn bị và nhập dữ liệu ban đầu (Excel/CSV chính, PDF giao Qwen-VL) | ⬜ | | D-029 |
| 2 | Quản lý danh mục, tiêu chí kiểm định, người dùng/phân quyền, cấu hình hệ thống | ⬜ | | D-024 (model theo quả), D-027 (3 vai trò), D-028 (Settings) |
| 3 | Tiếp nhận đơn hàng (quét barcode QR, 1 mã = 1 hộp = 1 phiên) | ⬜ | | D-019, D-020, D-021. Phiên AI khác báo mới có form nhập tay, dữ liệu chỉ trong RAM (chưa kiểm chứng) |
| 4 | Kiểm tra realtime: camera + YOLO chuyên hóa + ByteTrack + ảnh tĩnh bằng chứng | ⬜ | | D-024, D-025, D-026. Cần tìm dataset, train model, đo hiệu năng trên GTX 1650 Ti |
| 5 | Phân tích chuyên sâu Qwen-VL (bấm nút, HTTP REST từ máy chủ) | ⬜ | | D-017 |
| 6 | Đối chiếu và đánh giá kết quả bằng Python theo tiêu chí trong DB | ⬜ | | D-023. Phụ thuộc Q-004 (cách xử lý sai mã) |
| 7 | Màn hình báo cáo và người kiểm duyệt xác nhận (reviewer trên LAN) | ⬜ | | D-027. Phụ thuộc Q-004 |
| 8 | Lưu kết quả vào PostgreSQL (ảnh gốc trên SMB, SHA-256, kết quả AI, quyết định, lịch sử) | ⬜ | | D-014, D-018 |
| 9 | Quản lý và tra cứu dữ liệu | ⬜ | | |
| 10 | Báo cáo và thống kê (bộ lọc, KPI, biểu đồ, kết quả cấp đơn tổng hợp từ hộp) | ⬜ | | D-022, D-029 (chat AI tương lai) |
| 11 | Xuất báo cáo PDF/Excel, lịch sử xuất | ⬜ | | |
| 12 | Kết thúc và sử dụng tiếp (lưu trữ, tải lại báo cáo) | ⬜ | | |
| 13 | Đóng gói EXE trên Windows | ⬜ | | |

## Phiên khảo sát đầu tiên

Việc AI cần làm ở phiên đầu (chỉ đọc, **không sửa tệp**):

1. Xem cấu trúc thư mục, điểm khởi chạy, kiến trúc giao diện, tầng nghiệp vụ, tầng dữ liệu, cấu hình.
2. Kiểm tra `git status` và lịch sử gần đây.
3. Xác nhận code hiện tại chưa có PostgreSQL, YOLO hay bất kỳ tầng nghiệp vụ/dữ liệu nào (chỉ có UI shell + demo dataclass).
4. Điền bảng trên với bằng chứng thực tế.
5. Liệt kê chỗ code lệch với `PROJECT.md` và sơ đồ.
   Kiểm tra riêng các điểm làm việc nhóm: cách chuyển trang trong `main_window.py` (số thứ tự hay tên), số tệp QSS, `.gitignore` đã chặn DB/ảnh/model chưa, đã có test hay CI chưa, SQL có nằm trong tầng giao diện không.
6. Báo cáo và chờ người dùng xác nhận.

## Nhật ký

| Ngày | Nhiệm vụ | Kết quả | Kiểm chứng | Việc còn lại |
|---|---|---|---|---|
| 29/10/2026 | Phiên AI khác phân tích luồng 12 bước so với repo, chỉ đọc | Báo cáo `agroscan_flow_review.md` | **Chưa kiểm chứng bởi phiên này** | Xác minh các nhận định khi khảo sát repo |
| 01/11/2026 | Phiên hỏi đáp làm rõ yêu cầu: chốt 15 quyết định mới (D-016 → D-029), đóng Q-001/Q-002/Q-007, hủy P-005 | Cập nhật `DECISIONS.md`, `PROJECT.md`, `PROGRESS.md` | File đã ghi, chưa commit | Khảo sát repo, lập kế hoạch triển khai |
| 01/11/2026 | Chốt D-030 (trạng thái), D-031 (camera-first + sim feed), D-032 (dynamic RBAC); phát hiện mã nguồn đang dở dang giữa Bước 2 và 3 | Ghi nhận D-030→D-032; đã tạo các module trang mới và services | `python run.py` văng `ImportError: CommodityType` do `main_window.py` chưa nối `navigation.py` | Ráp nối `main_window.py` & `main.py` với `navigation.py`, hoàn thiện UI shell |
| 01/11/2026 | Ráp nối `main_window.py`, `main.py`, `placeholder_page.py`, `dark_theme.qss`; gỡ xung đột `new_inspection_page.py` | Khởi chạy hoàn chỉnh luồng `LoginDialog` ↔ `MainWindow` theo `PageKey` và phân quyền động D-032 (3 vai trò), nối luồng `BoxIntake` → `LiveInspection` → `AssessmentResult` → `ReviewQueue` (mock RAM) | Chạy pass toàn bộ smoke test & vòng lặp `run.py` trên `QT_QPA_PLATFORM=offscreen` (01/11/2026) | Bổ sung toggle simulation feed D-031 trong `LiveInspectionPage`, hoàn thiện UI chi tiết cho 5 trang placeholder, tích hợp PostgreSQL / YOLO / Qwen-VL |
| 04/11/2026 | Hoàn thiện thẻ `[Desktop] (8) 3.2.4.2 – Design Login/Criteria/QR Screens and VLM JSON Schema` | Xây dựng `CatalogPage` + `catalog_validation.py` (Goods Category & Criteria Editor, nối `MainWindow`); định nghĩa hợp đồng `vlm_models.py` + `docs/api/vlm_analysis.schema.json` (JSON Schema 1.0); tạo `VlmResultPanel` (defects, label OCR + đối chiếu đơn, uncertainty, 5 mã lỗi & loading/cancel) tích hợp vào `LiveInspectionPage` & `RecordDetailWidget`; xuất `docs/ui-spec/3.2.4.2-ui-spec.md`; sửa lỗi ẩn `error_label` sớm trong `LoginDialog` | Chạy pass 10/10 unit test trong `tests/test_sprint2_checklist.py` trên `QT_QPA_PLATFORM=offscreen` (04/11/2026) | Hoàn thiện 4 trang placeholder còn lại (`USERS`, `DATA_IMPORT`, `INSPECTION_HISTORY`, `REPORTS`), nối PostgreSQL & HTTP client Qwen-VL thật |

## Rủi ro và vấn đề tồn đọng

| Mức | Mô tả | Ảnh hưởng | Cách giảm thiểu |
|---|---|---|---|
| *Cần xử lý trước nghiệm thu* | Chưa có dataset YOLO cho các loại quả mục tiêu | Bước 4 chưa chạy thật được | Tìm dataset công khai trên Roboflow/Kaggle, train và đo trên GTX 1650 Ti |
| *Cần xử lý trước nghiệm thu* | Qwen-VL và PostgreSQL trên máy chủ chưa cài/đo | Chưa biết hiệu năng thực tế của Qwen-VL trên RTX 3060, và cấu hình PostgreSQL | Cài, cấu hình, đo thời gian phản hồi |
| *Cần xử lý trước nghiệm thu* | `LiveInspectionPage` hiện chỉ đọc `QCamera` vật lý, chưa có toggle simulation feed theo D-031 (`.venv` chưa cài `opencv-python`) | Máy demo không gắn webcam sẽ hiện "No camera detected" và không chụp được ảnh bằng chứng | Bổ sung chế độ simulation feed (video/ảnh mẫu) trong `LiveInspectionPage` theo D-031 |
| *Đã xử lý (01/11/2026)* | Chuyển trang theo số thứ tự cố định trong `main_window.py` | Đã thay hoàn toàn bằng `PageKey` và `PAGE_SPECS` từ `navigation.py` | Đã kiểm chứng qua smoke test 3 vai trò |
| *Chưa kiểm chứng* | `.gitignore` chưa chặn tệp DB, ảnh, model AI (báo từ phiên AI khác) | Có thể push nhầm tệp nặng hoặc dữ liệu | Kiểm tra `.gitignore` |
| *Chưa kiểm chứng* | Chưa có test tự động hoặc CI (báo từ phiên AI khác) | Hỏng chỉ biết khi mở app bấm thử | Đề xuất sau, cần duyệt (P-006) |
