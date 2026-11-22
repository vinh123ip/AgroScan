# Kịch bản Trình diễn & Phương án Dự phòng 1-Click Phòng Thi (T4.4, T4.5)

Tài liệu này quy định **3 kịch bản demo chuẩn** trước hội đồng bảo vệ đồ án tốt nghiệp và **phương án dự phòng 1-click** để đảm bảo buổi bảo vệ diễn ra trơn tru 100% trong mọi điều kiện phần cứng/mạng tại phòng thi.

---

## 1. Chuẩn bị trước giờ bảo vệ (Pre-Flight Checklist — 2 phút)

1. **Cơ sở dữ liệu:** Đảm bảo dịch vụ PostgreSQL 18 đang chạy (nếu demo 1 máy dùng `127.0.0.1:5432`, nếu 2 máy LAN điền IP máy chủ vào **Settings → Database Server** và bấm **Test All**).
2. **Dịch vụ Qwen-VL:**
   - Mở **LM Studio**, nạp model `Qwen2.5-VL` và bật **Local Server** (cổng `1234`), **HOẶC** chạy lệnh:
     ```powershell
     python server/qwen_service.py --port 8000
     ```
3. **Phương án dự phòng 1-Click (T4.5):**
   - Nếu webcam tại phòng thi bị ngược sáng hoặc không nhận USB: tại màn hình **Live Inspection**, bấm nút **`🧪 Use Simulation Feed`** (hoặc chọn dropdown **Feed Source → Simulation Feed**). Hệ thống nạp ngay luồng ảnh mẫu chuẩn chạy qua `YoloEngine` (ONNX Runtime) và băm SHA-256 thật 100%.

---

## 2. Ba Kịch Bản Demo Trọng Tâm (T4.4 — 3 Core Showcase Cases)

### Kịch bản 1: Kiện hàng Đạt chuẩn (PASS — Luồng chuẩn tốc độ cao)
1. **Đăng nhập:** Chọn tài khoản nhanh **`Inspector`** (`inspector` / `inspector123`) trên `LoginDialog`.
2. **Quét mã hộp (`Box Intake`):**
   - Nhập hoặc quét mã QR: `AGS:DH00123-07/10` (Đơn hàng Chuối tiêu `BANANA`, ngưỡng dập tối đa 10%, thối 0%).
   - Bấm **Start Inspection** (hoặc bấm **Print QR Label** để trình diễn tính năng sinh nhãn QR ISO/IEC 18004).
3. **Kiểm định trực tiếp (`Live Inspection`):**
   - Chọn mẫu **`🍌 Fresh Bananas (Pass)`** (hoặc đưa hộp chuối tươi vào camera).
   - Bấm **`● Capture Evidence`** → Hệ thống lưu ảnh gốc PNG, băm mã **SHA-256** (64 ký tự) và chạy `banana_defect.onnx`.
   - Bấm **`Finish Inspection →`** → `RuleEngine` đề xuất **`PASS`** (tỷ lệ dập 5% $\le$ ngưỡng 10%, thối 0%).
   - Bấm **`Submit for Review`**.

---

### Kịch bản 2: Kiện hàng Lỗi nghiêm trọng (FAIL — Vượt ngưỡng Critical Defect)
1. **Quét mã hộp (`Box Intake`):**
   - Nhập mã QR: `AGS:DH00123-08/10` → Bấm **Start Inspection**.
2. **Kiểm định trực tiếp (`Live Inspection`):**
   - Chọn mẫu **`🍌 Rotten Bananas (Fail - 1 critical rotten)`**.
   - Bấm **`● Capture Evidence`** → Bấm **`Finish Inspection →`**.
3. **Kết quả Rule Engine (`Assessment Result`):**
   - Hệ thống tự động cảnh báo đỏ **`FAIL`** vì phát hiện lỗi nghiêm trọng (`rotten > 0%`, `is_critical = True`).
   - Bấm **`Submit for Review`**.

---

### Kịch bản 3: Kiện hàng Nghi ngờ — Gọi Qwen-VL Deep Analysis & Reviewer Phê duyệt + Xuất PDF
1. **Quét mã hộp (`Box Intake`):**
   - Nhập mã QR: `AGS:DH00123-09/10` → Bấm **Start Inspection**.
2. **Phân tích chuyên sâu Qwen-VL (`Live Inspection`):**
   - Chọn mẫu **`🍌 Bruised Bananas (Fail - 15% bruised)`** → Bấm **`● Capture Evidence`**.
   - Bấm nút **`Deep Analysis (Qwen-VL)`** → Hộp thoại `VlmResultPanel` hiển thị kết quả phân tích JSON Schema 1.0 từ Qwen-VL: mô tả vết thâm cơ học, kết quả đọc nhãn OCR (`box_code`, `supplier`, `packed_date` đối chiếu khớp đơn hàng), mức độ bất định (`Uncertainty`) và khuyến nghị xử lý.
   - Bấm **`Finish Inspection →`** → **`Submit for Review`**.
3. **Kiểm duyệt viên xác nhận & Xuất biên bản PDF (`Review Queue` & `Reports`):**
   - Bấm **Logout** ở góc phải → Đăng nhập bằng tài khoản **`Admin`** hoặc **`Reviewer`**.
   - Vào **`Review Queue`**: Chọn các hộp vừa gửi, bấm vào ảnh thumbnail trên `EvidenceStrip` để mở hộp thoại phóng to kèm trạng thái **`✔ SHA-256 Verified`**, nhập ghi chú và bấm **`Pass`** / **`Fail`**.
   - Vào **`Inspection History`**: Chọn phiên vừa duyệt, bấm **`📄 Export Certificate PDF`** để mở file PDF biên bản nghiệm thu có nhúng ảnh bằng chứng và dấu niêm phong SHA-256.
   - Vào **`Reports`**: Bấm **`📊 Export Excel (.xlsx)`** và **`📄 Export PDF`** để xuất báo cáo tổng hợp cấp đơn hàng.

