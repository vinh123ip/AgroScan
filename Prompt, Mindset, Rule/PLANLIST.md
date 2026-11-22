# PLANLIST.md — Kế hoạch Triển khai Độc lập (Solo Developer Plan)
## DỰ ÁN AGROSCAN (13/11/2026 – 12/12/2026)

> **Mục tiêu:** Kế hoạch hành động tập trung cho **một người tự triển khai toàn bộ hệ thống** từ nay đến ngày bảo vệ đồ án tốt nghiệp (~4 tuần). Triển khai tuần tự theo lát cắt dọc (*Vertical Slice*) để hoàn thiện bản chạy thật End-to-End và đóng gói nghiệm thu.
>
> **Tiến độ hiện tại (23/11/2026):** Toàn bộ các mục phát triển mã nguồn, giao diện, báo cáo PDF/Excel, Qwen-VL REST API, lưu trữ SMB và cấu hình đóng gói PyInstaller (`T1.1` → `T4.5`) đã hoàn thành và được xóa khỏi danh sách chờ theo quy tắc dự án.

---

## 1. Nguyên tắc sống còn khi làm việc một mình (Solo Strategy)

1. **Lát cắt dọc (Vertical Slice First):** Luồng `Quét mã` → `Camera/YOLO` → `Tính kết quả` → `Lưu DB` → `Xuất PDF` đã thông suốt hoàn toàn.
2. **Đóng băng giao diện (UI Freeze):** Toàn bộ 11 màn hình chức năng đã hoàn thiện, xóa sạch `PlaceholderPage`.
3. **Thu gọn bài toán AI:** Đã tích hợp `YoloEngine` (ONNX Runtime), `Simulation Feed` (D-031) và `server/qwen_service.py` (cầu nối REST API sang LM Studio).
4. **Đơn giản hóa dữ liệu:** Đã kết nối PostgreSQL 18 (`PostgresRepository`) kèm cơ chế nạp đơn hàng từ CSV/Excel (`DataImportPage`).

---

## 2. Danh mục nhiệm vụ còn lại (Task List)

*(Không còn nhiệm vụ tồn đọng — Toàn bộ các hạng mục `T1.1` → `T4.5` đã hoàn tất. Khi bảo vệ đồ án chỉ cần bật LM Studio nạp model Qwen-VL ở ngoài và chạy kịch bản trong `docs/demo_presentation_flow.md`.)*
