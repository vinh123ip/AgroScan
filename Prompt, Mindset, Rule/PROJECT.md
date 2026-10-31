# PROJECT.md — Bối cảnh, kiến trúc và quy tắc nghiệp vụ AgroScan

Tài liệu mô tả **cái gì cần xây** và **ràng buộc nghiệp vụ**. Đây là *ý định*, không phải trạng thái hiện tại: luôn kiểm tra code thực tế và `PROGRESS.md` trước khi xác định cái gì đã có.

---

## 1. Tổng quan

AgroScan là ứng dụng desktop hỗ trợ thu mua và kiểm tra chất lượng nông sản, có khả năng mở rộng cho các nhóm hàng hóa khác. Đồ án tốt nghiệp ngành Software Engineering, Duy Tan University.

## 2. Công nghệ đã thống nhất

Không đổi nếu chưa có lý do kỹ thuật rõ ràng và sự đồng ý của người dùng (xem `DECISIONS.md`).

| Thành phần | Lựa chọn |
|---|---|
| Ngôn ngữ | Python |
| Giao diện | PySide6, tùy biến bằng QSS |
| Cơ sở dữ liệu | **PostgreSQL trên máy chủ trong LAN** (D-014). Dùng ngay từ đầu; demo cài trên 1 máy, app trỏ tới bằng địa chỉ cấu hình được |
| Thị giác máy tính | YOLO chạy cục bộ **trên máy trạm** (D-003, D-016). Model chuyên hóa theo loại quả (D-024). Tích hợp ByteTrack chống đếm trùng (D-025) |
| Mô hình ngôn ngữ-thị giác | Qwen-VL chạy **trên máy chủ** qua HTTP REST nội bộ (D-004, D-016, D-017). Phần mềm tải AI của Microsoft (tương tự Ollama) |
| LangChain | Tùy chọn; chỉ dùng khi có lợi ích rõ ràng |
| Xuất báo cáo | Thư viện Python tạo PDF và Excel |
| Triển khai | Windows, đóng gói EXE |
| Vận hành | Ưu tiên ngoại tuyến; **không** phụ thuộc API AI trực tuyến |
| Lưu trữ ảnh | Thư mục mạng dùng chung Windows Share (SMB) trên máy chủ (D-018) |
| Nhập dữ liệu | Excel/CSV là kênh chính; PDF giao cho Qwen-VL trích xuất (D-029) |

### Phần cứng demo (D-016)

| Vai trò | Phần cứng | Chạy gì |
|---|---|---|
| **Máy chủ** (PC) | i5-12400F, RTX 3060 12 GB, 32 GB RAM | PostgreSQL, Qwen-VL service (HTTP REST), thư mục SMB lưu ảnh |
| **Máy trạm** (Laptop) | i7-10750H, GTX 1650 Ti 4 GB VRAM, 16 GB RAM | Ứng dụng PySide6, camera, YOLO (ONNX) + ByteTrack, máy quét barcode 2D USB |

### Vai trò AI đã chốt (D-007)

Chỉ cần 2 thành phần AI + Python, **không cần AI riêng thứ 3:**

- **YOLO (Mắt nhìn nhanh — Edge/Workstation):** Phát hiện, đếm tức thời, định vị bounding box, phân loại lỗi cơ bản (fresh/bruised/rotten). Model chuyên hóa theo loại quả, chạy nhẹ trên GTX 1650 Ti.
- **Qwen-VL (Bộ não tư duy sâu — Server):** Phân tích chuyên sâu khi người dùng yêu cầu, giải thích dấu hiệu hư hỏng, đọc PDF trích xuất dữ liệu, chat báo cáo.
- **Python (Trọng tài — Deterministic Engine):** Áp dụng tiêu chí và quy tắc nghiệp vụ, tính toán kết quả chính thức. Mọi con số và quyết định Đạt/Không đạt đều do Python quyết định, không để AI tính toán số học.

## 3. Luồng nghiệp vụ mục tiêu (12 bước theo sơ đồ hệ thống)

Nguồn: sơ đồ luồng hệ thống do người dùng cung cấp (29/10/2026). Đây là ý định thiết kế, chưa phải trạng thái đã triển khai.

1. **Chuẩn bị và nhập dữ liệu ban đầu.** Nguồn: Excel/CSV (kênh chính), PDF (giao Qwen-VL trích xuất). Nội dung: danh sách đơn hàng, thông tin sản phẩm, tiêu chí kiểm định, nhà cung cấp/khách hàng, người dùng và phân quyền. Kiểm tra định dạng, loại trùng, chuẩn hóa (mã, tên, đơn vị), báo lỗi nếu sai định dạng, nhập vào DB. Cung cấp file mẫu template cho Excel/CSV.
2. **Quản lý danh mục và thiết lập hệ thống.** Danh mục sản phẩm (tên, category, hình ảnh mẫu, tiêu chí chất lượng); quản lý tiêu chí kiểm định (ngưỡng từng loại sản phẩm, các loại lỗi như dập/thối/mốc, loại nào nghiêm trọng); quản lý người dùng (3 vai trò: admin/inspector/reviewer; phân quyền chức năng); cấu hình hệ thống (IP máy chủ DB, URL dịch vụ AI, đường dẫn lưu ảnh SMB, cấu hình model YOLO theo loại quả, thiết bị camera). **Model YOLO chuyên hóa theo loại quả:** mỗi loại quả gắn với file model riêng (D-024).
3. **Tiếp nhận đơn hàng.** Quét mã vạch/QR bằng máy quét 2D USB (hoạt động như bàn phím) hoặc tìm kiếm mã đơn. **1 barcode = 1 hộp = 1 phiên kiểm tra** (D-019). Một đơn hàng gồm nhiều hộp, mỗi hộp có QR do AgroScan tự sinh: `AGS:<Mã_Đơn>-<Số_Hộp>/<Tổng>`. Hiển thị thông tin đơn (mã đơn, sản phẩm, nhà cung cấp, số lượng dự kiến, tiêu chuẩn, trạng thái). **Quét mã mới:** phiên hộp trước tự chuyển sang "Pending Review" (D-020). **Quét lại mã cũ:** tạo phiên mới, phiên cũ giữ nguyên làm lịch sử (D-021).
4. **Kiểm tra hàng hóa (realtime + ảnh tĩnh).** Camera livestream; YOLO model chuyên hóa (nạp theo loại quả trên đơn) phát hiện, đếm, phân loại tình trạng (fresh/bruised/rotten), hiển thị bounding box. Tích hợp **ByteTrack** chống đếm trùng khi hộp bị kéo qua lại. **Chỉ số realtime:** số quả đang thấy trong khung hình và tỷ lệ theo loại, làm mượt (moving average) qua vài khung hình. Không lấy tổng số ID từng xuất hiện. **Ảnh bằng chứng:** hệ thống tự chụp ảnh tĩnh khi hộp dừng ổn định; có nút chụp tay làm phương án dự phòng ("chữa cháy"). Ảnh tĩnh được băm SHA-256, lưu vào kho SMB và DB làm bằng chứng gốc (D-026).
5. **Phân tích chuyên sâu với Qwen (tùy chọn).** Chỉ gọi khi người dùng bấm "Phân tích sâu"; hệ thống gợi ý tự động trên ảnh YOLO không chắc chắn (D-017). Qwen-VL chạy trên máy chủ qua HTTP REST nội bộ. Nhận xét chi tiết, giải thích dấu hiệu hư hỏng, so sánh với tiêu chí; trả về cấu trúc JSON và nhận xét ngôn ngữ tự nhiên. Có timeout và bắt lỗi; nếu server không phản hồi thì nút báo không khả dụng.
6. **Đối chiếu và đánh giá kết quả (Python).** Kết hợp kết quả YOLO và Qwen (nếu có), áp dụng tiêu chí kiểm định trong DB (D-023): (1) Tỷ lệ lỗi từng loại vượt ngưỡng → Đề xuất Không đạt. (2) Có lỗi nghiêm trọng (thối/mốc, cấu hình được) → Đề xuất Không đạt ngay. (3) Độ tin cậy thấp hoặc quá ít quả → Chuyển "Pending Review". **Số liệu chính thức tính từ ảnh tĩnh đã lưu và băm** (D-026), không từ video realtime.
7. **Hiển thị báo cáo và người kiểm duyệt xác nhận.** Xem ảnh chi tiết từng quả, xem nhận xét AI (nếu có), **người kiểm duyệt** (vai trò riêng, đăng nhập theo tài khoản) xác nhận Đạt / Không đạt / Cần kiểm tra lại, ghi chú nếu cần. Người kiểm duyệt duyệt từ danh sách "Pending Review" trên bất kỳ máy nào trong LAN (D-027).
8. **Lưu kết quả vào cơ sở dữ liệu.** Thông tin hàng và kết quả kiểm tra, ảnh gốc và ảnh đã xử lý, kết quả YOLO và Qwen, quyết định của người kiểm duyệt, metadata (thời gian, người thực hiện, thiết bị), hash SHA-256 của ảnh gốc, lịch sử thao tác.
9. **Quản lý và tra cứu dữ liệu.** Tìm kiếm theo mã đơn, ngày, sản phẩm; xem lịch sử kiểm tra, ảnh và kết quả chi tiết; chỉnh sửa ghi chú (nếu có quyền); quản lý tiêu chí, sản phẩm, người dùng.
10. **Báo cáo và thống kê.** Bộ lọc (khoảng thời gian, trạng thái, loại sản phẩm, nội dung); tổng quan (tổng đơn, đạt, không đạt, sai mã), biểu đồ theo ngày, tỷ lệ chất lượng, chi tiết đơn hàng; nhận xét tổng hợp do Qwen viết khi người dùng yêu cầu. **Kết quả cấp đơn hàng:** tổng hợp từ các hộp, hiển thị kiểu "8/10 hộp đạt, 1 chờ, 1 không đạt" (D-022). **Định hướng tương lai:** khung chat AI hỏi đáp số liệu và gợi ý xuất file (D-029).
11. **Xuất báo cáo.** PDF và Excel theo bộ lọc hiện tại (số liệu, biểu đồ, bảng chi tiết, ảnh kèm mã hash nếu cần), Qwen viết phần nhận xét tổng kết, lưu lịch sử xuất báo cáo.
12. **Kết thúc và sử dụng tiếp.** Báo cáo lưu để tải lại, dữ liệu giữ trong hệ thống, tiếp tục kiểm tra đơn mới. Phiên chưa hoàn tất phải tiếp tục được quản lý, không bị coi là đã kết thúc.

**Lưu ý khi đọc sơ đồ:**
- Các "quy tắc ví dụ" ở bước 6 (tỷ lệ dập ≤ 10% là đạt, có quả thối là không đạt, sai mã định danh là không đạt, kết quả mâu thuẫn cần kiểm duyệt) chỉ là **ví dụ minh họa**. Tiêu chí thật là cấu hình theo từng loại sản phẩm ở bước 2, lưu trong DB. Không hardcode ngưỡng trong code.
- Mô hình trạng thái kết quả (Sai mã là lỗi hay trạng thái riêng, "Cần kiểm tra lại" so với "Chờ xác nhận") chưa nhất quán trong sơ đồ: xem `DECISIONS.md` Q-004.
- Sơ đồ viết bằng tiếng Việt, nhưng nhãn giao diện và báo cáo trong ứng dụng dùng tiếng Anh (D-013).

## 4. Kiến trúc phân tầng

Giữ kiến trúc hiện có nếu còn đáp ứng yêu cầu. Chỉ thêm lớp hoặc tệp khi có mục đích rõ ràng.

| Tầng | Trách nhiệm | Không được |
|---|---|---|
| **Giao diện** (PySide6, QSS) | Trang, hộp thoại, nhận thao tác, hiển thị dữ liệu, trạng thái, lỗi | Chứa quy tắc nghiệp vụ phức tạp hoặc SQL rải rác |
| **Nghiệp vụ** | Điều phối luồng, kiểm tra dữ liệu và trạng thái, áp tiêu chí, tính kết quả chính thức, xử lý ngoại lệ | |
| **Truy cập dữ liệu** | Truy vấn, lưu, giao dịch, thay đổi cấu trúc có kiểm soát (PostgreSQL qua psycopg hoặc SQLAlchemy) | Nhân bản cùng logic truy vấn ở nhiều nơi |
| **AI / thị giác máy tính** | Tải và quản lý model YOLO (chuyên hóa theo quả), suy luận, ByteTrack tracking, chuẩn hóa kết quả. Gọi Qwen-VL qua HTTP REST. Lỗi, timeout, tài nguyên | Để logic riêng của một model lan sang module không liên quan |
| **Báo cáo** | Tổng hợp dữ liệu chính thức, KPI, biểu đồ, tạo PDF/Excel | Dùng nội dung AI sinh ra làm nguồn số liệu |
| **Thiết bị** | Camera, máy quét barcode (USB HID) | |

## 5. Quy tắc nghiệp vụ và toàn vẹn dữ liệu

### Cấu trúc đơn hàng — hộp — phiên

- **Đơn hàng (Order):** Nhóm các hộp. Không có trạng thái Đạt/Không đạt đơn lẻ; chỉ có tổng hợp (D-022).
- **Hộp (Box):** Đơn vị kiểm tra, 1 barcode = 1 hộp (D-019). Có kết quả riêng.
- **Phiên kiểm tra (Session):** Một lần kiểm tra cụ thể của một hộp. Mỗi hộp có thể có nhiều phiên (kiểm tra lại). Chỉ 1 phiên đang mở tại một thời điểm (D-021).

### Quy tắc chung

- Không âm thầm ghi đè lịch sử kiểm tra.
- Phân biệt **kết quả AI đề xuất** với **kết quả đã được người kiểm duyệt xác nhận**.
- Đơn đang chờ xác nhận **không** được tính là đạt hay không đạt cho đến khi có quyết định cuối.
- Kiểm tra mã định danh trước khi cho tiếp tục quy trình.
- Kiểm tra: dữ liệu thiếu, ảnh bị mất, mã trùng, phiên chưa hoàn tất.
- Dùng giao dịch DB cho các thao tác phải thành công hoặc thất bại đồng thời.

### Bảo toàn bằng chứng ảnh

- Giữ ảnh gốc tách biệt với ảnh đã xử lý hoặc có bounding box.
- Không ghi đè ảnh gốc khi suy luận.
- Tính SHA-256 trên đúng nội dung byte của tệp ảnh gốc, **trước** khi chạy suy luận.
- Lưu: hash, thời gian chụp, liên kết đến đơn hàng/phiên kiểm tra, **đường dẫn tương đối** (để dời thư mục không hỏng liên kết).
- Xử lý rõ hai ca lỗi: lưu ảnh được nhưng ghi DB thất bại, và ngược lại.
- Lưu ý: hash giúp phát hiện thay đổi dữ liệu, không tự chứng minh tính hợp lệ pháp lý của hồ sơ.

## 6. Quy tắc AI

### YOLO
- Chỉ dùng cho nhiệm vụ mà model và dữ liệu huấn luyện hỗ trợ. Nhận diện được loại quả không có nghĩa nhận diện được hư hỏng.
- Model chuyên hóa theo loại quả (D-024): mỗi sản phẩm gắn với file model riêng. Khi mở đơn, nạp đúng model.
- Không khẳng định đủ chính xác khi chưa kiểm thử.
- Cấu hình model và ngưỡng tin cậy phải tường minh, nằm ngoài code logic.
- Không chạy suy luận dài trên luồng giao diện. Đo hiệu năng thực tế, không giả định realtime.
- Chỉ số realtime = số quả đang thấy trong khung hình, làm mượt moving average. **Không** cộng dồn tổng ID (D-026).

### Qwen-VL
- Chạy trên máy chủ qua HTTP REST nội bộ trong LAN (D-017).
- Chỉ gọi khi người dùng bấm; hệ thống gợi ý "Nên phân tích sâu" khi YOLO không chắc chắn.
- Tách bạch: dấu hiệu quan sát được / nhận định của AI / mức không chắc chắn / đề xuất.
- Kiểm tra định dạng đầu ra trước khi dùng.
- Không âm thầm ghi đè kết quả YOLO hoặc quyết định của con người.
- Có phương án dự phòng khi model lỗi, quá thời gian chờ hoặc trả dữ liệu không hợp lệ.
- Cũng dùng để trích xuất dữ liệu từ PDF (D-029) và chat báo cáo (D-029).

### LangChain
- Chỉ đưa vào khi cần quản lý prompt, chuẩn hóa đầu ra hoặc điều phối Qwen mà có lợi rõ ràng cho kiến trúc.
- Không thay thế logic Python thông thường. Không gọi LLM trong vòng lặp xử lý từng khung hình camera.

### Quyết định chất lượng cuối cùng (D-023)
- Python áp dụng tiêu chí nghiệp vụ cấu hình trong DB theo từng loại sản phẩm.
- Tỷ lệ lỗi vượt ngưỡng → Đề xuất Không đạt. Lỗi nghiêm trọng → Đề xuất Không đạt ngay. Thiếu chắc chắn → Pending Review.
- Người kiểm duyệt phải có thể xác nhận hoặc yêu cầu kiểm tra lại.
- Không tuyên bố ứng dụng xác nhận an toàn thực phẩm hay tuân thủ pháp luật khi chưa có phương pháp và bằng chứng phù hợp.
- Nội dung AI sinh ra và dữ liệu nhập là **dữ liệu chưa tin cậy**.

## 7. Hiệu năng và tài nguyên

- Tác vụ dài (suy luận, nhập hàng loạt, xuất báo cáo) chạy trên worker/thread phù hợp với PySide6; cập nhật giao diện bằng cơ chế an toàn của Qt.
- Hàng đợi khung hình camera có giới hạn.
- Dọn dẹp tài nguyên: đóng camera, kết thúc tác vụ nền.
- Chặn thao tác trùng khi một chức năng đang chạy.
- Hiển thị trạng thái xử lý và lỗi có thể khắc phục.
- Kiểm tra hành vi đóng ứng dụng khi AI hoặc tác vụ nền còn chạy.
- Không tối ưu sớm khi chưa có số liệu, nhưng không bỏ qua lỗi thiết kế gây treo giao diện hoặc rò rỉ tài nguyên.

## 8. Nhập, lưu và xuất dữ liệu

- Kiểm tra tệp nhập trước khi ghi DB; báo rõ dòng nào lỗi và nguyên nhân.
- Dữ liệu trùng xử lý theo quy tắc xác định; không âm thầm bỏ qua dữ liệu xung đột.
- Nhập hàng loạt dùng giao dịch.
- Thay đổi cấu trúc DB không được làm mất dữ liệu cũ. Quản lý schema bằng migration.
- Xác định rõ mốc thời gian dùng để lọc báo cáo.
- PDF và Excel dùng **cùng** bộ lọc và phạm vi dữ liệu.
- Số liệu chính thức do Python tính. LLM không tự đếm bản ghi, suy đoán tổng số đơn hay tính KPI từ văn bản.

## 9. Bảo mật và cấu hình

- Không hardcode mật khẩu, khóa bí mật, thông tin xác thực.
- Kiểm tra đường dẫn tệp và dữ liệu người dùng cung cấp.
- Tuân thủ phân quyền đã có (3 vai trò: admin/inspector/reviewer — D-027).
- Không ghi dữ liệu nhạy cảm không cần thiết vào log.
- Đường dẫn model, ngưỡng, cấu hình quản lý tập trung, dễ bảo trì.
- **Cấu hình kết nối LAN** (D-028): Màn hình Settings trên ứng dụng máy trạm cho phép cấu hình IP máy chủ DB, URL dịch vụ AI, đường dẫn thư mục lưu ảnh, kèm nút "Test Connection".
- Dịch vụ Qwen-VL trên máy chủ chỉ mở trong LAN (D-017). Không thêm dịch vụ mạng ra Internet, telemetry, hoặc API AI trực tuyến khi chưa được duyệt.

## 10. Roadmap

Dự án phát triển theo giai đoạn. Tiến độ thật ghi ở `PROGRESS.md`, **không** suy ra từ tài liệu này.

- Giữ nguyên chức năng đã hoàn thành.
- Không bỏ phần nền tảng để nhảy sang AI nếu chưa được yêu cầu.
- Hoàn thành được xác định bằng hành vi kiểm chứng được và tiêu chí nghiệm thu, không phải vì đã có mã.
- Thiếu điều kiện tiên quyết: giải thích và đề xuất công việc nhỏ nhất cần làm trước.
- Không tự đặt lại roadmap vì có ý tưởng kiến trúc mới.
