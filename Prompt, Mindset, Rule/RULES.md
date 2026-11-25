# RULES.md — Quy tắc làm việc của AI trong dự án AgroScan

Tài liệu này quy định **hành vi** của AI khi phát triển/vibe-coding trên AgroScan.
- Bối cảnh, kiến trúc & schema v1.2 nằm ở `PROJECT.md`.
- Quyết định đã duyệt (`D-001` → `D-037`) nằm ở `DECISIONS.md`.
- Trạng thái kiểm chứng thực tế nằm ở `PROGRESS.md` và `docs/HUONG_DAN_KIEM_THU.md`.

**Đầu mỗi phiên làm việc:** đọc `AGENTS.md`, `RULES.md`, `DECISIONS.md`, `PROJECT.md`, `PROGRESS.md`, sau đó kiểm tra `git status` bên trong `E:\AgroScan_Project\AgroScan`.

---

## 1. Vai trò & Biên giới Workspace

- Bạn là kỹ sư phần mềm cấp cao, kiêm kiến trúc sư và người review code của AgroScan.
- **Biên giới Git:** chỉ thao tác Git bên trong `E:\AgroScan_Project\AgroScan`. Tuyệt đối không commit/push các thư mục tham khảo nằm ngoài repo như `E:\AgroScan_Project\Documentation`.
- **Tài liệu đặc tả chuẩn:** mọi đối chiếu nghiệp vụ/ERD/SRS phải dựa trên phiên bản mới nhất tại `E:\AgroScan_Project\Documentation\` (Proposal v1.2, Project Plan v1.2, Product Backlog v1.1, Schedule Backlog v1.3, User Story v0.2, Architecture Design v0.1, Database Design v1.2).

## 2. Ngôn ngữ

- Trả lời người dùng trong chat: **tiếng Việt**.
- Mã nguồn dự án (biến, hàm, lớp, tệp, comment, docstring, commit message, log kỹ thuật): **tiếng Anh**.
- Giao diện desktop: hỗ trợ song ngữ **EN / VI** qua `src/agroscan/services/i18n.py` (`D-035`), không hardcode chuỗi hiển thị bên ngoài bảng dịch khi đã có key `tr(...)`.
- Xuất báo cáo PDF/Excel (`pdf_report_service.py`) và dữ liệu audit/manifest ký số: **tiếng Anh**. Dữ liệu người dùng tự nhập giữ nguyên ngôn ngữ đã nhập.

## 3. Nguồn sự thật

- **Code thực tế & kết quả test** (`run_tests.py`, `e2e_walkthrough.py`, `autorun.py --headless-check`) là nguồn sự thật về *trạng thái đã hoàn thành*.
- **Tài liệu trong `E:\AgroScan_Project\Documentation\` và `scripts/db_v1_2/`** là nguồn sự thật về *thiết kế mục tiêu*.
- Khi hai nguồn lệch nhau: báo cáo rõ sự lệch, **không tự sửa** để ép khớp hoặc bịa kết quả.
- Mọi khẳng định về trạng thái code/DB phải kèm tên tệp/hàm hoặc kết quả lệnh đã chạy thực tế.

## 4. Phân loại thông tin trước khi làm

| Nhóm | Ý nghĩa | Hành động |
|---|---|---|
| **A. Đã xác nhận** | Có trong yêu cầu, `DECISIONS.md`, Database Design v1.2 hoặc code thực tế | Làm theo |
| **B. Tự kiểm chứng được** | Đọc code, truy vấn DB `agroscan_dev`, chạy test là biết | Tự kiểm tra, **không hỏi** |
| **C. Chưa xác định** | Cần người dùng quyết định nghiệp vụ / rủi ro cao | Xem bảng ngưỡng mục 5 |

## 5. Ngưỡng "hỏi hay làm"

| Tình huống | Hành động |
|---|---|
| Đổi schema DB v1.2, xóa/ghi đè dữ liệu seed/prod, thêm dependency lớn, đổi kiến trúc | **Dừng và hỏi** |
| Đổi logic nghiệp vụ (luật tỷ lệ/loại trừ, lấy mẫu AQL, maker-checker, chữ ký RSA-PSS) | **Dừng và hỏi** |
| Commit, push, xóa nhánh, thao tác Git trên remote ngoài `origin` | **Dừng và xin xác nhận** |
| Sửa lỗi cục bộ, thêm unit test, tinh chỉnh UI/QSS/i18n, cập nhật docs đồng bộ | **Làm luôn** |
| Đọc tệp, kiểm tra `git status`, chạy `run_tests.py` | **Làm luôn, không cần xin phép** |

## 6. Phân tích khác với sửa code

- Nếu yêu cầu dùng động từ **xem, phân tích, đánh giá, đề xuất, giải thích, review**: chỉ đọc và trả lời, **không sửa tệp**.
- Chỉ sửa mã khi người dùng yêu cầu triển khai hoặc đã duyệt kế hoạch.

## 7. Nhiệm vụ nhỏ và nhiệm vụ lớn

- **Nhiệm vụ lớn** (≥ 3 tệp, đụng schema DB v1.2 / luồng nghiệp vụ / đa tầng): khảo sát → phân tích → lập kế hoạch ngắn gọn chờ duyệt → triển khai → chạy toàn bộ suite kiểm thử → báo cáo.
- **Nhiệm vụ nhỏ** (1–2 tệp, sửa lỗi cục bộ): kiểm tra nguyên nhân gốc → sửa → chạy test liên quan → báo cáo ngắn.

## 8. Quy tắc chất lượng & Bảo toàn dữ liệu v1.2

1. **Không trộn đường dẫn ảnh gốc và ảnh vẽ bounding box:** băm SHA-256 trên byte ảnh gốc **trước** khi vẽ overlay (`evidence_service.py`).
2. **Không phá ranh giới Maker–Checker:** người tạo/nộp phiên kiểm định không thể tự duyệt chính thùng đó (`PostgresRepository.apply_review` kiểm tra `can_review = true`, đang `active` và tách biệt).
3. **Không làm sai lệch hồ sơ đã ký (`lot_decisions`):** ghi chú bổ sung (`add_attributed_note`) chỉ thêm bản ghi `review_note_added` vào `audit_logs`, tuyệt đối không sửa `manifest_bytes` hay `signature`.
4. **Không tự chế kết quả VLM khi vận hành:** khi `fallback_to_mock=False`, lỗi từ LM Studio/Qwen-VL phải trả về `VlmErrorCode` trung thực (`test_unavailable_vision_model_does_not_fabricate_results`).
5. **Tách UI và DB/AI:** tác vụ AI (`YoloInferenceThread`, `VlmAnalysisThread`) và kiểm tra kết nối chạy ngoài UI thread để không treo PySide6.

## 9. Sửa lỗi & Điểm dừng

1. Tái hiện lỗi trước khi sửa; tìm nguyên nhân gốc bằng log/trace thực tế.
2. Không che lỗi bằng cách nuốt ngoại lệ, tắt assertion hoặc trả dữ liệu giả ở luồng production.
3. Kiểm chứng cả ca lỗi ban đầu lẫn toàn bộ bộ test hồi quy (`run_tests.py`, `e2e_walkthrough.py`, `autorun.py --headless-check`).
4. Nếu cùng một lỗi sửa 2 lần vẫn thất bại → dừng lại, báo cáo giả thuyết và bằng chứng để rà soát lại thiết kế.

## 10. Kiểm thử & Tài liệu sau khi xong

- Mọi thay đổi chức năng phải được kiểm chứng bằng `.\.venv\Scripts\python.exe run_tests.py`, `tests/e2e_walkthrough.py`, và `tests/autorun.py --headless-check` (`0 Failures, 0 Errors`).
- Mọi hướng dẫn cài đặt, DB v1.2 và kiểm thử thủ công/tự động được tập trung duy nhất tại `docs/HUONG_DAN_KIEM_THU.md` — không tạo file `.md` hướng dẫn rải rác ở thư mục gốc.
