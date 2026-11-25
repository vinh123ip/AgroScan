# AgroScan

> **AI-Powered Semi-Automated Multi-Category Goods Inspection System**  
> Ứng dụng desktop kiểm tra và đánh giá chất lượng hàng hóa nông/thủy sản tại cửa khẩu logistics bằng **PySide6**, **YOLOv8 ONNX**, **Qwen-VL** và **PostgreSQL v1.2**.

---

## Tính năng đã hoàn thiện

- **Desktop Workstation song ngữ EN / VI:** Xây dựng bằng PySide6 + QSS với 11 màn hình nghiệp vụ đầy đủ và phân quyền RBAC 4 vai trò (`Admin`, `Inspector`, `Reviewer`, `Manager`).
- **Tiếp nhận & Định danh QR ISO/IEC 18004:** Hỗ trợ quét mã hộp `AGS:<Order>-<Box>/<Total>` hoặc UUID `scan_token`, phát hiện 7 loại lỗi quét và sinh/in nhãn QR.
- **Thị giác máy tính Edge & Bằng chứng SHA-256:** Chạy YOLOv8 ONNX trên `QThread` nền (`CentroidTracker`), hỗ trợ **Live Camera**, **Import Original**, **Simulation Feed** và theo dõi độ phủ toàn thùng (`BoxZone`). Ảnh gốc luôn được băm SHA-256 trước khi vẽ bounding box.
- **Phân tích sâu Qwen-VL & Rule Engine:** Giao tiếp HTTP REST JSON Schema 1.0 tới LM Studio / `server/qwen_service.py`; Python Rule Engine đánh giá deterministic theo cấu hình trong DB.
- **PostgreSQL Database Design v1.2:** Triển khai đầy đủ 15 bảng, 19 khóa ngoại, 3 views (`current_selections`, `latest_lot_decisions`, `box_rule_counts`), 5 lô seed mẫu (`DEMO-V12-01` → `DEMO-V12-05`), maker-checker độc lập và hồ sơ ký số RSA-PSS/SHA-256.
- **Báo cáo PDF & Excel:** Xuất chứng nhận PDF có ảnh & SHA-256 (`reportlab`) và Excel 3-sheet (`openpyxl`) chuẩn tiếng Anh.

---

## Khởi chạy nhanh (Quick Start)

```powershell
# 1. Cài đặt môi trường (chạy 1 lần trên máy mới)
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/export_yolo_onnx.py
Copy-Item .env.example .env

# 2. Tạo tài khoản Admin trên PostgreSQL v1.2 (sau khi nạp SQL trong scripts/db_v1_2/)
python run.py --create-admin admin

# 3. Khởi chạy ứng dụng
python run.py          # Chế độ PostgreSQL v1.2
python run.py --demo   # Chế độ Demo dùng RAM (inspector / reviewer / admin)
```

> **Hướng dẫn chi tiết từ đầu đến cuối** (nạp PostgreSQL 15 bảng & 5 seed mẫu, kiểm thử thủ công TC01–TC12, kịch bản trình diễn bảo vệ đồ án và chạy Unit Test tự động): xem duy nhất tại **[docs/HUONG_DAN_KIEM_THU.md](docs/HUONG_DAN_KIEM_THU.md)**.

---

## Cấu trúc thư mục chính

```text
AgroScan/
├── docs/
│   ├── api/vlm_analysis.schema.json   # Hợp đồng JSON Schema 1.0 cho Qwen-VL
│   ├── benchmark_report.md            # Báo cáo đo hiệu năng hệ thống
│   ├── BRANCH_TRELLO_AUDIT.md         # Đối chiếu Git branches & Trello
│   └── HUONG_DAN_KIEM_THU.md          # Tài liệu cài đặt, DB v1.2 & kiểm thử duy nhất
├── Prompt, Mindset, Rule/             # Quy tắc AI & tài liệu thiết kế tham chiếu
├── scripts/
│   ├── db_v1_2/                       # 01_schema.sql, 02_seed.sql, 03_grant_app.sql
│   ├── export_yolo_onnx.py            # Xuất model YOLOv8 ONNX baseline
│   └── build_exe.bat                  # Script đóng gói PyInstaller
├── server/qwen_service.py             # Qwen-VL HTTP REST bridge (port 8000)
├── src/agroscan/                      # Mã nguồn chính (models, services, ui)
├── tests/                             # Bộ kiểm thử Unit, E2E & Autorun 18 bước
├── run.py                             # Launcher tự nhận diện .venv & bật VLM bridge
└── run_tests.py                       # Trình chạy toàn bộ bộ kiểm thử tự động
```
