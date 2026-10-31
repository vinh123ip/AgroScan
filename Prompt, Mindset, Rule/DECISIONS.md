# DECISIONS.md — Nhật ký quyết định của AgroScan

Chỉ ghi **quyết định đã được người dùng duyệt**. Ý tưởng do AI đề xuất không được ghi vào mục "Đã duyệt" cho đến khi người dùng xác nhận rõ ràng.

AI đọc tệp này đầu mỗi phiên. Quyết định mới mâu thuẫn quyết định cũ: chỉ ra mâu thuẫn và hỏi người dùng trước khi làm.

---

## Đã duyệt

| ID | Quyết định | Ngày | Ghi chú |
|---|---|---|---|
| D-001 | Ngôn ngữ chính: Python | *(điền ngày)* | Khớp sơ đồ hệ thống |
| D-002 | Giao diện: PySide6, tùy biến bằng QSS | *(điền ngày)* | Khớp sơ đồ hệ thống |
| D-003 | Thị giác máy tính: YOLO chạy cục bộ trên máy trạm | *(điền ngày)* | Khớp sơ đồ hệ thống. Chạy trên laptop GTX 1650 Ti (D-016) |
| D-004 | Mô hình ngôn ngữ-thị giác: Qwen-VL chạy trên máy chủ LAN | *(điền ngày)* | Khớp sơ đồ hệ thống. Chạy trên PC RTX 3060 (D-016) |
| D-005 | Ưu tiên hoạt động ngoại tuyến, không dùng API AI trực tuyến | *(điền ngày)* | Thêm API trực tuyến cần duyệt riêng |
| D-006 | Môi trường: Windows, đóng gói EXE | *(điền ngày)* | |
| D-007 | YOLO: phát hiện/đếm/phân loại. Qwen-VL: phân tích chuyên sâu theo yêu cầu. Python: quyết định nghiệp vụ. **Không cần AI riêng thứ 3** | *(điền ngày)* | Khớp sơ đồ (bước 4, 5, 6). Người dùng xác nhận 01/11/2026: YOLO + Qwen-VL + Python là bộ ba hoàn chỉnh, không thêm model phân loại sâu hay phát hiện bất thường |
| D-008 | Lưu ảnh gốc và lịch sử kiểm tra; không ghi đè | *(điền ngày)* | Khớp sơ đồ (bước 8) |
| D-009 | LangChain là tùy chọn, chỉ dùng khi có lợi ích rõ | *(điền ngày)* | Sơ đồ ghi "tùy chọn" |
| D-010 | Báo cáo xuất PDF và Excel | *(điền ngày)* | Khớp sơ đồ (bước 11) |
| D-011 | AI trả lời người dùng bằng tiếng Việt. Mã nguồn dự án bằng tiếng Anh: tên biến/hàm/lớp/tệp, comment, docstring, commit message | 29/10/2026 | Người dùng xác nhận. Ngôn ngữ giao diện: xem D-013 |
| D-012 | Công cụ AI: Google Antigravity và Claude Code. Tệp khởi động ở gốc repo: `AGENTS.md` (và `CLAUDE.md` trỏ tới) | 29/10/2026 | Người dùng xác nhận công cụ |
| D-013 | Giao diện ứng dụng (menu, nút, thông báo, nhãn) và báo cáo PDF/Excel dùng **tiếng Anh** | 29/10/2026 | Dữ liệu người dùng tự nhập giữ nguyên ngôn ngữ đã nhập |
| D-014 | Cơ sở dữ liệu: **PostgreSQL trên máy chủ trong mạng LAN**. Dùng PostgreSQL ngay từ đầu, demo cài trên 1 máy, app trỏ tới bằng địa chỉ cấu hình được; lên LAN chỉ cần đổi địa chỉ | 01/11/2026 | Định hướng tương lai: mô hình nhà máy, nhiều trạm |
| D-015 | **Luồng 12 bước là hướng chính của dự án**; `ROADMAP.md` chỉ tham khảo | 29/10/2026 | |
| D-016 | **Phân vai 2 máy qua LAN.** Máy chủ (PC i5-12400F, RTX 3060 12 GB, 32 GB RAM): chạy PostgreSQL, Qwen-VL service, thư mục chia sẻ SMB. Máy trạm (laptop i7-10750H, GTX 1650 Ti 4 GB VRAM, 16 GB RAM): chạy ứng dụng PySide6, camera, YOLO, máy quét barcode | 01/11/2026 | YOLO trên máy trạm vì camera gắn ở đó. Qwen-VL trên máy chủ vì GPU 4 GB không đủ |
| D-017 | **Dịch vụ Qwen-VL:** Chạy qua phần mềm tải AI của Microsoft (tương tự Ollama) trên máy chủ, cung cấp HTTP REST API nội bộ trong LAN. Laptop gọi qua mạng khi người dùng bấm "Phân tích sâu" | 01/11/2026 | Chỉ gọi khi người dùng bấm; hệ thống gợi ý "Nên phân tích sâu" khi YOLO không chắc chắn. Có timeout và bắt lỗi; nếu server không phản hồi thì nút báo không khả dụng |
| D-018 | **Lưu trữ ảnh qua LAN:** Thư mục mạng dùng chung Windows Share (SMB) trên máy chủ (ví dụ `\\SERVER_IP\AgroScan_Data`). Laptop ghi trực tiếp, DB lưu đường dẫn tương đối | 01/11/2026 | Đơn giản nhất, không cần code thêm file server |
| D-019 | **Barcode: 1 mã = 1 hộp = 1 phiên kiểm tra.** Một đơn hàng gồm nhiều hộp, mỗi hộp có barcode riêng do AgroScan tự sinh QR nội bộ, cấu trúc `AGS:<Mã_Đơn>-<Số_Hộp>/<Tổng>` (ví dụ `AGS:DH00123-03/10`). Nhìn mã biết hộp thuộc đơn nào. Vẫn tra DB để xác thực | 01/11/2026 | Thuận tiện demo. Nếu cần mua barcode thật sau thì bổ sung |
| D-020 | **Luồng quét liên tục (Non-blocking):** Khi quét barcode hộp mới, phiên hộp trước tự chuyển sang "Pending Review" (kết quả AI đã lưu). Người kiểm duyệt xác nhận sau theo danh sách, trạm không phải chờ | 01/11/2026 | |
| D-021 | **Kiểm tra lại:** Quét lại cùng barcode → tạo phiên mới cho hộp đó. Phiên cũ giữ nguyên làm lịch sử. Mỗi hộp tại một thời điểm chỉ có 1 phiên đang mở | 01/11/2026 | |
| D-022 | **Kết quả cấp đơn hàng:** Mỗi hộp có kết quả riêng. Đơn chỉ là nhóm, báo cáo hiển thị kiểu "8/10 hộp đạt, 1 chờ, 1 không đạt" | 01/11/2026 | Đơn không có trạng thái Đạt/Không đạt đơn lẻ, chỉ có tổng hợp |
| D-023 | **Quy tắc đánh giá chất lượng (Python rule engine, cấu hình trong DB theo từng loại sản phẩm):** (1) Tỷ lệ quả lỗi theo từng loại lỗi vượt ngưỡng → Đề xuất Không đạt. (2) Có lỗi nghiêm trọng (thối/mốc, loại nào nghiêm trọng do người dùng cấu hình) → Đề xuất Không đạt ngay. (3) Độ tin cậy YOLO thấp hoặc quá ít quả được nhận diện → Chuyển "Pending Review" | 01/11/2026 | Ngưỡng cụ thể cấu hình trong DB, không hardcode |
| D-024 | **YOLO model chuyên hóa theo loại quả.** Huấn luyện model riêng cho từng loại (ví dụ `banana_defect.onnx`, `apple_defect.onnx`). Khi quét mã đơn, hệ thống biết loại quả và tự nạp model tương ứng. Đa quả: chuối, táo và các loại khác (cần tìm dataset công khai trên Roboflow/Kaggle) | 01/11/2026 | Model nhỏ chạy nhẹ trên GTX 1650 Ti; phân loại lỗi chính xác hơn model chung. Hệ thống tự đối chiếu loại quả camera thấy với loại khai báo trên đơn |
| D-025 | **Tracking chống đếm trùng:** Tích hợp thuật toán theo dõi vật thể nhẹ (ByteTrack / Centroid Tracking). Mỗi quả có 1 ID duy nhất trên video preview, khi kéo hộp qua lại camera vẫn nhận diện đúng quả đó | 01/11/2026 | |
| D-026 | **Số liệu realtime vs chính thức (Q-007 — ĐÃ ĐÓNG).** Chỉ số realtime trên video = số quả đang thấy trong khung hình hiện tại và tỷ lệ theo loại, làm mượt (moving average) qua vài khung hình. **Không** lấy tổng số ID từng xuất hiện. Số liệu chính thức lưu DB và báo cáo = tính từ ảnh tĩnh chụp khi hộp dừng ổn định (hoặc nút chụp tay), có băm SHA-256. Hai phần bổ sung cho nhau | 01/11/2026 | Video realtime = visual feedback cho nhân viên. Ảnh tĩnh = bằng chứng pháp lý và nguồn số liệu chính thức |
| D-027 | **Phân quyền & Đăng nhập:** Tạo sẵn 3 tài khoản mặc định (admin, inspector, reviewer) kèm màn hình Login đơn giản. Có nút chọn nhanh tài khoản cho tiện demo. Người kiểm duyệt duyệt từ danh sách "Pending Review" trên bất kỳ máy nào trong LAN | 01/11/2026 | |
| D-028 | **Cấu hình kết nối LAN:** Màn hình Settings trên ứng dụng máy trạm cho phép cấu hình IP máy chủ DB, URL dịch vụ AI, đường dẫn thư mục lưu ảnh (kèm nút "Test Connection"). Khi đổi mạng chỉ cần sửa IP trên giao diện | 01/11/2026 | |
| D-029 | **Nhập dữ liệu (Bước 1):** Excel (.xlsx) và CSV là kênh nhập chính, cung cấp file mẫu template. PDF giao cho Qwen-VL trích xuất. Tích hợp khung chat AI ở Bước 10 để hỏi đáp số liệu và gợi ý xuất file (định hướng tương lai) | 01/11/2026 | |
| D-030 | **Bộ trạng thái chuẩn hóa (Bỏ CONDITIONAL_PASS):** `SessionStatus` (IN_PROGRESS, PENDING_REVIEW, COMPLETED); `AiRecommendation` (PASS, FAIL, NEEDS_REVIEW); `ReviewerDecision` (PASS, FAIL, RE_INSPECT) | 01/11/2026 | Nghiệp vụ rõ ràng: chỉ Nhận hoặc Trả hàng; nghi ngờ thì đưa vào NEEDS_REVIEW / RE_INSPECT |
| D-031 | **Nguồn dữ liệu kiểm định: Camera-first.** Bỏ trang upload file ảnh độc lập. Tích hợp tùy chọn giả lập nguồn video/ảnh (simulation feed) ngay trong Live Inspection phục vụ demo khi thiếu camera | 01/11/2026 | Giữ đúng chuẩn trạm kiểm định công nghiệp, vừa an toàn khi bảo vệ đồ án |
| D-032 | **Phân quyền giao diện (Dynamic Role-based UI):** LoginDialog hỗ trợ 3 nút chọn nhanh (Admin, Inspector, Reviewer). Ẩn hẳn các trang quản trị (Settings, Users, Catalog) với Inspector; sidebar tự co giãn cập nhật động khi đổi tài khoản | 01/11/2026 | Đạt chuẩn bảo mật và mượt mà cho trải nghiệm chấm đồ án |

*(D-001 đến D-010 được rút từ hai tài liệu quy tắc cũ và đối chiếu với sơ đồ. Hãy xác nhận từng mục và điền ngày.)*

## Ghi nhận môi trường (dữ kiện, không phải quyết định)

- Máy phát triển / máy chủ demo: Intel i5-12400F, NVIDIA RTX 3060 12 GB, RAM 32 GB (29/10/2026).
- Máy trạm demo: laptop Intel i7-10750H, NVIDIA GTX 1650 Ti (4 GB VRAM), RAM 16 GB (01/11/2026 — người dùng xác nhận 16 GB RAM).
- Máy trạm thu mua thật khi triển khai: chưa biết (laptop demo chỉ là đại diện).

## Chờ quyết định

AI **không được tự chọn** các mục này. Hỏi người dùng khi công việc phụ thuộc vào chúng.

| ID | Vấn đề | Vì sao cần chốt | Phương án |
|---|---|---|---|
| Q-004 | **"Sai mã" — cách xử lý cụ thể.** Đã xác nhận 4 tình huống (1: mã không có trong DB; 2: mã trùng/đơn kiểm xong; 3: hàng trước camera khác loại khai báo; 4: nhãn lô/NCC khác khai báo). **Chưa xác nhận:** cách xử lý từng tình huống, mã quét nằm ở đâu (giấy đơn hay dán trên hàng) | Ảnh hưởng KPI và thao tác kiểm duyệt | **Đề xuất AI, chưa duyệt:** Lúc tiếp nhận (1, 2): chặn, ghi sự kiện, không tạo kết quả. Sau kiểm tra (3, 4): đánh dấu "nghi sai hàng", chuyển reviewer. Hỏi khi làm bước 3 và 6 |
| Q-005 | Nguồn PDF ở bước 1: trích dữ liệu gì từ PDF (danh sách đơn? tiêu chuẩn?) | Giao cho Qwen-VL đọc (D-029), nhưng cần biết cấu trúc PDF mẫu | Ưu tiên thấp, hỏi khi làm chức năng nhập PDF |

## Đề xuất tinh chỉnh luồng 12 bước (chưa duyệt)

Theo D-015. Mỗi mục cần người dùng duyệt riêng trước khi thành yêu cầu.

| ID | Đề xuất | Lý do | Trạng thái |
|---|---|---|---|
| P-001 | Tách trạng thái **đơn hàng** và **phiên kiểm tra** thành máy trạng thái tường minh | Một đơn có nhiều hộp/phiên; tránh đếm sai KPI | **Đã tích hợp vào D-019, D-020, D-021, D-022** |
| P-002 | Chặn mã sai ngay ở bước 3 (tình huống 1, 2 của Q-004) | Tiết kiệm kiểm tra vô ích | Chờ Q-004 |
| P-003 | Lưu **bản chụp tiêu chí áp dụng** vào từng phiên kiểm tra | Sửa tiêu chí sau không sai báo cáo cũ | Chưa duyệt |
| P-004 | Định nghĩa cụ thể thế nào là "mâu thuẫn" giữa YOLO và Qwen | Bước 6 hiện chỉ nói "mâu thuẫn" chung chung | Chưa duyệt |
| P-006 | Cấu trúc làm việc nhóm: page registry theo key, tách tầng, mock AI, QSS theo module, migration, `.gitignore`, test, CI, bảo vệ nhánh `main` | Tránh thành viên ảnh hưởng chéo | Chưa duyệt, chưa kiểm chứng trên repo |

## Đã thay thế / hủy bỏ

| ID | Quyết định cũ | Lý do thay thế | Ngày |
|---|---|---|---|
| *(Q-001)* | Chưa chốt DB (SQLite hay PostgreSQL) | Đã chốt PostgreSQL (D-014) | 01/11/2026 |
| *(Q-002)* | Chưa chốt YOLO và Qwen-VL chạy ở đâu | Đã chốt phân vai 2 máy (D-016, D-017) | 01/11/2026 |
| *(Q-007)* | Chưa chốt số liệu chính thức lấy từ đâu | Đã chốt: ảnh tĩnh là chính thức, video là tham khảo (D-026) | 01/11/2026 |
| *(P-005)* | Phạm vi demo đầu chỉ 1 loại sản phẩm | Người dùng muốn nhiều loại quả với model chuyên hóa (D-024) | 01/11/2026 |

---

## Mẫu thêm quyết định mới

```
| D-0XX | <quyết định> | <ngày> | <lý do ngắn, ảnh hưởng> |
```
