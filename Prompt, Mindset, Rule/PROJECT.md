# PROJECT.md — Bối cảnh, kiến trúc và quy tắc nghiệp vụ AgroScan

Tài liệu tóm tắt kiến trúc kỹ thuật và ràng buộc nghiệp vụ của **AgroScan** (Đồ án tốt nghiệp Software Engineering — Đại học Duy Tân, C2SE.07). Trạng thái kiểm chứng thực tế xem ở `PROGRESS.md`; hướng dẫn cài đặt & kiểm thử xem ở `docs/HUONG_DAN_KIEM_THU.md`.

---

## 1. Tài liệu đặc tả chính thức (Phiên bản mới nhất)

Thư mục tài liệu ngoài repo tại `E:\AgroScan_Project\Documentation\`:

| Tài liệu | Phiên bản hiện hành | Vị trí tham chiếu |
|---|---|---|
| Proposal | `ver_1.2` | `E:\AgroScan_Project\Documentation\1. Proposal\01 C2SE.07_Proposal_AgroScan_ver_1.2.docx` |
| Project Plan | `ver_1.2` | `E:\AgroScan_Project\Documentation\2. Project Plan\02 C2SE.07_Project-Plan_AgroScan_ver_1.2.docx` |
| Product Backlog | `ver1.1` / Schedule `v1.3` | `E:\AgroScan_Project\Documentation\3. Product Backlog\03 C2SE.07_ProductBacklog_AgroScan_ver1.1.docx` & `AgroScan_Schedule_Backlog_Merged_v1.3.xlsx` |
| User Story | `ver0.2` | `E:\AgroScan_Project\Documentation\4. User Story\04 C2SE.07_UserStory_AgroScan_ver0.2.docx` |
| Architecture Design | `ver 0.1` | `E:\AgroScan_Project\Documentation\5. Architecture Design\05 C2SE.07-AchitectureDesign_AgroScan_ver 0.1.docx` |
| Database Design | `ver1.2` | `E:\AgroScan_Project\Documentation\6. Database Design\06 C2SE.07_Database_Design_AgroScan_ver1.2.docx` |
| UI Design | `ver 1.2` (Markdown) | `Prompt, Mindset, Rule/07_C2SE07_User_Interface_Design_AgroScan.md` |

---

## 2. Công nghệ & Kiến trúc triển khai

| Thành phần | Triển khai thực tế trong `src/agroscan/` |
|---|---|
| **Desktop UI** | Python 3.13 + PySide6 + QSS (`ui/main_window.py`, `ui/theme.py`, `ui/navigation.py`), hỗ trợ chuyển đổi động **EN / VI** (`services/i18n.py`). |
| **11 Trang giao diện** | `DashboardPage`, `BoxIntakePage`, `LiveInspectionPage`, `AssessmentResultPage`, `ReviewQueuePage`, `InspectionHistoryPage`, `ReportsPage`, `DataImportPage`, `CatalogPage`, `UsersPage`, `SettingsPage`. |
| **Database v1.2** | PostgreSQL 18 (`scripts/db_v1_2/01_schema.sql`, `02_seed.sql`, `03_grant_app.sql`) qua `services/database.py` & `services/postgres_repository.py`. Schema `agroscan` gồm **15 bảng, 19 khóa ngoại, 3 views** (`current_selections`, `latest_lot_decisions`, `box_rule_counts`). |
| **AI Detection (Edge)** | `services/yolo_engine.py`: YOLOv8 ONNX (`onnxruntime`) chạy nền `QThread` (`YoloInferenceThread`) + `CentroidTracker` chống đếm trùng. |
| **Rule Engine** | `services/rule_engine.py`: Đánh giá deterministic `PASS / FAIL / NEEDS_REVIEW` từ tiêu chí sản phẩm trong DB (không hardcode). |
| **VLM Deep Analysis** | `services/vlm_client.py` ↔ `server/qwen_service.py`: HTTP REST JSON Schema 1.0 (`docs/api/vlm_analysis.schema.json`), kết nối LM Studio hoặc fallback an toàn ở chế độ Demo. |
| **Bằng chứng & Lưu trữ** | `services/evidence_service.py` & `services/storage_service.py`: Lưu ảnh gốc trước overlay, tính SHA-256 64 ký tự hex không ghi đè, hỗ trợ SMB / cache local. |
| **Báo cáo** | `services/pdf_report_service.py`: Xuất PDF chứng nhận phiên (`reportlab`) và Excel 3-sheet (`openpyxl`: `Order Summary`, `Inspection Sessions`, `Evidence Integrity`) luôn chuẩn tiếng Anh. |

---

## 3. Quy tắc nghiệp vụ & Toàn vẹn dữ liệu (Database Design v1.2)

1. **Cấu trúc Đơn → Lô → Thùng → Lượt chọn → Phiên (Attempt):**
   - `orders` → `lots` → `boxes` → `sample_selections` → `inspections` → `inspection_batches` → `inspection_images` & `observed_products`.
   - **Thay thùng (`sample_selections.replaces_id`):** Thùng chưa kiểm nhưng không tiếp cận được có thể được Reviewer cho phép thay bằng thùng dự phòng ở cùng lô/revision/slot.
   - **Tái kiểm (`inspections.previous_id`):** Thùng đã kiểm nhưng thiếu bằng chứng được Reviewer chuyển `reinspect` để mở attempt kế tiếp trên cùng `selection_id`.
2. **Độ phủ & Ảnh đếm:**
   - Khi nộp (`submit_for_review`), bắt buộc `coverage_confirmed=True`, toàn bộ ảnh hợp lệ khớp SHA-256 và ảnh cuối của batch (`is_count_image=true`) có kết quả detector thực tế.
3. **Maker–Checker độc lập & Chữ ký lô (`lot_decisions`):**
   - Reviewer phải có `can_review = true`, `active = true`, và tách biệt với người tạo/nộp.
   - Bản kê ký số RSA-PSS/SHA-256 (`manifest_bytes`, `signature`) là bất biến; ghi chú bổ sung (`add_attributed_note`) chỉ ghi thêm vào `audit_logs`.
4. **Hàng rào môi trường:**
   - `python run.py` tự khởi động local VLM bridge trên `127.0.0.1:8000` (nếu cấu hình mặc định) và kết nối PostgreSQL v1.2 qua `.env`.
   - `python run.py --demo` chạy chế độ mô phỏng trên RAM (`MockRepository` + `MockAuthService`).
