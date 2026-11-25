# AGENTS.md — AgroScan

Ứng dụng desktop kiểm tra chất lượng nông/thủy sản (**Python 3.13 + PySide6 + YOLOv8 ONNX + Qwen-VL Bridge + PostgreSQL v1.2**).

## Bắt đầu mỗi phiên

1. Đọc theo thứ tự trong `Prompt, Mindset, Rule/`:
   - `RULES.md` (quy tắc hành vi, ngưỡng hỏi/làm, sửa lỗi, báo cáo)
   - `DECISIONS.md` (các quyết định kiến trúc & nghiệp vụ đã duyệt `D-001` → `D-037`)
   - `PROJECT.md` (kiến trúc, schema PostgreSQL v1.2 15 bảng, quy tắc AI & bảo toàn bằng chứng)
   - `PROGRESS.md` (trạng thái thực tế kèm bằng chứng kiểm chứng)
   - `PLANLIST.md` (danh sách tác vụ tương lai nếu có)
2. Tài liệu đặc tả chính thức phiên bản mới nhất nằm ngoài repo tại `E:\AgroScan_Project\Documentation\` (xem bảng đối chiếu trong `PROJECT.md`).
3. Hướng dẫn cài đặt, nạp DB v1.2 và kiểm thử duy nhất trong repo: `docs/HUONG_DAN_KIEM_THU.md`.
4. Chạy `git status` trong `E:\AgroScan_Project\AgroScan` trước khi sửa tệp.

## Ba quy tắc cốt lõi

1. Yêu cầu *"xem / phân tích / đánh giá / đề xuất / giải thích"* → **chỉ đọc, không sửa tệp**.
2. Nhiệm vụ lớn (≥ 3 tệp, đụng DB/nghiệp vụ, nhiều tầng) → trình bày kế hoạch và **chờ xác nhận** trước khi sửa mã.
3. Không tự ý đổi schema PostgreSQL v1.2, quy tắc lấy mẫu/ký lô, hoặc công nghệ chính ngoài `DECISIONS.md`.

## Ngôn ngữ & Song ngữ

- **Chat với người dùng:** tiếng Việt (giữ nguyên tên định danh/tệp tiếng Anh).
- **Mã nguồn, comment, docstring, commit message:** tiếng Anh.
- **Giao diện ứng dụng:** hỗ trợ chuyển đổi động **EN / VI** (`i18n.py`).
- **Báo cáo xuất file (PDF / Excel) & khóa bản kê ký số:** luôn xuất bằng **tiếng Anh** (`D-035`).
