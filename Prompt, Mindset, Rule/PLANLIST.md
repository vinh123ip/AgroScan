# PLANLIST.md — Kế hoạch & Tác vụ Mở rộng Tiếp theo (AgroScan)

> **Hiện trạng đến 26/11/2026:** Toàn bộ luồng kiểm định Desktop 12 bước, kết nối PostgreSQL v1.2 (15 bảng + 5 seed mẫu), song ngữ EN/VI, Qwen-VL HTTP Bridge, xuất PDF/Excel và bộ test tự động đã hoàn tất và tích hợp trên `main` và `develop`.

---

## Các hạng mục mở rộng / hoàn thiện sau khi các thành viên khác pull `main`

1. **Huấn luyện & đánh giá model YOLO thực tế:**
   - Gán nhãn tập ảnh nông/thủy sản thật và xuất model chuyên biệt qua `scripts/export_yolo_onnx.py` để thay thế model baseline khi cần.
   - Ghi nhận kết quả mAP@0.5 trên tập kiểm thử độc lập (thẻ Trello `3.1.5.5`).
2. **Đo kiểm VLM Qwen2-VL / Qwen2.5-VL trên phần cứng mục tiêu:**
   - Chạy thử nghiệm thực tế với Ollama hoặc LM Studio trên máy chủ GPU và cập nhật bổ sung `docs/benchmark_report.md` (thẻ `3.2.5.3`).
3. **Khởi tạo tệp `agroscan.spec` và đóng gói `AgroScan.exe`:**
   - Tạo `agroscan.spec` cho PyInstaller và kiểm thử chạy `scripts/build_exe.bat` trên máy Windows sạch không cài Python.
4. **Hoàn thiện UI thao tác khóa kế hoạch & ký quyết định cấp lô trực tiếp (tùy chọn mở rộng v1.2):**
   - Hiện `PostgresRepository` đọc đầy đủ `current_selections`, `latest_lot_decisions` và kiểm chứng khóa kế hoạch/chữ ký RSA-PSS ở tầng DB; có thể bổ sung màn hình tạo/điều chỉnh kế hoạch lấy mẫu và ký lô trực tiếp trên desktop nếu mở rộng thêm.
