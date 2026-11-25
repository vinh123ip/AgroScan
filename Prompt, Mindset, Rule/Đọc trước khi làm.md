# Đọc trước khi làm — Quy ước nhanh cho AI

1. **Nguồn sự thật tài liệu:**
   - Đặc tả chính thức phiên bản mới nhất nằm tại `E:\AgroScan_Project\Documentation\` (Proposal v1.2, Project Plan v1.2, Product Backlog v1.1, Schedule v1.3, User Story v0.2, Architecture Design v0.1, Database Design v1.2).
   - Hướng dẫn cài đặt, nạp PostgreSQL v1.2, chạy kiểm thử thủ công & tự động duy nhất trong repo: `docs/HUONG_DAN_KIEM_THU.md`.
2. **File kế hoạch & tiến độ trong `Prompt, Mindset, Rule/`:**
   - Luôn đọc `AGENTS.md`, `RULES.md`, `DECISIONS.md`, `PROJECT.md` trước khi code.
   - `PLANLIST.md` lưu các tác vụ còn lại hoặc mở rộng tương lai (xóa việc đã xong kèm bằng chứng).
   - `PROGRESS.md` phản ánh trạng thái thực tế của hệ thống kèm bằng chứng test đã chạy.
3. **Quy tắc test tiết kiệm & chính xác:**
   - Chạy kiểm thử trên bộ test chính thức của repo (`python run_tests.py`, `python tests/e2e_walkthrough.py`, `python tests/autorun.py --headless-check`), không sinh file test thừa thãi ngoài `tests/` khi không cần thiết.
   - Mọi test ghi PostgreSQL phải dùng savepoint rollback (`isolated_writes`) để giữ nguyên 5 seed mẫu `DEMO-V12-01` → `DEMO-V12-05`.
