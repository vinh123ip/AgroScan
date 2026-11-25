# PROGRESS.md — Tiến độ thực tế của AgroScan

**Quy tắc cập nhật:** chỉ đánh dấu 🟢 Hoàn thành khi có **bằng chứng thực tế** (tệp/hàm trong codebase và kết quả chạy test).

**Cập nhật lần cuối:** 26/11/2026

## Trạng thái tổng quan theo 12 bước nghiệp vụ

| # | Hạng mục | Trạng thái | Bằng chứng xác nhận trong codebase |
|---|---|---|---|
| 1 | Nhập dữ liệu đầu vào (CSV/XLSX) | 🟢 | `DataImportPage` + `PostgresRepository.import_orders` (validate từng dòng, tạo `orders`, `lots`, `boxes`, `audit_logs` trong 1 transaction). Pass `test_account_catalog_and_order_import`. |
| 2 | Quản lý danh mục, tiêu chí, người dùng & cấu hình | 🟢 | `CatalogPage` + `catalog_validation.py`, `UsersPage` + `PostgresAuthService`, `SettingsPage` + `connection_checker.py`, RBAC 4 vai trò (`navigation.py`). Pass `test_sprint2_checklist.py`, `test_task_3_2_5_7.py`. |
| 3 | Tiếp nhận hộp & Quét mã QR/Token | 🟢 | `BoxIntakePage` (7 mã lỗi, debounce 350ms, chặn mở trùng phiên), `qr_encoder.py` (ISO/IEC 18004), `PostgresRepository.resolve_box` (hỗ trợ cả `AGS:...` và UUID `scan_token`). Pass `test_postgres_repository.py`. |
| 4 | Kiểm tra realtime: Camera / Simulation Feed + YOLO ONNX + SHA-256 | 🟢 | `LiveInspectionPage`, `YoloEngine` + `YoloInferenceThread` (`models/weights/*.onnx`), `CentroidTracker`, `evidence_service.py` (băm SHA-256 ảnh gốc trước overlay), Whole-Box Coverage (`BoxZone`). Pass `test_week1_evidence_and_yolo.py`, `test_simulation_feed.py`. |
| 5 | Phân tích chuyên sâu Qwen-VL | 🟢 | `VlmResultPanel`, `vlm_models.py` (Schema 1.0), `vlm_client.py`, `server/qwen_service.py` (bridge LM Studio). Pass `test_sprint2_checklist.py`, `test_sprint34_integration.py`, `docs/benchmark_report.md`. |
| 6 | Đối chiếu quy tắc & Đánh giá (Rule Engine) | 🟢 | `rule_engine.py` (`FAIL > NEEDS_REVIEW > PASS` không hardcode) + `AssessmentResultPage` + xác nhận độ phủ toàn thùng trước `submit_for_review`. Pass `test_week2_rule_engine_and_review_flow.py`. |
| 7 | Hàng đợi duyệt độc lập (Maker-Checker) | 🟢 | `ReviewQueuePage`, `EvidenceViewerDialog` (zoom & kiểm tra SHA-256), `PostgresRepository.apply_review` (Pass / Fail / Re-inspect). Pass `TestFlowWithMockRepository` & `TestFlowWithPostgresRepository`. |
| 8 | Cơ sở dữ liệu PostgreSQL v1.2 (15 bảng & 5 seed mẫu) | 🟢 | `scripts/db_v1_2/01_schema.sql`, `02_seed.sql`, `03_grant_app.sql` và `PostgresRepository` (3 views `current_selections`, `latest_lot_decisions`, `box_rule_counts`, 5 lô `DEMO-V12-01`→`05`). Pass `test_postgres_repository.py`. |
| 9 | Lịch sử phiên bản, Audit Trail & Ghi chú định danh | 🟢 | `InspectionHistoryPage`, `RecordDetailWidget`, `PostgresRepository.box_versions` & `add_attributed_note` (không làm thay đổi `lot_decisions.manifest_bytes`). Pass `test_signed_history_note_permissions_and_frozen_manifest`. |
| 10 | Dashboard KPI song ngữ EN/VI & Thống kê | 🟢 | `DashboardPage` (`sample_progress` tính theo `current_selections`), `ReportsPage`, chuyển đổi động EN/VI (`i18n.py`). Pass `test_dashboard_counts_current_slots_only` & `test_sprint34_integration.py`. |
| 11 | Xuất báo cáo PDF & Excel | 🟢 | `pdf_report_service.py` (`export_inspection_record_pdf`, `export_report_excel` 3 sheets luôn xuất tiếng Anh) + ghi nhận `workstation_export` vào `audit_logs`. Pass `test_submitted_seed_review_and_pdf_excel_export`. |
| 12 | Tự động hóa kiểm thử & Tài liệu bàn giao | 🟢 | `run_tests.py` (toàn bộ suite pass 0 lỗi), `tests/e2e_walkthrough.py` (7 bước pass), `tests/autorun.py --headless-check` (18 bước pass), tài liệu hợp nhất tại `docs/HUONG_DAN_KIEM_THU.md`. |

## Hạng mục ngoài phạm vi Desktop hoặc phụ thuộc hạ tầng ngoài
- **Fine-tune trọng số YOLO trên dataset thực tế & đo mAP@0.5 độc lập:** dùng `scripts/export_yolo_onnx.py` khi có bộ dữ liệu Roboflow/Kaggle đã gán nhãn đầy đủ.
- **Đóng gói `AgroScan.exe` bằng `scripts/build_exe.bat`:** script hiện tham chiếu `agroscan.spec` (chưa tạo trong repo); cần sinh `.spec` qua PyInstaller khi đóng gói phát hành.
- **Kiểm thử webcam/máy quét USB/LM Studio thật trên mạng LAN 2 máy:** kiểm thử thủ công theo `docs/HUONG_DAN_KIEM_THU.md`.
