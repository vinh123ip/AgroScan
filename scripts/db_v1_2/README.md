# AgroScan — PostgreSQL Database Design v1.2 Scripts

Thư mục này chứa bộ SQL triển khai **15 bảng, 19 khóa ngoại, 3 views** (`current_selections`, `latest_lot_decisions`, `box_rule_counts`) và **5 lô seed mẫu** (`DEMO-V12-01` → `DEMO-V12-05`).

## Thứ tự chạy trên pgAdmin 4

Mở **Query Tool** trên database đích (ví dụ `agroscan_dev`) bằng tài khoản quản trị PostgreSQL và chạy lần lượt:

1. `01_schema.sql` — Tạo schema `agroscan`, toàn bộ bảng, view, trigger và ràng buộc v1.2.
2. `02_seed.sql` — Nạp 5 lô mẫu (`DEMO-V12-01` đến `DEMO-V12-05`) và bản kê ký số RSA-PSS/SHA-256 mẫu.
3. `03_grant_app.sql` — Cấp quyền vận hành cho vai trò `agro_user` (sửa tên vai trò trong script nếu `.env` dùng tên khác).

> Xem hướng dẫn đầy đủ cách cấu hình `.env`, tạo tài khoản Admin (`python run.py --create-admin`), câu lệnh SQL đối chiếu 5 seed mẫu và toàn bộ ca kiểm thử tại **[docs/HUONG_DAN_KIEM_THU.md](../../docs/HUONG_DAN_KIEM_THU.md)**.
